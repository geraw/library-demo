import sys,json,hashlib,io,collections
from pathlib import Path
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--evidence-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
evidence_root=args.evidence_root
engine=Path(__file__).resolve().parent
sys.path.insert(0,str(engine))
from contract_context import derive
from traffic import normalize
from judge import analyze
contracts={'mealie':'mealie-contract.json','wger':'cycles/1-wger/config/contract.json','tandoor':'cycles/2-tandoor/config/tandoor-openapi.2.7.2.json','kimai':'cycles/3-kimai/config/kimai-openapi.2.70.0.json','dtrack':'cycles/4-dtrack/config/dtrack-openapi.5.2.1.json','vikunja':'toolkit/v2.7/configs/vikunja/contract.json','gitea':'toolkit/v2.7/configs/gitea/contract.json'}
allout=[]
for path in sorted((evidence_root/'results').glob('*/gateway-journal.jsonl')):
 system=path.parent.name.split('-')[0]; raw=path.read_bytes(); rows=[json.loads(x) for x in raw.splitlines() if x.strip()]
 result=json.loads((path.parent/'result_stories.json').read_text()); physical=[(i,r) for i,r in enumerate(rows,1) if r.get('category')=='research' and not r.get('path','').startswith('/__sbt/')]
 out={'system':system,'run':path.parent.name,'repository_path':str(path.relative_to(evidence_root)),'fetched_sha256':hashlib.sha256(raw).hexdigest(),'journal_records':len(rows),'product_http':len(physical),'observed_5xx':sum(500<=r.get('status',0)<600 for _,r in physical),'producer_story_statuses':dict(collections.Counter(s.get('status') for s in result.get('stories',[]))),'producer_failed_checks':sum(len(s.get('failed_checks',[])) for s in result.get('stories',[])),'producer_contract_sha256':result.get('contract_sha256')}
 if system not in contracts:
  out['blocked']='CONTRACT_NOT_LOCATED';allout.append(out);continue
 cp=evidence_root/contracts[system];cb=cp.read_bytes();doc=json.loads(cb)
 out['contract_hash_matches_run']=any(hashlib.sha256(v).hexdigest()==result.get('contract_sha256') for v in (cb,cb.rstrip(b'\n')));out['contract_path']=contracts[system];out['contract_info']=doc.get('info',{});out['contract_canonical_sha256']=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 try:
  context=derive(doc,hashlib.sha256(cb).hexdigest()); normalized=[]; errors=[]
  for i,r in physical:
   clean={k:r[k] for k in ['method','path','status','input','response','t_utc'] if k in r}
   if r.get('session'):clean['actor']=r['session']
   if isinstance(clean.get('response'),str):
    try:clean['response']=json.loads(clean['response'])
    except ValueError:pass
   try:normalized.append(normalize(clean,{'path':out['repository_path'],'line':i,'sha256':out['fetched_sha256']}))
   except Exception as e:errors.append({'line':i,'error':str(e)})
  buf=io.StringIO();a=analyze(normalized,context,buf,capture={});out['analysis']=a;out['normalization_errors']=errors
 except Exception as e:out['blocked']=type(e).__name__+': '+str(e)
 allout.append(out)
output=args.output
if output.exists():raise SystemExit('Refusing to overwrite existing output')
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps({'source_commit':'d378389226c1af05e767ddb0db895fcc41bd368d','mode':'offline_existing_evidence_no_new_SUT_requests','capture_policy':'No isolation/completeness/epoch assertions fabricated','engine_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(engine.glob('*.py'))},'results':allout},indent=2))
for o in allout:print(o['system'],o['product_http'],o['observed_5xx'],o.get('blocked'),o.get('analysis',{}).get('finding_partitions'),o['producer_story_statuses'],o['producer_failed_checks'])
