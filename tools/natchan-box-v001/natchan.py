"""Stable offline pipeline interface over the existing Natchan analyzers (Python 3.10+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT.parent
VERSION = 'natchan-box/1.0.0'
ADAPTERS = {'provengo-native-lifecycle', 'gitea-native-tools', 'historical-corpus', 'normalized-observations'}
DEPENDENCIES = ['natchan-v003', 'natchan-v004', 'natchan-v005', 'natchan-v006', 'natchan-v008', 'natchan-v011', 'natchan-v014', 'natchan-v015', 'natchan-v016', ROOT.name]

class InputError(ValueError):
    pass
class Unsupported(InputError):
    pass
class EngineError(RuntimeError):
    pass

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''): h.update(chunk)
    return h.hexdigest()

def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise InputError('Duplicate JSON key: ' + key)
        out[key] = value
    return out

def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique)
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise InputError('Cannot read JSON: ' + str(path)) from e

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def obj(value, allowed, required, label):
    if not isinstance(value, dict): raise InputError(label + ' must be an object')
    if set(value) - set(allowed): raise InputError(label + ': unknown fields ' + str(sorted(set(value)-set(allowed))))
    if set(required) - set(value): raise InputError(label + ': missing fields ' + str(sorted(set(required)-set(value))))

def path_at(base, value):
    if not isinstance(value, str) or not value.strip(): raise InputError('Path must be a nonempty string')
    return (base / value).resolve()

def validate(request, base):
    obj(request, ['schema_version','run','evidence','configuration'], ['schema_version','run','evidence'], 'request')
    if request['schema_version'] != 'natchan-request/1': raise Unsupported('Unsupported request schema')
    run=request['run'];obj(run,['id','tool','product','product_version'],['id','tool','product','product_version'],'run')
    if any(not isinstance(v,str) or not v.strip() for v in run.values()): raise InputError('Run metadata must be nonempty strings')
    ev=request['evidence'];obj(ev,['adapter','archive','directory','manifest','observations','root','sha256'],['adapter'],'evidence')
    adapter=ev['adapter']
    if adapter not in ADAPTERS: raise Unsupported('Unsupported adapter: '+str(adapter))
    keys=[k for k in ['archive','directory','manifest','observations'] if k in ev]
    if len(keys)!=1: raise InputError('Exactly one evidence location is required')
    key=keys[0]
    supported={'provengo-native-lifecycle':['archive'],'gitea-native-tools':['archive','directory'],'historical-corpus':['manifest'],'normalized-observations':['observations']}
    if key not in supported[adapter]: raise Unsupported('Evidence location incompatible with adapter')
    if adapter=='provengo-native-lifecycle' and (run['tool']!='provengo' or run['product']!='gitea'): raise Unsupported('Native lifecycle adapter supports Gitea/Provengo only')
    if adapter=='gitea-native-tools' and (run['tool'] not in ['evomaster','schemathesis','mixed'] or run['product']!='gitea'): raise Unsupported('Native-tools adapter supports Gitea EvoMaster/Schemathesis only')
    if 'root' in ev and adapter!='historical-corpus': raise InputError('root is only valid for historical-corpus')
    if adapter=='historical-corpus' and 'root' not in ev: raise InputError('Historical corpus requires evidence.root')
    target=path_at(base,ev[key])
    if not (target.is_dir() if key=='directory' else target.is_file()): raise InputError('Evidence location not found: '+str(target))
    if 'sha256' in ev:
        h=ev['sha256']
        if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h): raise InputError('sha256 must be 64 lowercase hexadecimal characters')
        if not target.is_file() or sha(target)!=h: raise InputError('Evidence SHA256 mismatch')
    cfg=request.get('configuration',{});obj(cfg,['product_profile','catalog_set','profile','catalogs'],[],'configuration')
    if cfg.get('catalog_set','research-catalogs-v014')!='research-catalogs-v014': raise Unsupported('Unknown catalog set')
    expected='gitea-lifecycle' if adapter=='provengo-native-lifecycle' else 'adapter-default'
    if cfg.get('product_profile',expected)!=expected: raise Unsupported('Unsupported product profile for adapter')
    if 'profile' in cfg and adapter!='provengo-native-lifecycle': raise Unsupported('Explicit profile supported only by native lifecycle adapter')
    if 'catalogs' in cfg and adapter not in ['provengo-native-lifecycle','normalized-observations']: raise Unsupported('Explicit catalogs unsupported by this adapter')
    for k in ['profile','catalogs']:
        if k in cfg:
            p=path_at(base,cfg[k])
            if not (p.is_dir() if k=='catalogs' else p.is_file()): raise InputError('Configuration location not found: '+str(p))
    return adapter,key,target,cfg

def inventory(path):
    paths=[path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts)
    return [{'path':str(p.resolve()),'sha256':sha(p)} for p in paths]

def unpack(archive, target):
    """Bounded extraction; normalize Windows separators, reject traversal/collisions/links."""
    seen=set();budget=0
    try:
        with zipfile.ZipFile(archive) as z:
            if len(z.infolist())>20000: raise InputError('Archive member limit exceeded')
            for info in z.infolist():
                name=info.filename.replace('\\','/')
                parts=name.split('/')
                if name.startswith('/') or any(p in ['..'] or ':' in p for p in parts): raise InputError('Unsafe ZIP member')
                dest=target.joinpath(*parts).resolve()
                if not dest.is_relative_to(target.resolve()): raise InputError('Unsafe ZIP member')
                if stat.S_ISLNK(info.external_attr >> 16): raise InputError('ZIP symlinks unsupported')
                canonical=str(dest).casefold()
                if canonical in seen: raise InputError('Duplicate ZIP member')
                seen.add(canonical);budget+=info.file_size
                if budget>1000000000: raise InputError('Expanded ZIP budget exceeded')
                if info.is_dir(): dest.mkdir(parents=True,exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(info) as src,dest.open('wb') as out: shutil.copyfileobj(src,out)
    except (zipfile.BadZipFile,RuntimeError) as e: raise InputError('Invalid ZIP archive') from e

def launch(command):
    p=subprocess.run([sys.executable,*map(str,command)],capture_output=True,text=True,encoding='utf-8',errors='replace',env=dict(os.environ,PYTHONUTF8='1'))
    if p.returncode:
        # Keep diagnostic details, but never convert engine errors into a clean zero.
        raise EngineError(p.stderr[-5000:] or p.stdout[-5000:] or 'Engine returned '+str(p.returncode))

def execute(adapter,key,target,cfg,base,work):
    output=work/'engine';catalogs=path_at(base,cfg['catalogs']) if 'catalogs' in cfg else TOOLS/'natchan-v014/catalogs'
    if adapter=='provengo-native-lifecycle':
        profile=path_at(base,cfg['profile']) if 'profile' in cfg else TOOLS/'natchan-v016/profiles/gitea-lifecycle.json'
        try:
            with zipfile.ZipFile(target) as z:
                if 'native.log' not in z.namelist(): raise InputError('native.log missing from archive root')
        except zipfile.BadZipFile as e: raise InputError('Invalid ZIP archive') from e
        launch([TOOLS/'natchan-v016/analyze.py','--input',target,'--output',output,'--profile',profile,'--catalogs',catalogs])
    elif adapter=='gitea-native-tools':
        folder=target
        if key=='archive':
            folder=work/'extracted';folder.mkdir();unpack(target,folder)
        if not any(p.is_dir() and (p/'run-meta.json').exists() for p in folder.iterdir()): raise InputError('Expected run directories containing run-meta.json directly inside evidence directory/archive')
        launch([TOOLS/'natchan-v015/native_analysis.py','--input',folder,'--output',output])
    elif adapter=='historical-corpus':
        manifest=read(target)
        if manifest.get('schema_version')!='natchan-corpus/1' or not manifest.get('datasets'): raise InputError('Expected nonempty natchan-corpus/1 manifest')
        launch([TOOLS/'natchan-v014/run.py','--manifest',target,'--root',path_at(base,cfg['_evidence_root']),'--output',output])
    else:
        document=read(target)
        if document.get('schema_version')!='natchan-observations/1' or not isinstance(document.get('observations'),list) or not document['observations']: raise InputError('Expected nonempty natchan-observations/1 input')
        output.mkdir()
        launch([TOOLS/'natchan-v003/classifier.py','--input',target,'--output',output/'analysis.json','--catalogs',catalogs])
    return read(output/'analysis.json'),output

def metadata(report, adapter):
    common=report.get('common_analysis',report)
    values=common.get('observations',[])
    rows=[(o.get('product'),o.get('product_version'),o.get('tool')) for o in values]
    if adapter=='gitea-native-tools':rows += [('gitea',r.get('version'),r.get('tool')) for r in report['runs']]
    elif adapter=='historical-corpus':rows += [(r.get('product'),r.get('version'),r.get('tool')) for r in report.get('runs',[])]
    return rows

def normalized(report, adapter):
    common=report.get('common_analysis',report)
    index={o['id']:o for o in common.get('observations',[])}
    grouped={}
    for a in common.get('assessments',[]):
        if a['status']!='matched':continue
        oid=a['observation_id'];o=index[oid]
        item=grouped.setdefault(oid,dict(occurrence_id=oid,evidence_tier=o.get('evidence_tier','recomputed_observation'),source=o['source'],product=o.get('product'),product_version=o.get('product_version'),tool=o.get('tool'),run_id=o.get('run_id'),tags=[],known_bugs=[],witnesses=o.get('witnesses',[]),checks=[],needs_human=True,root_cause_identity_proven=False))
        item['known_bugs' if a.get('kind')=='known_bug' else 'tags'].append(a['catalog_id'])
        item['checks'].append(a)
        item.setdefault('severity_suggestions',{})[a['catalog_id']]=a.get('suggested_severity','requires_context')
    # Native adapter includes general error/state tags even when no catalog rule matches.
    for f in report.get('findings',[]) if adapter=='provengo-native-lifecycle' else []:
        item=grouped.setdefault(f['occurrence_id'],dict(f,evidence_tier='raw_native_http'))
        item['tags']=sorted(set(item.get('tags',[])+f['tags']));item['known_bugs']=sorted(set(item.get('known_bugs',[])+f['known_bugs']))
    # Log signatures remain separate occurrences; no fabricated causal HTTP join.
    if adapter=='gitea-native-tools':
        for run in report['runs']:
            for f in run['signatures']['findings']:
                s=f['source'];oid='log-'+hashlib.sha256(json.dumps([s['sha256'],s['record']],sort_keys=True).encode()).hexdigest()[:28]
                item=grouped.setdefault(oid,dict(occurrence_id=oid,evidence_tier='server_log_signature',source=s,product='gitea',product_version=run['version'],tool=run['tool'],run_id=run['run_id'],tags=[],known_bugs=[],checks=[],witnesses=[],needs_human=True,root_cause_identity_proven=False,causal_join=False))
                item['tags'].append(f['signature_id']);item['checks'].append(f)
    for f in grouped.values():
        f['tags']=sorted(set(f['tags']));f['known_bugs']=sorted(set(f['known_bugs']))
    return sorted(grouped.values(),key=lambda f:f['occurrence_id'])

def coverage(report,adapter,target):
    gaps=[];common=report.get('common_analysis',report)
    if not common.get('observations'):gaps.append({'code':'NO_NORMALIZED_OBSERVATIONS'})
    gaps += [{'code':'UNKNOWN_EVIDENCE','detail':x} for x in common.get('unknown_evidence',[])]
    gaps += [{'code':'RULE_NOT_EVALUABLE','detail':x} for x in common.get('rule_coverage',[]) if str(x.get('status','')).startswith('not_evaluable')]
    if adapter=='provengo-native-lifecycle':
        with zipfile.ZipFile(target) as z:has_server='sut.log' in z.namelist() and bool(z.read('sut.log').strip())
        if not has_server:gaps.append({'code':'SERVER_LOG_MISSING','affects':'server-error correlation and exact known-bug matching'})
    if adapter=='gitea-native-tools':
        for r in report['runs']:
            if not all(r['metadata_checks'].values()):raise InputError('Native metadata counters disagree with raw evidence: '+r['run_id'])
            state=r['lifecycle']
            if r['tool']=='evomaster' and state.get('native_fault_count') is None:gaps.append({'code':'NATIVE_FAULT_COUNT_UNKNOWN','run':r['run_id']})
            if state.get('process_status') in ['failed','unknown_or_incomplete']:gaps.append({'code':'TOOL_RUN_INCOMPLETE','run':r['run_id']})
    return dict(schema_version='natchan-coverage/1',scope=adapter,scope_is_limited=True,gaps=gaps,
        underlying_rule_coverage=common.get('rule_coverage',[]),
        unknown_evidence=common.get('unknown_evidence',[]),
        limitations=['COMPLETE means successful processing within this adapter scope, not complete product or bug coverage.','Missing evidence and unmatched known signatures never prove product correctness.','Imported facts retain the legacy classifier trust policy; this wrapper does not verify an arbitrary producer.'])

def report_md(result,findings,cov):
    lines=['# Natchan pipeline report','','Processing: '+result['status'],'Run: '+str((result.get('run') or {}).get('id')),'Adapter: '+str(result.get('adapter')),'',
        'Counts describe evidence occurrences, not independent bugs. Log signatures are separate from HTTP occurrences.','',
        '| Occurrence | Evidence tier | Tags | Known bugs |','|---|---|---|---|']
    def cell(s):return str(s).replace('|','\\|').replace('\n',' ')
    for f in findings:lines.append('| '+' | '.join(map(cell,[f['occurrence_id'],f['evidence_tier'],', '.join(f['tags']),', '.join(f['known_bugs']) or 'unmatched']))+' |')
    lines += ['','## Coverage gaps','',*['- '+json.dumps(g,ensure_ascii=False) for g in cov.get('gaps',[])],'','## Limits','',*['- '+s for s in cov.get('limitations',[])]]
    return '\n'.join(lines)+'\n'

def run(request_path, output):
    request_path=request_path.resolve();output=output.resolve()
    # Reserve only a fresh destination; never overwrite an earlier result or the request.
    if output.exists():raise InputError('Output already exists')
    if request_path.is_relative_to(output):raise InputError('Output contains request')
    # Reject an output nested in raw input before creating any files there.
    try:
        pre=read(request_path)
        location=pre.get('evidence',{}).get('directory')
        if location and output.is_relative_to(path_at(request_path.parent,location)):
            raise InputError('Output must be outside the input directory')
    except (AttributeError, TypeError):
        pass
    except InputError as e:
        if str(e)=='Output must be outside the input directory':raise
    output.mkdir(parents=True)
    result=dict(schema_version='natchan-result/1',wrapper_version=VERSION,status='FAILED',exit_code=4,run=None,adapter=None,new_sut_requests=0,artifacts={})
    findings=[];cov=dict(schema_version='natchan-coverage/1',gaps=[],scope_is_limited=True);diagnostics=[];prov=dict(schema_version='natchan-provenance/1',wrapper_version=VERSION,python=sys.version,inputs=[],code=[],new_sut_requests=0)
    try:
        request=read(request_path);base=request_path.parent
        adapter,key,target,cfg=validate(request,base);result.update(run=request['run'],adapter=adapter)
        if target.is_dir() and output.is_relative_to(target):raise InputError('Output must be outside the input directory')
        inputs=inventory(request_path)+inventory(target)
        for k in ['catalogs','profile']:
            if k in cfg:inputs+=inventory(path_at(base,cfg[k]))
        if adapter=='historical-corpus':cfg=dict(cfg,_evidence_root=request['evidence']['root'])
        prov['inputs']=inputs
        prov['code']=[entry for name in DEPENDENCIES if (TOOLS/name).exists() for entry in inventory(TOOLS/name)]
        prov['request']=request;prov['engine_versions']={'native':'v016','native_tools':'v015','corpus':'v014','classifier':'v003'}
        with tempfile.TemporaryDirectory(prefix='natchan-box-') as temp:
            report,engine_dir=execute(adapter,key,target,cfg,base,Path(temp))
            for product,version,tool in metadata(report,adapter):
                for field,actual in [('product',product),('product_version',version),('tool',tool)]:
                    expected=request['run'][field]
                    if actual is not None and expected!='mixed' and actual!=expected:raise InputError('Declared '+field+' disagrees with observed evidence')
            if any(sha(Path(x['path']))!=x['sha256'] for x in inputs):raise InputError('Input changed during analysis')
            if inventory(target)!=[x for x in inputs if x['path']==str(target) or (target.is_dir() and Path(x['path']).is_relative_to(target))]:
                raise InputError('Evidence membership changed during analysis')
            findings=normalized(report,adapter);cov=coverage(report,adapter,target)
            if adapter=='gitea-native-tools' and key=='archive':
                prov['source_locations']={'temporary_prefix':str(Path(temp)/'extracted'),'archive':str(target),'archive_sha256':sha(target),'rule':'Paths below temporary_prefix map to slash-normalized ZIP member names. Member bytes and hashes are preserved; no extracted evidence remains after this invocation.'}
            # Preserve the legacy analysis without rewriting its facts or findings.
            shutil.copy2(engine_dir/'analysis.json',output/'analysis.json')
            for name in ['report.md','report.html','report-view.json']:
                if (engine_dir/name).exists():shutil.copy2(engine_dir/name,output/('engine-'+name))
            # Historical gateways list the actual raw inputs they opened.
            prov['engine_input_inventory']=report.get('input_inventory',[])
            prov['catalogs']=report.get('catalogs',report.get('common_analysis',{}).get('catalogs',[]))
        result.update(status='PARTIAL' if cov['gaps'] else 'COMPLETE',exit_code=0,
            counts={'finding_occurrences':len(findings),'known_bug_occurrences':sum(bool(f['known_bugs']) for f in findings),'known_bug_ids':sorted({b for f in findings for b in f['known_bugs']}),'log_signature_occurrences':sum(f['evidence_tier']=='server_log_signature' for f in findings)},
            observation='Finding counts are evidence occurrences, not distinct root causes or all tested bugs.')
    except Unsupported as e:result['exit_code']=3;diagnostics.append(dict(code='UNSUPPORTED_INPUT',message=str(e)))
    except (InputError,OSError,zipfile.BadZipFile) as e:result['exit_code']=2;diagnostics.append(dict(code='INVALID_INPUT',message=str(e)))
    except Exception as e:result['exit_code']=4;diagnostics.append(dict(code='ENGINE_ERROR',message=str(e),exception_type=type(e).__name__))
    if result['exit_code']:
        findings=[];cov['gaps'].append({'code':'ANALYSIS_FAILED','not_evaluated':True})
    write(output/'findings.json',{'schema_version':'natchan-findings/1','findings':findings})
    write(output/'coverage.json',cov);write(output/'provenance.json',prov)
    write(output/'diagnostics.json',{'schema_version':'natchan-diagnostics/1','items':diagnostics})
    (output/'report.md').write_text(report_md(result,findings,cov),encoding='utf-8')
    result['artifacts']={p.name:{'path':p.name,'sha256':sha(p)} for p in sorted(output.iterdir()) if p.is_file() and p.name!='result.json'}
    write(output/'result.json',result) # Commit marker: consumers read this file last.
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:result=run(a.request,a.output)
    except (InputError,OSError) as e:print('NATCHAN_BOX_INVALID_OUTPUT '+str(e),file=sys.stderr);return 2
    print('NATCHAN_BOX '+json.dumps({'status':result['status'],'exit_code':result['exit_code'],'output':str(a.output.resolve())}))
    return result['exit_code']

if __name__=='__main__':raise SystemExit(main())
