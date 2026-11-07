"""Read-only qualification of saved Mealie evidence. No HTTP or replay."""
import argparse,hashlib,io,json,zipfile
from pathlib import Path

def compare_owner_readbacks(before,action,after,order,names):
 reasons=[]
 b,a,f=names
 if any(n not in order for n in names) or not(order.index(b)<order.index(a)<order.index(f)):reasons.append('Observation order not established')
 if before.get('code')!=200 or after.get('code')!=200:reasons.append('Owner readback unsuccessful')
 left=before.get('body');right=after.get('body')
 if not isinstance(left,dict) or not isinstance(right,dict):return {'complete':False,'reasons':reasons+['Missing object readback']}
 if not left.get('id') or left.get('id')!=right.get('id'):reasons.append('Resource identity mismatch')
 if before.get('actor')!=after.get('actor'):reasons.append('Reader identity mismatch')
 keys=['id','userId','groupId','householdId']
 if any(left.get(k)!=right.get(k) for k in keys):reasons.append('Resource scope changed between observations')
 return {'complete':not reasons,'reasons':reasons,'response_code':action.get('code'),
   'different_actor':action.get('actor')!=before.get('actor'),
   'state_changed':left.get('listItems')!=right.get('listItems') or left.get('recipeReferences')!=right.get('recipeReferences'),
   'before_item_count':len(left.get('listItems',[])),'after_item_count':len(right.get('listItems',[]))}

def audit(path):
 raw=Path(path).read_bytes();outer=zipfile.ZipFile(io.BytesIO(raw))
 if outer.testzip() is not None:raise ValueError('Outer ZIP CRC failure')
 contract=json.loads(outer.read('model/mealie-openapi.v3.28.0.reviewed.json'))
 declared={m.upper()+' '+p:list(op.get('responses',{})) for p,item in contract['paths'].items() for m,op in item.items() if m in ['get','post','put','patch','delete']}
 runs=[];changes=[]
 for name in outer.namelist():
  if not name.endswith('campaign-original.zip'):continue
  nested=zipfile.ZipFile(io.BytesIO(outer.read(name)))
  if nested.testzip() is not None:raise ValueError('Campaign CRC failure')
  for file in nested.namelist():
   if '/result-' not in file or not file.endswith('.json'):continue
   result=json.loads(nested.read(file));receipt=result['runtime_receipt'];program=receipt['identity_program'];obs=program['observations'];order=program['order']
   failures=[{'code':v['code'],'contract_documented':str(v['code']) in declared.get(v.get('operation'),[])} for v in obs.values() if v.get('code',0)>=500]
   run={'case':result['case'],'sample':result['sample'],'responses':receipt['response_count'],'server_errors':failures}
   if result['case']=='household-controls':
    for actor,victim in [('a','b'),('b','a')]:
     keys=('list_before_'+victim,'other_list_add_'+actor,'owner_list_after_'+actor)
     if any(k not in obs for k in keys):raise ValueError('Missing saved owner observation')
     finding=compare_owner_readbacks(*(obs[k] for k in keys),order,keys)
     if not finding['complete']:raise ValueError(str(finding['reasons']))
     finding.update(case=result['case'],sample=result['sample']);changes.append(finding)
   runs.append(run)
 f4=sum(len(r['server_errors']) for r in runs if r['case'] in ('separate','reference-controls'))
 return {'status':'SAVED_EVIDENCE_AUDITED_NOT_REPLAYED','input_sha256':hashlib.sha256(raw).hexdigest(),
 'http_requests_sent':0,'native_provengo_executed_by_audit':False,'new_generator_f04_f05_reproduction_complete':False,
 'run_count':len(runs),'response_count':sum(r['responses'] for r in runs),'runs':runs,
 'F04':{'saved_server_error_manifestations':f4,'contract_classification':'documented response codes checked; no invented 403/404 expectation'},
 'F05':{'identity_bound_owner_comparisons':changes,'observed_changes_after_server_error':sum(c['state_changed'] and c['response_code']==500 and c['different_actor'] for c in changes)},
 'limits':['Analysis of original evidence only','No regenerated live F04/F05 execution','Observed change after failure is reported separately from permission policy','Full server atomicity and root cause are not established']}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archive',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();report=audit(a.archive);a.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print('SAVED_F04_F05_EVIDENCE_AUDIT_PASS; no HTTP, Provengo or Git changes');print('Report:',a.output)
