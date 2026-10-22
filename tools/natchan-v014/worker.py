"""Raw artifact gateways for the common engine; isolated legacy module namespaces."""
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import zipfile
ROOT=Path(__file__).resolve().parent

def digest(raw):return hashlib.sha256(raw).hexdigest()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def obs(product,version,run,tool,source,facts,**extra):
 return dict(id=run+':'+str(source.get('record',0)),product=product,product_version=version,run_id=run,tool=tool,source=source,facts=facts,fact_basis='recomputed',producer='natchan-v014-raw-gateway',**extra)

def bundle(path,meta):
 if path.is_dir():
  parts=[bundle(p,meta) for p in sorted(path.glob('review*.zip'))]
  if not parts:raise ValueError('No original review ZIPs')
  return {key:[item for part in parts for item in part[key]] for key in ('observations','runs','original_oracles')}
 sys.path.insert(0,str(ROOT.parent/'natchan-v005'))
 import analyze_coverage as previous
 raw=path.read_bytes();out=[];runs=[];claims=[]
 def walk(payload,chain,depth=0,budget=None):
  if depth>5:raise ValueError('Nested archive depth >5')
  if budget is None:budget=[500_000_000]
  with previous.checked_zip(payload) as z:
   names=z.namelist()
   if 'gateway-journal.jsonl' not in names:
    for n in names:
     if n.endswith('.zip'):
      info=z.getinfo(n);budget[0]-=info.file_size
      if budget[0]<0:raise ValueError('Expanded archive budget exceeded')
      walk(z.read(n),chain+[n],depth+1,budget)
    return
   if 'generated/contract-ir.json' not in names:raise ValueError('Missing source IR')
   payload=z.read('gateway-journal.jsonl');rows=[json.loads(l) for l in payload.decode('utf-8-sig').splitlines() if l.strip()]
   resultnames=[n for n in names if n.startswith('result_') and n.endswith('.json')]
   if len(resultnames)!=1:raise ValueError('Expected one native run result')
   result=json.loads(z.read(resultnames[0]));ir=json.loads(z.read('generated/contract-ir.json'))
   version=result.get('sut_version');runid=meta['id']+':'+('/'.join(chain) or path.stem)
   if not version:raise ValueError('Actual SUT version missing')
   native=z.read('native.log').decode('utf-8-sig') if 'native.log' in names else ''
   tool='provengo' if 'INFO [RUN' in native else 'unqualified-producer'
   source=dict(file=str(path),archive_sha256=digest(raw),members=chain+['gateway-journal.jsonl'],sha256=digest(payload))
   run=dict(id=runid,product='gitea',version=version,tool=tool,seed=result.get('seed'),source=source)
   data=dict(records=rows,ir=ir,sut_log=z.read('sut.log').decode('utf-8-sig') if 'sut.log' in names else '')
   values,oracles=previous.baseline.gitea_observations(run,data);previous.augment_gitea(values,rows)
   from raw_sequences import augment as augment_raw_sequences
   augment_raw_sequences(values,rows,json.loads(z.read('generated/plan.json')) if 'generated/plan.json' in names else None)
   for o in values:
    f=o['facts'];req=o.get('request');message=o.get('server_message','')
    if isinstance(req,dict):
     f['nul_request_verified']=any(isinstance(v,str) and '\x00' in v for v in req.values())
     f['long_string_request_verified']=any(isinstance(v,str) and len(v)>255 for v in req.values())
     f['postgres_nul_error_correlated']=bool(o.get('correlated_log')) and 'invalid byte sequence for encoding' in message and '0x00' in message
     f['postgres_length_error_correlated']=bool(o.get('correlated_log')) and 'value too long for type character varying(255)' in message
     if o['entity']=='release' and isinstance(req.get('tag_name'),str):
      f['tag_name_length']=len(req['tag_name']);family=f.get('correlated_error_family')
      f['release_tag_error_context_verified']=family=='invalid_tag' or family=='git_ref_failure' and len(req['tag_name'])>=10000
   count=sum(r.get('category')=='research' for r in rows)
   if result.get('requests') is not None and result['requests']!=count:raise ValueError('Native/raw request count mismatch')
   terminal=next((o['source'] for o in reversed(values) if o.get('status')==500),None)
   runs.append(dict(last_http_500_source=terminal,id=runid,product='gitea',version=version,tool=tool,native_status=result.get('status'),native_exit=result.get('native_exit'),http_records=count,source=source))
   out.extend(values);claims.extend(oracles)
 walk(raw,[])
 return dict(observations=out,runs=runs,original_oracles=claims)

def audit_g005(folder,meta):
 m=module('audit_original',ROOT.parent/'natchan-v011/audit_report.py');r=m.g005(folder)
 out=[]
 for row in r['noop_version_observations']:
  source=dict(row['source'],sha256=row['source']['journal_sha256'],record=row['lines'][-1]-1,member='gateway-journal.jsonl',lines=row['lines'])
  out.append(obs('gitea','28.1.0',meta['id']+':'+row['source']['archive'],'provengo',source,
     dict(noop_content_version_advance=True,repeated_stale_version_rejected=True,version_before=row['version_before'],version_after=row['version_after'],business_fields=row['business_fields']),
     entity='issue',operation='update',status=409,evidence_tier='raw_before_write_repeat_sequence'))
 for row in r['undeclared_length_observations']:
  source=dict(row['source'],sha256=row['source']['journal_sha256'],record=row['line']-1,member='gateway-journal.jsonl')
  out.append(obs('gitea','28.1.0',meta['id']+':'+row['source']['archive'],'provengo',source,
    dict(restriction_observed=True,restriction_documented=False,sent_length=row['sent_length'],exact_boundary_measured=False),entity=row['entity'],field=row['field'],status=422,evidence_tier='raw_request_response_and_schema'))
 return dict(observations=out,runs=[],original_oracles=[])

def adjacency(path,meta):
 m=module('audit_original',ROOT.parent/'natchan-v011/audit_report.py');rows=m.adjacency(path);out=[]
 for row in rows:
  source=dict(file=str(path),sha256=row['journal_sha256'],archive_sha256=row['archive_sha256'],record=row['line']-1,members=['v164-comment-create-20261018-153234.zip',row['review_member'],'gateway-journal.jsonl'])
  out.append(obs('vikunja',meta.get('version'),meta['id']+':'+row['review_member'],'provengo',source,
    dict(adjacency_probe_observed=True,lock_class_evidence=row['grouped_lock_evidence'],unique_lock_line_match=row['unique_log_match'],matching_client_500s=row['matching_client_500s'],matching_lock_lines=row['matching_lock_lines'],causation_proven=False),
    status=500,method=row['method'],path=row['path'],evidence_tier='unique_scoped_log_join' if row['unique_log_match'] else 'scoped_repeated_key_class_evidence'))
 return dict(observations=out,runs=[],original_oracles=[])

def baseline_native(folder,meta):
 m=module('audit_original',ROOT.parent/'natchan-v011/audit_report.py');rows=m.baselines(folder);out=[];runs=[]
 for row in rows:
  run=meta['id']+':'+row['run'];tool=row['tool'].lower()
  facts={};version=meta.get('version')
  if row['tool']=='EvoMaster':
   sha=row['report_sha256'];facts.update(native_report_observed=True,native_fault_total_field=row['native_fault_total_field'],native_fault_entries=row['native_fault_entries'],native_categories=row['native_category_codes'],native_replay_status_drift=row['replay_500_became_401'],native_500_category_absent=not row['has_native_500_fault_code_100'],native_counter_mismatch=row['native_fault_total_field']!=row['native_fault_entries'])
   # Lock evidence comes from the original paired server context, not old summaries.
   context=folder/row['run']/'sut-lock-context.log';text=context.read_text(errors='replace');lines=[l for l in text.splitlines() if 'status=500' in l and 'database is locked' in l]
   for i,line in enumerate(lines):
    out.append(obs('vikunja',version,run,tool,dict(file=str(context),sha256=digest(context.read_bytes()),record=i),dict(lock_class_evidence=True),status=500,evidence_tier='retained_server_context_log'))
  else:
   sha=row['junit_sha256'];facts.update(native_response_empty_label=row['label_title_empty_201'],native_minlength_one=row['declared_minLength_1'],native_missing_body_reported=row['missing_body_reported'],native_testcases=row['native_testcases'],native_failed_testcases=row['native_failed_testcases'])
  out.append(obs('vikunja',version,run,tool,dict(file=str(folder/row['run']/('report.json' if row['tool']=='EvoMaster' else next((folder/row['run']).glob('junit*.xml')).name)),sha256=sha,record='native-report'),facts,evidence_tier='native_tool_report'))
  runs.append(dict(id=run,product='vikunja',version=version,tool=tool,native_evidence=row,http_records=None))
 return dict(observations=out,runs=runs,original_oracles=[])



def sequence_descriptors(result):
    """Adapt raw request pairs to facts; do not classify them in this gateway."""
    helper=module('raw_pair_gateway',ROOT.parent/'natchan-v008/family_audit.py')
    groups={};extra=[];coverage=[]
    for o in result['observations']:
        if o['product']!='gitea':continue
        src=o['source'];file=src.get('file')
        if not file or not Path(file).is_file():continue
        chain=src.get('members') or [src.get('member','gateway-journal.jsonl')]
        key=(file,tuple(chain))
        groups.setdefault(key,o)
    for (file,chain),context in groups.items():
        path=Path(file)
        if path.suffix=='.jsonl':payload=path.read_bytes()
        elif path.suffix=='.zip':
            payload=path.read_bytes()
            for name in chain:
                with zipfile.ZipFile(io.BytesIO(payload)) as z:payload=z.read(name)
        else:continue
        rows=[json.loads(l) for l in payload.splitlines() if l.strip()]
        value=helper.analyze_rows(rows,[])
        coverage.append(dict(sha256=digest(payload),counts=value['counts']))
        for row in value['observations']:
            if row['evidence_level']!='same-field-value-status-comparison':continue
            f=row['facts'];source=dict(context['source'],sha256=digest(payload),record=row['lines'][-1]-1,pair_lines=row['lines'])
            extra.append(obs('gitea',context.get('product_version'),context['run_id'],context.get('tool'),source,
                dict(status_pair_difference_observed=f['response_class_differs'],create_status=f['create_status'],update_status=f['update_status']),field=f['field'],evidence_tier='raw_same_field_value_pair_without_business_precondition_inference'))
    result['observations'].extend(extra);result['family_coverage']=coverage
    return result

def execute(task,root):
 kind=task['adapter']
 if kind=='coverage-v005':
  sys.path.insert(0,str(ROOT.parent/'natchan-v005'));import analyze_coverage as m
  result=m.run(json.loads((root/task['manifest']).read_text()),root/task['evidence_root'])
 elif kind=='cloud-v006':
  sys.path.insert(0,str(ROOT.parent/'natchan-v006'));import analyze_cloud_v006 as m
  result=m.analyze(json.loads((root/task['manifest']).read_text()),root/task['evidence_root'])
 elif kind=='gitea-review-bundle':result=bundle(root/task['path'],task)
 elif kind=='g005-sequence-rules':result=audit_g005(root/task['path'],task)
 elif kind=='vikunja-adj-records':
  sys.path.insert(0,str(ROOT.parent/'natchan-v005'));import analyze_coverage as previous
  result=adjacency(root/task['path'],task)
  contract=json.loads((root/task['contract']).read_text(encoding='utf-8-sig'))
  for seed in (1,2):
   chain=['v164-comment-create-20261018-153234.zip',f'review_seed{seed}_run{seed}.zip']
   spec=dict(id=task['id']+':v164-s'+str(seed),sha256=digest((root/task['path']).read_bytes()),version=task['version'],seed=seed,journal_members=chain+['gateway-journal.jsonl'],ir_members=chain+['generated/contract-ir.json'],paired_log_members=[chain[0],f'sut_locked_seed{seed}_run{seed}.txt'])
   values=previous.archive_observations(spec,root/task['path'],contract)
   result['observations'].extend(values);result['runs'].append(dict(id=spec['id'],product='vikunja',version=task['version'],tool='provengo',observed_rows=len(values)))
 elif kind=='baseline-native':result=baseline_native(root/task['path'],task)
 else:raise ValueError('Unsupported raw gateway '+kind)
 result=sequence_descriptors(result)
 return dict(observations=result.get('observations',[]),runs=result.get('runs',[]),original_oracles=result.get('original_oracles',[]),family_coverage=result.get('family_coverage',[]))

if __name__=='__main__':
 task=json.loads(sys.argv[1]);root=Path(sys.argv[2]).resolve();target=Path(sys.argv[3]);reads=set();enabled=True
 def hook(event,args):
  if event!='open' or not enabled or not isinstance(args[0],(str,bytes)):return
  name=Path(args[0]).resolve();mode=args[1]
  if isinstance(mode,str) and any(c in mode for c in 'wa+'):return
  if name.suffix.lower()=='.md':raise ValueError('Analyst Markdown is not an accepted evidence input: '+str(name))
  if name.is_file() and root in name.parents:reads.add(str(name))
 sys.addaudithook(hook)
 r=execute(task,root);enabled=False
 r['read_inputs']=[dict(path=str(Path(p).relative_to(root)),sha256=digest(Path(p).read_bytes())) for p in sorted(reads) if '__pycache__' not in p and not p.endswith('.py')]
 target.write_text(json.dumps(r,ensure_ascii=False))
