"""Acceptance harness for preserved cycle-5 reproduction pairs, not discovery rules."""
import sys,json,io,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from contract_context import derive
from traffic import normalize
from judge import analyze
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--evidence-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
if args.output.exists():raise SystemExit('Use a new output file')
root=args.evidence_root;reports=[]
for system,file in [('homebox','homebox-swagger.json'),('paperless','paperless-openapi.json')]:
 p=root/('repro-c5-'+system+'.json');raw=p.read_bytes();data=json.loads(raw);cb=(root/'config'/file).read_bytes();context=derive(json.loads(cb),hashlib.sha256(cb).hexdigest());rows=[]
 for i,case in enumerate(data['cases']):
  for side in ['control','test']:
   r=case[side];method,path,body=r['request'];answer=r['answer']
   try:answer=json.loads(answer)
   except ValueError:pass
   rows.append(normalize({'method':method,'path':path,'input':body,'status':r['status'],'response':answer},{'sha256':hashlib.sha256(raw).hexdigest(),'pointer':f'/cases/{i}/{side}'}))
 out=io.StringIO();a=analyze(rows,context,out,capture={})
 reports.append({'system':system,'source_sha256':hashlib.sha256(raw).hexdigest(),'contract_sha256':hashlib.sha256(cb).hexdigest(),'pairs':len(data['cases']),'exchanges':a['exchanges'],'findings':a['finding_partitions'],'control_5xx':sum(c['control']['status']>=500 for c in data['cases']),'test_5xx':sum(c['test']['status']>=500 for c in data['cases']),'producer_verdicts_used':False})
assert all(r['control_5xx']==0 and r['test_5xx']==r['pairs'] and r['findings']['server_5xx']['occurrences']==r['pairs'] for r in reports)
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'status':'PASS','source_repository':'weissye/vikunja_study','source_commit':'dc79b7a','results':reports,'scope':'preserved direct reproduction pairs; not complete story packages; no new SUT requests'},indent=2)+'\n');print('PASS',sum(r['pairs'] for r in reports),'500 witnesses and non-500 controls')
