"""Offline g012 variant audit: preserved gateways, strict version catalogs, raw witnesses."""
import argparse
from collections import Counter,defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v005'))
import analyze_coverage as previous
from coverage_classifier import classify
from classifier import load_catalogs,match,derived
from tse_gateways import parsed

VERSION={'nightly':'29.0.0+dev-175-g33610142c3','postgres':'28.1.0'}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def checked(raw):
 z=zipfile.ZipFile(io.BytesIO(raw));infos=z.infolist()
 if len(infos)>20000 or len({i.filename for i in infos})!=len(infos) or sum(i.file_size for i in infos)>128*1024*1024:raise ValueError('Unsafe archive')
 return z

def analyze(path):
 outerraw=path.read_bytes();outer=checked(outerraw)
 allobs=[];runs=[];errors=[];oracle_counts=defaultdict(Counter);atomic=[];rt=[];native_failures=[];all_oracles=[]
 for name in sorted(n for n in outer.namelist() if n.startswith('review_') and n.endswith('.zip')):
  m=re.fullmatch(r'review_(nightly|postgres)_(g003|g009)_s([1-4])\.zip',name)
  if not m:raise ValueError('Unexpected run name')
  variant,model,seed=m[1],m[2],int(m[3]);raw=outer.read(name)
  with checked(raw) as z:
   journal=z.read('gateway-journal.jsonl');rows=[json.loads(l) for l in journal.decode('utf-8-sig').splitlines() if l.strip()]
   result=json.loads(z.read('result_'+model+'.json'));summary=json.loads(outer.read('result_'+variant+'_'+model+'_s'+str(seed)+'.json'))
   if result!=summary:raise ValueError('Inner and outer result disagree')
   if result['sut_version']!=VERSION[variant]:raise ValueError('Unexpected actual SUT version')
   ir=json.loads(z.read('generated/contract-ir.json'));log=z.read('sut.log').decode('utf-8-sig');native=z.read('native.log').decode('utf-8-sig')
   runid='g012-'+variant+'-'+model+'-s'+str(seed)
   source=dict(file=path.name,archive_sha256=digest(outerraw),member=name,inner_archive_sha256=digest(raw),journal_member='gateway-journal.jsonl',sha256=digest(journal))
   run=dict(id=runid,product='gitea',version=VERSION[variant],tool='provengo',seed=seed,source=source)
   observations,oracles=previous.baseline.gitea_observations(run,dict(records=rows,ir=ir,sut_log=log))
   previous.augment_gitea(observations,rows)
   research=[r for r in rows if r.get('category')=='research']
   failures=[o for o in observations if type(o['status']) is int and 500<=o['status']<=599]
   # The retained gateway's direct UTC/unique-time joins work on these logs.
   for o in failures:
    request=o.get('request');message=o.get('server_message','')
    cause=('postgres_nul' if 'invalid byte sequence for encoding' in message and '0x00' in message else
           'postgres_varchar_limit' if 'value too long for type character varying(255)' in message else
           o['facts'].get('correlated_error_family','unjoined'))
    nul_fields=[k for k,v in (request or {}).items() if isinstance(v,str) and '\x00' in v] if isinstance(request,dict) else []
    long_fields={k:len(v) for k,v in (request or {}).items() if isinstance(v,str) and len(v)>255} if isinstance(request,dict) else {}
    errors.append(dict(run_id=runid,variant=variant,model=model,seed=seed,record=o['source']['record'],entity=o['entity'],action=o['action'],method=o['method'],path=o['path'],cause=cause,nul_fields=nul_fields,long_fields=long_fields,log=message,source=o['source']))
   for i,row in enumerate(rows):
    cat=row.get('category')
    if cat not in (None,'research'):oracle_counts[(variant,model,cat)][row.get('verdict','no-verdict')]+=1
    if cat=='atomicity-check':
     states=row.get('fields',{});values=set(states.values())
     recomputed='partial' if {'applied','kept'}<=values else 'rolled_back' if values=={'kept'} else 'committed_despite_error' if values=={'applied'} else 'unknown'
     atomic.append(dict(run_id=runid,variant=variant,model=model,record=i,logical_id=row.get('logical_id'),fields=states,readback_status=row.get('readback_status'),recorded=row.get('verdict'),recomputed_from_field_measurements=recomputed,full_state_independently_verified=False))
   native_failure=re.findall(r'FAIL:.*|actual \d+, expected:.*',native)
   native_failures.append(dict(run_id=runid,messages=native_failure[-4:],success_marker='Test Result: SUCCESS' in native,exit=result.get('native_exit')))
   actual_requests=len(research)
   if result['requests']!=actual_requests or len(result['http_5xx'])!=len(failures):raise ValueError('Producer counts disagree with raw HTTP')
   if model=='g009' and (result['native_exit']!=1 or 'actual 500, expected: [200]' not in native):raise ValueError('Native failure evidence differs')
   counts={k:result.get(k) for k in result if k in ('status','native_exit','elapsed_seconds','elapsed_s','requests','http_requests')}
   # Inspect producer summary below; independent HTTP counts always prevail.
   runs.append(dict(id=runid,variant=variant,model=model,seed=seed,version=VERSION[variant],status=result['status'],native_exit=result.get('native_exit'),http_requests=actual_requests,http_5xx=len(failures),correlated_5xx=sum(bool(o.get('server_message')) for o in failures),duration=result.get('elapsed_s',result.get('elapsed_seconds')),native_success_marker='Test Result: SUCCESS' in native,ir_source_version=ir.get('source',{}).get('version'),source=source,producer_summary=counts))
   allobs+=observations;all_oracles+=oracles
 report=classify(allobs,ROOT.parent/'natchan-v009/catalogs')
 entries,_=load_catalogs(ROOT.parent/'natchan-v009/catalogs')
 # Nightly is outside catalog version support: preserve diagnostics separately.
 cross=defaultdict(set)
 for o in report['observations']:
  if o.get('product_version')!=VERSION['nightly']:continue
  facts=derived(o)
  for entry in entries:
   if entry['kind']=='known_bug' and entry['status']=='active' and entry['product']=='gitea' and all(match(facts,c) for c in entry['all']) and not any(match(facts,c) for c in entry['exclusions']):cross[entry['id']].add(o['id'])
 known_by_run=defaultdict(lambda:defaultdict(set))
 for a in report['assessments']:
  for bug in a.get('known_bugs',[]):known_by_run[a['run_id']][bug].add(a['observation_id'])
 for run in runs:run['strict_catalog_known_occurrences']={bug:len(ids) for bug,ids in known_by_run[run['id']].items()}
 report.update(input_sha256=digest(outerraw),runs=runs,error_evidence=errors,atomicity_field_measurements=atomic,native_results=native_failures,
  nightly_behavioral_analogs_outside_catalog_versions={bug:len(ids) for bug,ids in cross.items()},
  nightly_analog_note='Executable semantic predicates only; not version-qualified known-bug matches. Catalog was not expanded.',
  original_oracle_counts=[dict(variant=k[0],model=k[1],category=k[2],counts=dict(v)) for k,v in oracle_counts.items()],new_sut_requests=0)
 report['summary_by_cohort']=[dict(variant=v,model=m,runs=len(rr),http_requests=sum(r['http_requests'] for r in rr),http_5xx=sum(r['http_5xx'] for r in rr),correlated_5xx=sum(r['correlated_5xx'] for r in rr),native_statuses=dict(Counter(r['status'] for r in rr))) for v in VERSION for m in ['g003','g009'] if (rr:=[r for r in runs if r['variant']==v and r['model']==m])]
 return report


def compare_sqlite(report,path,baseline_root):
    outer=checked(path.read_bytes());pairs=[];cache={}
    for error in report['error_evidence']:
        if not error['cause'].startswith('postgres'):continue
        seed=error['seed']
        with checked(outer.read('review_postgres_g003_s'+str(seed)+'.zip')) as z:
            row=[json.loads(l) for l in z.read('gateway-journal.jsonl').splitlines() if l.strip()][error['record']]
        baseline=baseline_root/('review_g003_s'+str(seed)+'.zip')
        if seed not in cache:
            raw=baseline.read_bytes()
            with checked(raw) as z:
                result=json.loads(z.read('result_g003.json'))
                if result['sut_version']!='28.1.0':raise ValueError('SQLite baseline version differs')
                payload=z.read('gateway-journal.jsonl')
                cache[seed]=(digest(raw),digest(payload),[json.loads(l) for l in payload.splitlines() if l.strip()])
        archive_hash,journal_hash,rows=cache[seed]
        candidates=[(i,r) for i,r in enumerate(rows) if r.get('category')=='research' and all(previous.baseline.same(r.get(k),row.get(k)) for k in ['action','logical_id','method','input','session'])]
        pairs.append(dict(cause=error['cause'],seed=seed,logical_id=row.get('logical_id'),action=row.get('action'),pg_status=row['status'],pg_source=error['source'],sqlite_source=dict(file=str(baseline),sha256=archive_hash,journal_sha256=journal_hash),sqlite_matches=[dict(record=i,status=r['status']) for i,r in candidates],comparison='same seed/session/action/logical ID/method/request body; not a randomized isolated DB intervention'))
    return pairs

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sqlite-baseline-root',type=Path);a=p.parse_args()
 if a.output.exists():p.error('Output exists')
 r=analyze(a.input)
 if a.sqlite_baseline_root:r['sqlite_comparison']=compare_sqlite(r,a.input,a.sqlite_baseline_root)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r['summary_by_cohort'],indent=2));print('ANALYSIS_COMPLETE',a.output)
