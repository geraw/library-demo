"""Execute the existing Java catalog, without invoking sample or generating tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import threading
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'campaign-v009'))
import resample_split_v009 as previous
from patch_runtime_v011 import patch
runtime,core=previous.runtime,previous.core
SOURCE_SHA='04084199740dedaeacade4efb4310ec8525181ae2de6b8a6376887146b85f514'
ARMS={'control':'none',**previous.ARMS}


def launch(command,folder,name,timeout):
    """Use the existing owned-process watchdog; keep each arm's native log."""
    stop=threading.Event()
    def progress():
        while not stop.wait(30):
            path=folder/'native.jsonl'
            count=len(path.read_text(encoding='utf-8').splitlines()) if path.exists() else 0
            print('V011_PROGRESS '+folder.name+' COMPLETED='+str(count),flush=True)
    watcher=threading.Thread(target=progress,daemon=True);watcher.start()
    try:return runtime.run([str(x) for x in command],folder,name,timeout)
    finally:stop.set();watcher.join()


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def main(args):
    started=time.perf_counter()
    reference,jar,profile=previous.source_inputs(args.reference_campaign,args.jar)
    source=Path(__file__).resolve().parents[1]/'src/StrictGuidedRun.java'
    normalized=source.read_text(encoding='utf-8').replace('\r\n','\n').rstrip('\n')
    if hashlib.sha256(normalized.encode()).hexdigest()!=SOURCE_SHA:
        raise RuntimeError('Fixed Java source changed; review before running a different suite')
    root=reference.parent/('java-fixed-split-v011-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
    root.mkdir(); timing={}; complete=False
    try:
        shutil.copytree(reference/'model',root/'model',ignore=shutil.ignore_patterns('products','__pycache__','.git'))
        shutil.copy2(reference/'sut_buggy_issta.py',root/'sut_buggy_issta.py')
        shutil.copy2(reference/'openapi.json',root/'openapi.json')
        core.write(root/'model_profile.json',profile)
        src=root/'src';src.mkdir();classes=root/'classes';classes.mkdir()
        (src/'StrictGuidedRun.java').write_text(patch(source.read_text(encoding='utf-8')),encoding='utf-8')
        shutil.copy2(Path(__file__).with_name('V011GuidedSuiteHarness.java'),src/'V011GuidedSuiteHarness.java')
        shutil.copy2(Path(__file__).with_name('V011Actuation.java'),src/'V011Actuation.java')
        core.write(root/'environment.json',{'version':'v011','reference_campaign':str(reference),
            'provengo_jar':str(jar),'jar_sha256':core.sha(jar),'python':sys.version,
            'java_source_sha256':core.sha(source),'java_source_normalized_sha256':SOURCE_SHA,
            'selection':'All existing fixed Java scenarios, original order; no sampling',
            'runtime_patch':'Native RTV evaluation, ActuationSummary checks, stop on failed actuation, cleanup',
            'patched_source_sha256':core.sha(src/'StrictGuidedRun.java'),
            'source_note':'Existing catalog includes previously sample-derived scenarios',
            'arms':ARMS,'case_timeout_seconds':args.case_timeout,'arm_timeout_seconds':args.arm_timeout})
        core.write(root/'input_hashes.json',{str(p.relative_to(root)):core.sha(p) for p in root.rglob('*') if p.is_file()})
        # Invoking the JDK compiler module also works when javac is not on PATH.
        compile_result=launch([args.java,'-m','jdk.compiler/com.sun.tools.javac.Main','-cp',jar,'-d',classes,
            src/'StrictGuidedRun.java',src/'V011GuidedSuiteHarness.java',src/'V011Actuation.java'],root,'compile',120)
        timing['compilation_seconds']=compile_result['wall_seconds']
        if compile_result['exit_code']:raise RuntimeError('Java compilation failed: inspect compile.log; use a JDK matching Provengo')
        cp=str(classes)+os.pathsep+str(jar)
        listing=launch([args.java,'-cp',cp,'V011GuidedSuiteHarness','--list'],root,'catalog',60)
        if listing['exit_code'] or 'SCENARIO_COUNT=542' not in (root/'catalog.log').read_text(errors='replace'):
            raise RuntimeError('Expected the frozen catalog of 542 scenarios')
        # Separate infrastructure checks; these do not enter the fixed catalog's score or time.
        preflight_started=time.perf_counter()
        for name,negative in [('preflight-positive',False),('preflight-wrong-status',True)]:
            folder=root/name;folder.mkdir();model=root/'model'
            if negative:
                model=root/'preflight-negative-model'
                shutil.copytree(root/'model',model)
                interface=model/'spec/js/interfaces.library.js'
                text=interface.read_text(encoding='utf-8')
                if 'expectedResponseCodes: [201]' not in text:raise RuntimeError('Negative self-check anchor changed')
                interface.write_text(text.replace('expectedResponseCodes: [201]','expectedResponseCodes: [202]'),encoding='utf-8')
            with runtime.Service(root,folder,'none'):
                check=launch([args.java,'-cp',cp,'V011GuidedSuiteHarness',model,folder/'native.jsonl',args.case_timeout,'--smoke'],
                    folder,'java-suite',args.case_timeout+30)
            native=rows(folder/'native.jsonl');http=rows(folder/'http.jsonl')
            if check['exit_code'] or len(native)!=1:raise RuntimeError('Incomplete transport self-check: '+name)
            if negative:
                native_log=(folder/'java-suite.log').read_text(encoding='utf-8',errors='replace')
                if native[0]['native_pass'] or not native[0]['actuator_errors'] or 'unexpected response code' not in native_log:
                    raise RuntimeError('Native HTTP-status assertion self-check failed')
            else:
                loan=[r for r in http if r['role']=='tool' and r['method']=='POST' and r['path'].split('?')[0]=='/loans' and r['status']==201]
                if not native[0]['native_pass'] or len(loan)!=1 or any(r['role'] in ('verdict','observer_error') for r in http):
                    raise RuntimeError('Native RTV/loan self-check failed')
                actual=loan[0]['response']
                if str(loan[0]['request'].get('userId'))!=str(actual.get('userId')) or str(loan[0]['request'].get('bookId'))!=str(actual.get('bookId')):
                    raise RuntimeError('Loan request/response identity mismatch')
            core.write(folder/'self_check.json',{'passed':True,'negative_control':negative})
        timing['transport_preflight_seconds']=time.perf_counter()-preflight_started
        core.write(root/'preflight_completed.json',{'positive_loan_created':True,'wrong_status_failed_natively':True})
        summary={};control={}

        for arm,bugs in ARMS.items():
            folder=root/arm;folder.mkdir();print('START JAVA '+arm+' BUGS='+bugs,flush=True)
            with runtime.Service(root,folder,bugs):
                outcome=launch([args.java,'-cp',cp,'V011GuidedSuiteHarness',root/'model',folder/'native.jsonl',args.case_timeout],
                    folder,'java-suite',args.arm_timeout)
            timing[arm+'_seconds']=outcome['wall_seconds']
            native=rows(folder/'native.jsonl')
            if len(native)!=542 or outcome['exit_code']:
                raise RuntimeError('Incomplete '+arm+'; evidence preserved; do not score incomplete suites')
            http=rows(folder/'http.jsonl')
            if any(r['role']=='observer_error' for r in http):
                raise RuntimeError('Observer error in '+arm+'; inspect evidence before scoring')
            boundaries=[r for r in http if r['role']=='boundary']
            if len(boundaries)!=542 or any(not r.get('empty_verified') for r in boundaries):
                raise RuntimeError('Missing verified empty case boundaries in '+arm)
            tool_rows=[r for r in http if r['role']=='tool']
            if any('@{' in json.dumps(r.get('request')) for r in tool_rows):
                raise RuntimeError('Unresolved request-body RTV in '+arm+'; execution invalid')
            diagnostic=previous.counts(folder)
            transport_counts={'successful_loans':sum(r['method']=='POST' and r['path'].split('?')[0]=='/loans' and r['status']==201 for r in tool_rows),
                'successful_holds':sum(r['method']=='POST' and r['path'].split('?')[0]=='/holds' and r['status']==201 for r in tool_rows),
                'get_requests':sum(r['method']=='GET' for r in tool_rows),'delete_requests':sum(r['method']=='DELETE' for r in tool_rows)}
            if arm=='control' and not transport_counts['successful_loans']:
                raise RuntimeError('Control catalog created no real loans; do not score')
            if arm=='control':control={str(r['case']):r for r in native}
            eligible={case for case,r in control.items() if r['native_pass'] and case not in summary.get('control',{}).get('observer',{}).get('clean_candidate_cases',{})}
            failed=[str(r['case']) for r in native if not r['native_pass']]
            candidates=diagnostic['clean_candidate_cases']
            summary[arm]={'bugs':bugs,'scenario_count':len(native),'native_failures':failed,'transport_counts':transport_counts,
                'control_eligible_cases':sorted(eligible,key=int),'observer':diagnostic,
                'native_failures_on_control_eligible_cases':[c for c in failed if c in eligible],
                'native_failures_with_clean_observer_candidate':{c:candidates[c] for c in failed if c in eligible and c in candidates},
                'scoring_note':'Native failure and observer candidate are separate evidence; inspect logs before assigning unique seeded bugs'}
            core.write(root/'results.json',summary)
            print('END JAVA '+arm+' NATIVE_FAILURES='+str(len(failed)),flush=True)
        timing['mutant_two_arms_seconds']=sum(timing[a+'_seconds'] for a in previous.ARMS)
        complete=True;core.write(root/'completed.json',{'complete':True,'sample_created':False,'scenario_count':542})
    finally:
        timing['total_before_packaging_seconds']=time.perf_counter()-started
        core.write(root/'timings.json',timing)
        archive=root.with_name(root.name+'-review.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob('*'):
                if p.is_file() and not {'products','__pycache__','classes'}.intersection(p.relative_to(root).parts):z.write(p,p.relative_to(root))
        print('V011_TIMINGS '+json.dumps(timing),flush=True)
        print('V011_REVIEW_ZIP '+str(archive),flush=True)
        if complete:print('JAVA_FIXED_V011_COMPLETE',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference-campaign',type=Path,required=True)
    parser.add_argument('--jar',type=Path)
    parser.add_argument('--java',default='java')
    parser.add_argument('--case-timeout',type=int,default=120)
    parser.add_argument('--arm-timeout',type=int,default=7200)
    args=parser.parse_args()
    if args.case_timeout<=0 or args.arm_timeout<=0:parser.error('Timeouts must be positive')
    main(args)
