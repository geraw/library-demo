"""Pinned Windows native-Provengo package -> immutable ZIP -> Natchan v004.
This coordinator never actuates experimental HTTP itself or changes generator/IR/tests.
"""
import argparse
from contextlib import contextmanager
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import queue
import threading
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / 'pins.json').read_text(encoding='utf-8'))
MAX_BYTES = 512 * 1024 * 1024
FIXED_OUTPUTS = ('result.json','findings.json','coverage.json','provenance.json','diagnostics.json','analysis.json','report.md')


class IntegrationError(RuntimeError): pass


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value): Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def command(args, *, cwd=None, env=None, log=None, check=True, timeout=240):
    # Never pass credentials on argv. No shell and no command-line string interpolation.
    try:
        result=subprocess.run([str(x) for x in args],cwd=cwd,env=env,capture_output=True,
                              encoding='utf-8',errors='replace',timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise IntegrationError('Command timed out: '+Path(str(args[0])).name) from exc
    if log:Path(log).write_text((result.stdout or '')+(result.stderr or ''),encoding='utf-8')
    if check and result.returncode:
        raise IntegrationError('Command failed: '+Path(str(args[0])).name+'; exit '+str(result.returncode))
    return result


def checkout(original, pin, destination):
    """New detached worktree; never reset/check out an existing user's working tree."""
    if original and (original/'.git').exists():
        remote=command(['git','-C',original,'remote','get-url','origin']).stdout.strip()
        if remote.removesuffix('.git').lower()!=pin['repository'].removesuffix('.git').lower():
            raise IntegrationError('Original repository origin differs from pinned repository')
        command(['git','-C',original,'fetch','origin',pin['branch']])
        available=command(['git','-C',original,'cat-file','-e',pin['commit']+'^{commit}'],check=False)
        if available.returncode:command(['git','-C',original,'fetch','origin',pin['commit']])
        command(['git','-C',original,'-c','core.longpaths=true','worktree','add','--detach',destination,pin['commit']])
    else:
        command(['git','-c','core.longpaths=true','clone','--single-branch','--branch',pin['branch'],pin['repository'],destination])
        command(['git','-C',destination,'checkout','--detach',pin['commit']])
    if command(['git','-C',destination,'rev-parse','HEAD']).stdout.strip()!=pin['commit']:
        raise IntegrationError('Pinned checkout verification failed')
    if command(['git','-C',destination,'status','--porcelain','--untracked-files=no']).stdout.strip():
        raise IntegrationError('Pinned checkout has modified tracked files')
    return destination


@contextmanager
def experiment_lock(study_root):
    path=study_root/'work-v001-active.lock'
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:raise IntegrationError('Another work-v001 run or interrupted producer owns '+str(path)) from exc
    with os.fdopen(fd,'w') as stream:json.dump({'pid':os.getpid(),'started_utc':datetime.now(timezone.utc).isoformat()},stream)
    interrupted=False
    try:yield
    except (KeyboardInterrupt,SystemExit):interrupted=True;raise
    finally:
        if not interrupted:path.unlink(missing_ok=True)


def docker_ready():
    if command(['docker','info','--format','{{.ServerVersion}}'],check=False,timeout=20).returncode==0:return
    desktop=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'Docker/Docker/Docker Desktop.exe'
    if not desktop.is_file():raise IntegrationError('Docker Desktop is not ready; start it and rerun')
    subprocess.Popen([str(desktop)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(45):
        time.sleep(2)
        if command(['docker','info','--format','{{.ServerVersion}}'],check=False,timeout=20).returncode==0:return
    raise IntegrationError('Docker Desktop did not become ready; no experiment was launched')


def stream_package(args,cwd,env,log):
    # Stream progress while preserving a private local console, never included in the share bundle.
    with Path(log).open('w',encoding='utf-8') as out:
        process=subprocess.Popen([str(x) for x in args],cwd=cwd,env=env,stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,encoding='utf-8',errors='replace')
        lines=queue.Queue()
        def pump():
            try:
                with process.stdout as stream:
                    for line in stream:lines.put(line)
            finally:lines.put(None)
        threading.Thread(target=pump,daemon=True).start()
        started=time.monotonic()
        try:
            while True:
                try:line=lines.get(timeout=15)
                except queue.Empty:
                    print('WORK_V001_NATIVE_RUNNING elapsed_seconds='+str(int(time.monotonic()-started)),flush=True)
                    continue
                if line is None:break
                out.write(line);out.flush();print(line,end='',flush=True)
            return process.wait()
        except BaseException:
            # The producer owns reset/cleanup. Do not terminate the child while it restores the SUT.
            print('Producer cleanup may still be running; do not start a second experiment.',flush=True)
            raise


def new_package(before,after):
    created=sorted(set(after)-set(before))
    if len(created)!=1:raise IntegrationError('Expected exactly one newly closed model package; found '+str(len(created)))
    return created[0]


def inspect_package(package):
    """Read only model artifacts. Count data availability; never trust a producer verdict as a finding."""
    budget=MAX_BYTES;runs=[];metadata={}
    with zipfile.ZipFile(package) as outer:
        names=outer.namelist()
        env_name='ENV_v1_model.txt'
        if env_name not in names:raise IntegrationError('Expected a closed outer model package with ENV_v1_model.txt')
        if outer.getinfo(env_name).file_size>1024*1024:raise IntegrationError('ENV file too large')
        for line in outer.read(env_name).decode('utf-8-sig').splitlines():
            if '=' in line:
                key,value=line.split('=',1);metadata[key.strip()]=value.strip()
        if metadata.get('kind')!='model' or not metadata.get('sut'):raise IntegrationError('Model package metadata is missing')
        for name in names:
            if not re.fullmatch(r'review_v1_s\d+\.zip',name):continue
            size=outer.getinfo(name).file_size;budget-=size
            if budget<0:raise IntegrationError('Expanded evidence limit exceeded')
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                needed=['result_v1.json','gateway-journal.jsonl']
                for member in needed:
                    if member not in inner.namelist():raise IntegrationError('Model run lacks '+member)
                    budget-=inner.getinfo(member).file_size
                    if budget<0:raise IntegrationError('Expanded evidence limit exceeded')
                result=json.loads(inner.read('result_v1.json').decode('utf-8-sig'))
                rows=[json.loads(line) for line in inner.read('gateway-journal.jsonl').decode('utf-8-sig').splitlines() if line.strip()]
                research=sum(r.get('category')=='research' for r in rows)
                if result.get('requests')!=research:raise IntegrationError('Research/result count disagreement')
                if result.get('sut')!=metadata['sut']:raise IntegrationError('Run/package product disagreement')
                runs.append(dict(member=name,seed=result.get('seed'),native_status=result.get('status'),
                    native_exit=result.get('native_exit'),jar_sha256=result.get('jar_sha256'),
                    frozen_jar_hash_matches=result.get('jar_sha256')==PINS['provengo_jar_sha256'],
                    sut_version=result.get('sut_version'),http_records=research,
                    atomicity_records=sum(r.get('category')=='atomicity-check' for r in rows),
                    atom_snapshots_v1=sum(r.get('category')=='atomicity-check' and isinstance(r.get('snapshots'),dict) and r['snapshots'].get('format')=='atom-snapshots/1' for r in rows),
                    divergence_records=sum(r.get('category')=='divergence-check' for r in rows),
                    div_evidence_v1=sum(r.get('category')=='divergence-check' and r.get('evidence_format')=='div-evidence/1' for r in rows)))
    versions={r['sut_version'] for r in runs if r.get('sut_version')}
    if metadata.get('sut_version'):versions.add(metadata['sut_version'])
    if len(versions)>1:raise IntegrationError('Package has more than one observed product version')
    return dict(package_sha256=sha(package),metadata=metadata,runs=runs,
                product=metadata['sut'],product_version=next(iter(versions),'unknown'),
                no_run_evidence=not runs,counts_are_evidence_availability_not_findings=True)


def native_assessment(mode,evidence):
    if mode=='existing-package':return 'NOT_ASSERTED_EXISTING_PACKAGE'
    if not evidence['runs']:return 'NOT_EVALUABLE_NO_RUN_EVIDENCE'
    if not all(r['frozen_jar_hash_matches'] for r in evidence['runs']):return 'NOT_CONFIRMED_JAR_MISMATCH'
    accepted={'COMPLETED','STOPPED_AT_FIRST_FAILURE','TIME_LIMIT'}
    if not all(r['native_status'] in accepted for r in evidence['runs']):return 'INCOMPLETE_NATIVE_EXECUTION'
    return 'NATIVE_PREFIX_RECORDED'


def check_result(output,exit_code):
    result_path=output/'result.json'
    if not result_path.is_file():raise IntegrationError('Analyzer did not write its final result marker')
    result=read(result_path)
    if result.get('wrapper_version')!='natchan-box/4.0.0':raise IntegrationError('Wrong analyzer version')
    if result.get('exit_code')!=exit_code:raise IntegrationError('Process/result exit disagreement')
    for name,spec in result.get('artifacts',{}).items():
        path=output/spec['path']
        if not path.resolve().is_relative_to(output.resolve()) or not path.is_file() or sha(path)!=spec['sha256']:
            raise IntegrationError('Analyzer output artifact hash mismatch: '+name)
    return result


def make_share(run,package,rc_path,private_values):
    """Sanitized COPY; canonical local outputs remain unchanged. Rehash copied artifacts explicitly."""
    share=run/'share';share.mkdir()
    (share/'evidence').mkdir();shutil.copy2(package,share/'evidence'/package.name)
    analysis=share/'analysis';analysis.mkdir();dest=analysis/'output';dest.mkdir()
    original={}
    for name in FIXED_OUTPUTS:
        source=run/'output'/name
        if source.is_file():original['analysis/output/'+name]=sha(source);shutil.copy2(source,dest/name)
    for name in ['integration-status.json','evidence-check.json']:
        if (run/name).is_file():shutil.copy2(run/name,share/name)
    request=read(run/'analysis-request.json')
    request['evidence']['archive']='../evidence/'+package.name
    request.pop('configuration',None)  # sut.json is embedded; share request has no local Git path dependency.
    write(analysis/'analysis-request.json',request)
    replacements=[]
    for value,label in private_values:
        if value:
            for form in {str(value),str(value).replace('\\','/'),str(value).replace('\\','\\\\')}:
                replacements.append((re.compile(re.escape(form),re.I),label))
    def clean(text):
        for pattern,label in replacements:text=pattern.sub(lambda _:label,text)
        return text
    def clean_json(value):
        if isinstance(value,str):return clean(value)
        if isinstance(value,list):return [clean_json(x) for x in value]
        if isinstance(value,dict):return {clean(k):clean_json(v) for k,v in value.items()}
        return value
    for path in share.rglob('*'):
        if path.is_file() and path.suffix=='.json':write(path,clean_json(read(path)))
        elif path.is_file() and path.suffix=='.md':path.write_text(clean(path.read_text(encoding='utf-8')),encoding='utf-8')
    if (dest/'result.json').exists():
        result=read(dest/'result.json')
        for spec in result.get('artifacts',{}).values():
            artifact=dest/spec['path']
            if not artifact.resolve().is_relative_to(dest.resolve()):raise IntegrationError('Export artifact path escapes output')
            spec['sha256']=sha(artifact)
        write(dest/'result.json',result)
    (share/'README.md').write_text('Research evidence and Natchan v004 output\n\nThe evidence ZIP is unchanged. Analysis files are a sanitized export; original file hashes are in EXPORT_MANIFEST.json. Canonical local outputs are retained on the operator machine. The portable request in analysis/ can be run with a fresh output directory. Experiment and analysis statuses are distinct. Evidence-format availability is not itself bug verification. Never add credentials.local.json or run-config.local.json to this package.\n',encoding='utf-8')
    write(share/'EXPORT_MANIFEST.json',dict(schema_version='natchan-share-export/1',
        transform='Sanitized copy of local analysis. Local originals unchanged; copied result artifact hashes refreshed.',
        input_archive_unchanged=True,input_archive_sha256=sha(package),
        original_analysis_sha256=original,
        exported_sha256={p.relative_to(share).as_posix():sha(p) for p in sorted(share.rglob('*')) if p.is_file()}))

    # Inspect nested archive bytes with the pinned producer's existing leak checker.
    checker=run/'producer/toolkit/v1/common/leakcheck.py'
    args=[sys.executable,checker,'--run-config',rc_path,'--dir',share]
    command(args,log=run/'export-leakcheck.log')
    target=run/'natchan-work-v001-review.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(share.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(share).as_posix())
    return target


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original-repo',type=Path,default=Path(r'C:\work\temp\vikunja_study'))
    p.add_argument('--study-root',type=Path,default=Path(r'C:\work\temp\gitea_tse_study'))
    p.add_argument('--jar',type=Path,default=Path(r'C:\work\temp\vikunja_tse_study\Provengo-2026-01-10.uber.jar'))
    p.add_argument('--seed',type=int,default=1);p.add_argument('--package',type=Path)
    a=p.parse_args(argv)
    if sys.version_info<(3,10):p.error('Python 3.10+ is required')
    if a.seed<1:p.error('Seed must be positive')
    a.original_repo=a.original_repo.resolve();a.study_root=a.study_root.resolve();a.jar=a.jar.resolve()
    if not a.study_root.is_dir():p.error('Existing study root required; setup/baseline is not installed by this launcher')
    run=a.study_root/'analysis'/('work-v001-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run.mkdir(parents=True)
    status=dict(integration_version=PINS['integration_version'],producer_commit=PINS['producer']['commit'],
                analyzer_commit=PINS['analyzer']['commit'],mode='existing-package' if a.package else 'native-provengo-model',
                seed=a.seed,state='PREPARING',analyzer_new_sut_requests=0)
    try:
        rc=a.original_repo/'stages/Gitea_Setup_g001/run-config.local.json'
        if not rc.is_file():raise IntegrationError('Existing local run configuration not found: '+str(rc))
        if not a.package:
            if sys.platform!='win32':raise IntegrationError('The native producer launcher requires Windows PowerShell')
            if not a.jar.is_file() or sha(a.jar)!=PINS['provengo_jar_sha256']:
                raise IntegrationError('Frozen Provengo JAR missing or SHA256 mismatch; no experiment launched')
            if not any((a.study_root/'baseline').glob('small-*')):raise IntegrationError('No SMALL baseline found; preserve the existing setup and inspect the path')
        producer=checkout(a.original_repo,PINS['producer'],run/'producer')
        analyzer=checkout(None,PINS['analyzer'],run/'analyzer')
        # Only harmless machine redaction preferences are copied; no credentials or natchan checkout override.
        old_local=a.original_repo/'toolkit/v1/local.json'
        local=read(old_local) if old_local.exists() else {}
        write(producer/'toolkit/v1/local.json',dict(study_root=str(a.study_root),provengo_jar=str(a.jar),redact=local.get('redact',[])))
        command([sys.executable,producer/'toolkit/v1/common/verify.py'],cwd=producer,log=run/'producer-integrity.log')
        command([sys.executable,'-m','unittest','discover','-s',analyzer/'tools/natchan-box-v004/tests','-q'],cwd=analyzer,log=run/'analyzer-tests.log')
        if a.package:package=a.package.resolve()
        else:
            for executable in ['java','docker','powershell']:
                if not shutil.which(executable):raise IntegrationError('Required command not found: '+executable)
            sut=read(producer/PINS['producer']['sut_config'])
            with experiment_lock(a.study_root):
                docker_ready();command(['docker','start',sut['deployment']['container']])
                downloads=Path.home()/'Downloads'
                pattern='v1-'+sut['name']+'-model-????????-??????.zip'
                before=set(downloads.glob(pattern))
                env=dict(os.environ);env['PYTHONIOENCODING']='utf-8'
                env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
                status['state']='NATIVE_PROVENGO_RUNNING';write(run/'integration-status.json',status)
                print('WORK_V001_START_NATIVE_PROVENGO seed='+str(a.seed),flush=True)
                args=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',producer/PINS['producer']['entry'],
                      '-Sut',producer/PINS['producer']['sut_config'],'-StudyRoot',a.study_root,'-ProvengoJar',a.jar,
                      '-RunConfig',rc,'-RunSeeds',str(a.seed)]
                status['producer_process_exit']=stream_package(args,producer,env,run/'producer-console.private.log')
                package=new_package(before,downloads.glob(pattern))
        status['package']=str(package)
        # Independently check the closed ZIP with the secret checker, even for supplied old packages.
        screening=run/'screening';screening.mkdir();shutil.copy2(package,screening/package.name)
        command([sys.executable,producer/'toolkit/v1/common/leakcheck.py','--run-config',rc,'--dir',screening],log=run/'input-leakcheck.log')
        evidence=inspect_package(package);write(run/'evidence-check.json',evidence)
        status.update(experiment_result=evidence['metadata'].get('result'),native_runs=evidence['runs'])
        status['native_execution_assessment']=native_assessment(status['mode'],evidence)
        if evidence['product']!='gitea':raise IntegrationError('This work profile expects Gitea')
        request=dict(schema_version='natchan-request/1',
                     run=dict(id=run.name,tool='provengo',product=evidence['product'],product_version=evidence['product_version']),
                     evidence=dict(adapter='toolkit-v1',archive=str(package),sha256=evidence['package_sha256']),
                     configuration=dict(toolkit_repo=str(producer)))
        write(run/'analysis-request.json',request)
        status['state']='ANALYZING';write(run/'integration-status.json',status)
        print('WORK_V001_START_NATCHAN_V004',flush=True)
        result=command([sys.executable,analyzer/PINS['analyzer']['entry'],'--request',run/'analysis-request.json','--output',run/'output'],
                       cwd=analyzer,log=run/'analyzer-console.log',check=False,timeout=1800)
        analysis=check_result(run/'output',result.returncode)
        status.update(analysis_status=analysis['status'],analysis_exit=result.returncode,counts=analysis.get('counts'))
        if (run/'output/coverage.json').is_file():
            coverage=read(run/'output/coverage.json')
            status['coverage_gap_count']=len(coverage.get('gaps',[]))
            status['resolved_evidence_counts']=dict(Counter(x['family']+':'+x['status'] for x in coverage.get('coverage_audit',{}).get('resolved_measurements',[])))
        if result.returncode:status['state']='ANALYSIS_FAILED'
        elif evidence['no_run_evidence']:status['state']='PRODUCER_STOPPED_NO_RUN_EVIDENCE'
        elif status['mode']=='native-provengo-model' and status['native_execution_assessment']!='NATIVE_PREFIX_RECORDED':status['state']='NATIVE_EXECUTION_INCOMPLETE'
        else:status['state']='ANALYZED'
        write(run/'integration-status.json',status)
        private=[(run,'<integration>'),(a.study_root,'<StudyRoot>'),(a.original_repo,'<original-repo>'),
                 (Path.home(),'<user-profile>'),(os.environ.get('COMPUTERNAME'),'<host>')]
        bundle=make_share(run,package,rc,private)
        upload=a.study_root/'upload';upload.mkdir(exist_ok=True)
        copied=upload/(run.name+'-review.zip');shutil.copy2(bundle,copied)
        print('INTEGRATION_STATUS '+str(run/'integration-status.json'),flush=True)
        print('WORK_V001_STATUS '+status['state']+' ANALYSIS='+analysis['status'],flush=True)
        print('UPLOAD THIS FILE: '+str(copied),flush=True)
        return 0 if status['state']=='ANALYZED' else 2
    except (IntegrationError,OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
        status.update(state='FAILED',error=str(exc));write(run/'integration-status.json',status)
        print('WORK_V001_FAILED '+str(exc),flush=True)
        print('INTEGRATION_STATUS '+str(run/'integration-status.json'),flush=True)
        return 2


if __name__=='__main__':raise SystemExit(main())
