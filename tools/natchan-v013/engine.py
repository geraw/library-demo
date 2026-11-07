"""One evidence -> facts -> rules engine. No analyst text or cached analysis input."""
from collections import Counter,defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import re
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v005'))
from coverage_classifier import classify
from providers import equal

def canonical(o):
 s=o['source'];sha=s.get('sha256') or s.get('journal_sha256')
 if not sha or 'record' not in s:raise ValueError('Observation lacks byte source and record')
 return 'event-'+hashlib.sha256(json.dumps([sha,s['record']],sort_keys=True).encode()).hexdigest()[:28]

def combine(parts):
 combined={};runs=[];oracles=[];inputs={}
 for dataset,part in parts:
  runs.extend(dict(r,dataset_id=dataset) for r in part.get('runs',[]));oracles.extend(part.get('original_oracles',[]))
  for item in part.get('read_inputs',[]):inputs[item['path']]=item['sha256']
  for original in part.get('observations',[]):
   o=deepcopy(original);key=canonical(o);o['id']=key;o['dataset_ids']=[dataset]
   o.setdefault('evidence_tier','recorded_http_sequence' if o.get('tool')=='direct-reproducer' else 'recorded_gateway_values')
   if o.get('measurement_sources'):o['evidence_tier']='producer_readback_values'
   o['event_role']='http-record' if o.get('method') and type(o.get('status')) is int else 'measurement'
   if o.get('tool') in ('evomaster','schemathesis'):o['event_role']='native-evidence'
   if key not in combined:combined[key]=o;continue
   prior=combined[key]
   if prior['product']!=o['product'] or prior.get('product_version')!=o.get('product_version'):raise ValueError('Same evidence has contradictory product/version')
   for k,v in o.get('facts',{}).items():
    if k in prior['facts'] and not equal(prior['facts'][k],v):raise ValueError('Conflicting facts '+key+' '+k)
    prior['facts'][k]=v
   prior['dataset_ids']=sorted(set(prior['dataset_ids']+o['dataset_ids']))
   prior.setdefault('alternate_sources',[]).append(o['source'])
   prior.setdefault('witnesses',[]).extend(o.get('witnesses',[]))
   for k in ('entity','operation','field'):
    if o.get(k) is not None and prior.get(k) is None:prior[k]=o[k]
   if prior.get('event_role')!='http-record' and o['event_role']=='http-record':
    for k in ('method','status','path','request','response','event_role'):prior[k]=o.get(k)
 return list(combined.values()),runs,oracles,[dict(path=p,sha256=s) for p,s in sorted(inputs.items())]

def enrich(observations):
 policy=json.loads((ROOT/'profiles.json').read_text())['readback_exclusions']
 for o in observations:
  f=o['facts'];ignored=[k for k in f.get('changed_fields',[]) if k in policy.get(o['product'],[])]
  if ignored:
   f['excluded_readback_fields']=ignored
   f['changed_fields']=[k for k in f['changed_fields'] if k not in ignored]
   f['silent_change']=bool(f['changed_fields'] or f.get('dropped_fields'))
 byrun=defaultdict(list)
 for o in observations:byrun[(o['product'],o['run_id'])].append(o)
 for values in byrun.values():
  for o in values:
   f=o['facts'];request=o.get('request');response=o.get('response')
   if o['product']=='vikunja':
    if o.get('method')=='DELETE' and re.fullmatch(r'/projects/[0-9]+/shares/0',o.get('path','')) and type(o.get('status')) is int and 200<=o['status']<300:
     f['zero_share_delete_success']=True
    if o.get('path')=='/register' and isinstance(request,dict):
     password=request.get('password')
     f['password_echoed']=bool(o.get('status')==412 and isinstance(password,str) and len(password)>0 and not re.fullmatch(r'<[0-9]+ chars>',password) and isinstance(response,dict) and password in json.dumps(response,ensure_ascii=False))

   if o['product']=='vikunja' and isinstance(request,dict):
    cover=request.get('cover_image_attachment_id')
    if f.get('accepted_cover_then_noop_rejected') and type(cover) is int and cover!=0 and isinstance(response,dict) and response.get('code')==4020:
     f.update(invalid_cover_reference_observed=True,cover_reference_value=cover)
    if f.get('blur_hash_ignored_on_update'):
     identity=(response or {}).get('id') if isinstance(response,dict) else None
     candidates=[x for x in values if x.get('operation')=='create' and x.get('entity')=='projects' and isinstance(x.get('request'),dict) and isinstance(x.get('response'),dict) and x['response'].get('id')==identity and 'background_blur_hash' in x['request'] and equal(x['request']['background_blur_hash'],x['response'].get('background_blur_hash')) and x['facts'].get('readback_verified') is True and x['source']['record']<o['source']['record']]
     if len(candidates)==1:
      f['client_create_value_retained']=True;o.setdefault('witnesses',[]).append(dict(accepted_client_create=candidates[0]['source']))
   if o['product']=='gitea' and f.get('stored_reference_then_failed_rename'):
    f['stored_ref_rename_error_observed']=True
   if o['product']=='gitea' and f.get('release_tag_error_context_verified'):
    f['c4_subtype']=f.get('correlated_error_family')
 return observations

def oracle_measurements(originals):
 out=[];unknown=[];seen=set()
 for item in originals:
  row=item['payload'];source=item['source'];key=(source.get('sha256'),source.get('record'))
  if key in seen:continue
  seen.add(key);category=row.get('category');facts={};family=None
  if category=='atomicity-check':
   family='ATOM-1-2';fields=row.get('fields',{});values=set(fields.values()) if isinstance(fields,dict) else set()
   if row.get('readback_status')==200 and row.get('first_status',0)>=500 and values:
    verdict='partial' if {'applied','kept'}<=values else 'unchanged' if values=={'kept'} else 'applied' if values=={'applied'} else 'unknown'
    facts=dict(measured_field_outcome=verdict,measured_fields=fields,full_snapshots_verified=False)
   unknown.append(dict(family=family,source=source,reason='full_before_after_snapshots_missing'))
  elif category in ('reference-check','link2-check'):
   family='REF-1' if category=='reference-check' else 'LINK-2'
   sent=row.get('sent');actual=row.get('stored') if family=='REF-1' else row.get('listed')
   if isinstance(sent,list) and isinstance(actual,list) and row.get('readback_status')==200 and type(row.get('status')) is int and 200<=row['status']<300:
    facts=dict(measured_reference_difference=not equal(sent,actual),sent_ids=sent,observed_ids=actual)
   elif type(row.get('status')) is int and 200<=row['status']<300:unknown.append(dict(family=family,source=source,reason='successful_id_projection_missing'))
  elif category=='divergence-check':unknown.append(dict(family='DIV-1',source=source,reason='stored_summary_is_not_independent_raw_pair'))
  if facts:
   # Product and run identity will be established from the source journal index.
   out.append(dict(source=source,facts=facts,entity=str(row.get('type','')).lower() or None,operation=row.get('kind') or row.get('action'),field=row.get('field'),family=family,evidence_tier='producer_field_measurements' if family=='ATOM-1-2' else 'producer_id_projection'))
 return out,unknown

def analyze(parts,catalogs=ROOT/'catalogs'):
 observations,runs,originals,inputs=combine(parts)
 raw_by_sha={o['source']['sha256']:o for o in observations}
 measurements,unknown=oracle_measurements(originals)
 for item in measurements:
  context=raw_by_sha.get(item['source'].get('sha256'))
  if context is None:continue
  o=dict(id='',product=context['product'],product_version=context.get('product_version'),run_id=context['run_id'],tool=context.get('tool'),source=item['source'],facts=item['facts'],fact_basis='recomputed',entity=item['entity'],operation=item['operation'],field=item['field'],event_role='measurement',evidence_tier=item['evidence_tier'],dataset_ids=context['dataset_ids'])
  o['id']=canonical(o)
  if not any(x['id']==o['id'] for x in observations):observations.append(o)
 observations=enrich(observations)
 report=classify(observations,catalogs)
 report.update(schema_version='natchan-unified-analysis/1',runs=runs,input_inventory=inputs,unknown_evidence=unknown,new_sut_requests=0,analyst_narrative_used=False)
 index={o['id']:o for o in observations};matched=defaultdict(set)
 for a in report['assessments']:
  if a['status']=='matched':matched[a['catalog_id']].add(a['observation_id'])
 report['rule_occurrences']={k:len(v) for k,v in sorted(matched.items())}
 report['finding_records']=[dict(catalog_id=k,observation_id=id,product=index[id]['product'],version=index[id].get('product_version'),run_id=index[id]['run_id'],tool=index[id].get('tool'),evidence_tier=index[id]['evidence_tier'],source=index[id]['source'],facts=next(a['facts'] for a in report['assessments'] if a['observation_id']==id),dataset_ids=index[id]['dataset_ids']) for k,ids in sorted(matched.items()) for id in sorted(ids)]
 coverage={}
 for _,part in parts:
  for c in part.get('family_coverage',[]):coverage[c['sha256']]=c['counts']
 report['descriptive_family_coverage']=dict(sum((Counter(c) for c in coverage.values()),Counter()))
 report['excluded_measurement_counts']=dict(Counter(k for o in observations for k in o['facts'].get('excluded_readback_fields',[])))
 report['rule_coverage']=[dict(catalog_id='VIK-O09',eligible_requests=sum(o.get('product')=='vikunja' and o.get('path')=='/register' for o in observations),status='request_evidence_present' if any(o.get('product')=='vikunja' and o.get('path')=='/register' for o in observations) else 'not_evaluable_no_registration_request')]
 resolution=json.loads((ROOT/'source-resolution.json').read_text())
 report['repository_resolution']=dict(repository=resolution['repository'],commit=resolution['commit'],exact_blob_matches=sum(bool(x['repository_paths']) for x in resolution['files']),unresolved_containers=sum(not x['repository_paths'] for x in resolution['files']),resolution_sha256=hashlib.sha256((ROOT/'source-resolution.json').read_bytes()).hexdigest())
 report['profile_sha256']=hashlib.sha256((ROOT/'profiles.json').read_bytes()).hexdigest()
 for run in runs:
  if run.get('last_http_500_source'):
   key=canonical({'source':run['last_http_500_source']})
   run['last_http_500_rules']=[rule for rule,ids in matched.items() if key in ids]
 report['evidence_summary']=dict(normalized_observations=len(observations),http_records=sum(o.get('event_role')=='http-record' for o in observations),http_5xx_records=sum(o.get('event_role')=='http-record' and type(o.get('status')) is int and 500<=o['status']<600 for o in observations),native_evidence_records=sum(o.get('event_role')=='native-evidence' for o in observations),measurements=sum(o.get('event_role')=='measurement' for o in observations),unclassified=report['summary']['unclassified_count'],unknown_evidence_records=len(unknown))
 return report
