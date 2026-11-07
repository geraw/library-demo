"""Recheck report corrections from original g005/v164 and baseline tool artifacts."""
from collections import Counter,defaultdict
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v005'))
import analyze_coverage as old

def sha(b):return hashlib.sha256(b).hexdigest()
def parsed(s):
 try:return json.loads(s) if isinstance(s,str) else s
 except ValueError:return None

def g005(folder):
 observations=[];limits=[]
 for path in sorted(folder.glob('review_g005_s*.zip')):
  with zipfile.ZipFile(path) as z:
   payload=z.read('gateway-journal.jsonl');rows=[json.loads(l) for l in payload.splitlines() if l.strip()];ir=json.loads(z.read('generated/contract-ir.json'))
  source=dict(archive=path.name,archive_sha256=sha(path.read_bytes()),journal_sha256=sha(payload))
  for i,r in enumerate(rows):
   if r.get('action')=='idem_write' and r.get('status')==409:
    first=next(((j,x) for j,x in reversed(list(enumerate(rows[:i]))) if x.get('action')=='idem_write' and x.get('case_id')==r.get('case_id')),None)
    before=next(((j,x) for j,x in reversed(list(enumerate(rows[:i]))) if x.get('action')=='idem_arm' and x.get('case_id')==r.get('case_id')),None)
    if not first or not before:continue
    j,a=first;k,b=before;pre=parsed(b.get('response'));post=parsed(a.get('response'));request=a.get('input')
    if not all(isinstance(x,dict) for x in (pre,post,request)):continue
    keys=[key for key,v in request.items() if v is not None and key!='content_version']
    intervening=any(x.get('method') in ('POST','PUT','PATCH','DELETE') and x.get('path')==a.get('path') for x in rows[k+1:i] if x is not a)
    qualified=(not intervening and bool(keys) and old.baseline.same(request,r.get('input')) and
               all(key in pre and old.baseline.same(pre[key],request[key]) for key in keys) and
               all(key in post and old.baseline.same(post[key],pre[key]) for key in keys) and
               request.get('content_version')==pre.get('content_version') and
               type(pre.get('content_version')) is int and post.get('content_version')==pre['content_version']+1 and
               a.get('status') in (200,201) and a.get('path')==r.get('path')==b.get('path') and
               'the issue is already changed' in str(r.get('response')))
    if qualified:observations.append(dict(id='GIT-O3',source=source,lines=[k+1,j+1,i+1],business_fields=keys,version_before=pre['content_version'],version_after=post['content_version'],statuses=[a['status'],r['status']],interpretation='optimistic concurrency observation; not automatically a bug'))
   if r.get('category')=='research' and r.get('status')==422 and 'MaxSize' in str(r.get('response')):
    context=old.baseline.gitea_context(r,ir);request=r.get('input') or {};logical=r.get('logical_id','');tail=re.split('_EDGEU?_',logical)
    if len(tail)!=2:continue
    field=next((key for key in sorted(request,key=len,reverse=True) if tail[1].startswith(key+'_')),None)
    schema=context['properties'].get(field)
    if not field or not isinstance(request[field],str) or not isinstance(schema,dict):continue
    if 'maxLength' not in schema:limits.append(dict(id='GIT-O4',source=source,line=i+1,entity=context['entity'],field=field,sent_length=len(request[field]),response=parsed(r['response']),maxLength_declared=False,exact_limit_verified=False))
 return dict(noop_version_observations=observations,undeclared_length_observations=limits)

def adjacency(path):
 result=[]
 with zipfile.ZipFile(path) as outer:
  middle=outer.read('v164-comment-create-20261018-153234.zip')
  with zipfile.ZipFile(io.BytesIO(middle)) as z:
   for seed in [1,2]:
    n=f'review_seed{seed}_run{seed}.zip';raw=z.read(n)
    with zipfile.ZipFile(io.BytesIO(raw)) as a:payload=a.read('gateway-journal.jsonl')
    rows=[json.loads(l) for l in payload.splitlines() if l.strip()];log=z.read(f'sut_locked_seed{seed}_run{seed}.txt').decode('utf-8-sig');links=old.scoped_lock_links(rows,log)
    for i,r in enumerate(rows):
     if r.get('action')!='adjacency_probe' or r.get('status')!=500:continue
     key=(r['method'],r['path'],500)
     matching=[l for l in log.splitlines() if f'method={key[0]} uri=/api/v1{key[1]} status=500 ' in l and 'database is locked' in l]
     clients=[x for x in rows if (x.get('method'),x.get('path'),x.get('status'))==key]
     result.append(dict(product='vikunja',seed=seed,line=i+1,method=r['method'],path=r['path'],case_id=r.get('case_id'),
       archive_sha256=sha(path.read_bytes()),journal_sha256=sha(payload),review_member=n,
       unique_log_match=i in links,matching_lock_lines=len(matching),matching_client_500s=len(clients),
       grouped_lock_evidence=bool(matching) and len(matching)==len(clients),
       limitation='Single-key class evidence does not establish trigger causality or a unique line assignment when repeated'))
 return result

def baselines(folder):
 result=[]
 for p in sorted(folder.glob('evomaster_rep*/report.json')):
  raw=p.read_bytes();r=json.loads(raw);faults=r['faults']['foundFaults'];codes=sorted({c['code'] for f in faults for c in f['faultCategories']})
  console=(p.parent/'tool-console.log').read_text(errors='replace');log=(p.parent/'sut-lock-context.log').read_text(errors='replace')
  locks=[line for line in log.splitlines() if 'status=500' in line and 'database is locked' in line]
  result.append(dict(tool='EvoMaster',run=p.parent.name,version=r['toolVersion'],report_sha256=sha(raw),native_fault_total_field=r['faults']['totalNumber'],native_fault_entries=len(faults),native_category_codes=codes,
       has_native_500_fault_code_100=100 in codes,lock_log_count=len(locks),lock_log_sha256=sha((p.parent/'sut-lock-context.log').read_bytes()),
       replay_500_became_401=bool(re.search(r'Different status code 401 returned from original 500',console)),
       limitation='Native aggregate count and entry count differ; neither is a known-business-bug count'))
 for p in sorted(folder.glob('schemathesis_rep*/junit*.xml')):
  raw=p.read_bytes();r=ET.fromstring(raw);case=next(c for c in r.iter('testcase') if c.get('name')=='PUT /labels');text='\n'.join(c.text or '' for c in case.findall('failure'))
  # Concrete response measurement from the exact native test, not a previous label.
  matches=re.findall(r'\[201\] Created:\s*`(\{[^`]+\})`',text);responses=[json.loads(x) for x in matches]
  label=next((x for x in responses if x.get('title')=='' and x.get('id') is not None),None)
  result.append(dict(tool='Schemathesis',run=p.parent.name,junit_sha256=sha(raw),native_failed_testcases=int(r.attrib['failures']),native_testcases=int(r.attrib['tests']),
       label_title_empty_201=label is not None,declared_minLength_1='"minLength": 1' in text,missing_body_reported='Invalid component: Missing request body' in text,
       known_signature='VIK-F02' if label is not None and '"minLength": 1' in text else None,
       evidence_tier='native response body and schema excerpt; no independent subsequent GET'))
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--g005',type=Path,required=True);p.add_argument('--v164',type=Path,required=True);p.add_argument('--baselines',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('Output exists')
 r=dict(schema_version='natchan-report-audit/1',g005=g005(a.g005),adjacency=adjacency(a.v164),baselines=baselines(a.baselines),new_sut_requests=0)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(dict(O3=len(r['g005']['noop_version_observations']),O4=len(r['g005']['undeclared_length_observations']),ADJ=len(r['adjacency']),baseline_runs=len(r['baselines']))))
