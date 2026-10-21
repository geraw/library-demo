import copy
import importlib.util
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('natchan_v009',Path(__file__).parents[1]/'analyzer.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def sample(family):
 policy={};profile=dict(id='synthetic-product',version='test-only',families={family:policy},relationships=[dict(id='p-c',parent='parent',child='child',cascade_required=True)])
 events=[]
 def add(role,**kwargs):
  e=dict(id=str(len(events)),run_id='run1',case_id='case1',actor='A',resource='item:1',method='GET',status=200,response={},time='2026-10-21T00:00:01Z',probe=dict(id='p1',family=family,role=role));e.update(kwargs);events.append(e);return e
 if family in ('RESPONSE','EDGE-1'):
  e=add('request',status=500 if family=='RESPONSE' else 201,request={'title':'long'})
  policy.update(request_path=['title'],constraints={'maxLength':2})
 elif family in ('EDGE-U','DIV-1'):
  policy['comparable_preconditions']=True
  a=add('create',resource='item:created',method='POST',status=201,parent_scope='parent:1',request={'title':'x'});a['probe']['field']='title'
  add('update_before',response={'title':'old'})
  b=add('update',method='PATCH',status=400,parent_scope='parent:1',request={'title':'x'});b['probe']['field']='title'
 elif family=='CASCADE-1':
  add('child_before',entity='child',parent_resource='parent:1')
  add('parent_delete',resource='parent:1',entity='parent',method='DELETE',status=204)
  e=add('child_after');e['probe']['relationship']='p-c'
 elif family in ('ADJ','KNOWN'):
  policy.update(trigger_operation='create-parent',window_seconds=10,definition=dict(statuses=[500],operations=['write-child'],window_seconds=10,response_regex='locked'))
  add('trigger',resource='parent:1',operation='create-parent',method='POST',time='2026-10-21T00:00:00Z')
  add('request',operation='write-child',method='PATCH',status=500,response='locked')
 elif family=='IDEM':
  add('first',method='PATCH',request={'title':'x'})
  add('second',method='PATCH',request={'title':'x'},status=500)
 else:
  add('before',response={'title':'old','x':0,'y':0,'ids':[1]})
  add('write',method='PATCH',status=500 if family=='ATOM-1-2' else 200,request={'title':'sent','x':1,'y':1,'ids':[2],'target':2})
  add('after',response={'title':'sen','x':1,'y':0,'ids':[]})
  if family=='RT-1':policy.update(readable_fields=['title'])
  if family=='ATOM-1-2':policy.update(operation='update')
  if family in ('REF-1','LINK-2'):policy.update(request_path=['ids'],response_path=['ids'],semantics='exact_set')
  if family=='VIEW':policy.update(expected_path=['ids'],response_path=['ids'],membership_required=True)
  if family=='LINK':policy.update(operation='add',target_path=['target'],response_path=['ids'])
 return dict(schema_version='natchan-events/1',synthetic=True,capture_complete=True,profile=profile,events=events)

EXPECTED={'RESPONSE':'GEN-SERVER_ERROR','EDGE-1':'GEN-BOUND_NOT_ENFORCED','RT-1':'GEN-SILENT_CHANGE','ATOM-1-2':'GEN-PARTIAL_WRITE','EDGE-U':'GEN-CREATE_UPDATE_DIVERGENCE','KNOWN':'GEN-KNOWN-TRANSIENT-SIGNATURE','CASCADE-1':'GEN-ORPHAN_AFTER_DELETE','ADJ':'GEN-TRIGGER-ADJACENCY','IDEM':'GEN-DUPLICATE_WRITE_ERROR','VIEW':'GEN-VIEW_MISMATCH','LINK':'GEN-LINK_MISMATCH','REF-1':'GEN-REFERENCE-POLICY-VIOLATION','LINK-2':'GEN-RELATIONSHIP-CLEARED','DIV-1':'GEN-CREATE_UPDATE_DIVERGENCE'}
def labels(r):return {x for a in r['assessments'] for x in a.get('patterns',[])}
@pytest.mark.parametrize('family',m.FAMILIES)
def test_positive_full_pipeline(family):
 r=m.analyze(sample(family));assert EXPECTED[family] in labels(r)
 assert r['family_coverage'][family]['evaluated']==1
 assert not any(a['known_bugs'] for a in r['assessments'])
@pytest.mark.parametrize('family',[f for f in m.FAMILIES if f not in ('RESPONSE','EDGE-1')])
def test_missing_final_record_never_finds_positive(family):
 d=sample(family);d['events'].pop()
 r=m.analyze(d);assert EXPECTED[family] not in labels(r)
 assert r['family_coverage'][family]['not_evaluable']==1
@pytest.mark.parametrize('family',[f for f in m.FAMILIES if f not in ('RESPONSE','EDGE-1')])
def test_wrong_actor_is_unknown(family):
 d=sample(family);d['events'][-1]['actor']='other'
 r=m.analyze(d);assert EXPECTED[family] not in labels(r)
 assert r['family_coverage'][family]['not_evaluable']==1
@pytest.mark.parametrize('family',['RT-1','ATOM-1-2','IDEM','REF-1','LINK-2','LINK','VIEW','CASCADE-1'])
def test_intervening_write_is_unknown(family):
 d=sample(family);e=copy.deepcopy(d['events'][-1]);e.update(id='interference',method='PATCH');e.pop('probe');d['events'].insert(-1,e)
 assert m.analyze(d)['family_coverage'][family]['not_evaluable']==1

def test_parent_mismatch_not_orphan():
 d=sample('CASCADE-1');d['events'][0]['parent_resource']='other'
 assert 'GEN-ORPHAN_AFTER_DELETE' not in labels(m.analyze(d))
def test_denied_child_read_not_orphan_or_absence():
 d=sample('CASCADE-1');d['events'][-1]['status']=403
 assert m.analyze(d)['family_coverage']['CASCADE-1']['not_evaluable']==1
@pytest.mark.parametrize('seconds',['2026-10-21T00:00:30Z','2026-10-20T23:59:59Z'])
def test_outside_window_not_adjacency(seconds):
 d=sample('ADJ');d['events'][-1]['time']=seconds
 assert 'GEN-TRIGGER-ADJACENCY' not in labels(m.analyze(d))
def test_identity_alias_declared_once_in_profile():
 d=sample('IDEM');d['events'][-1]['actor']='B';d['profile']['identities']={'A':'same-user','B':'same-user'}
 assert EXPECTED['IDEM'] in labels(m.analyze(d))
def test_idem_first_error_visible():
 d=sample('IDEM');d['events'][0]['status']=500;d['events'][1]['status']=200
 assert EXPECTED['IDEM'] in labels(m.analyze(d))
def test_reference_observe_is_symptom_not_policy_violation():
 d=sample('REF-1');d['profile']['families']['REF-1']['semantics']='observe'
 x=labels(m.analyze(d));assert 'GEN-REFERENCE-PROJECTION-DIFFERENCE' in x
 assert 'GEN-REFERENCE-POLICY-VIOLATION' not in x
def test_forged_verdict_ignored():
 d=sample('RT-1');d['events'][-1]['response']['title']='sent';d['events'][-1]['verdict']='mismatch'
 assert 'GEN-SILENT_CHANGE' not in labels(m.analyze(d))
def test_incomplete_capture_rejected():
 d=sample('RESPONSE');d['capture_complete']=False
 with pytest.raises(m.Missing):m.analyze(d)
def test_duplicate_ids_rejected():
 d=sample('IDEM');d['events'][1]['id']='0'
 with pytest.raises(m.Missing):m.analyze(d)
def test_known_never_suppressed():
 r=m.analyze(sample('KNOWN'));assert r['provider_evaluations'][0]['facts']['suppress_failure'] is False
 assert 'GEN-SERVER_ERROR' in labels(r)
@pytest.mark.parametrize('family',m.FAMILIES)
def test_healthy_control(family):
 d=sample(family);events=d['events']
 if family=='RESPONSE':events[-1]['status']=200
 elif family=='EDGE-1':events[-1]['request']['title']='ok'
 elif family=='RT-1':events[-1]['response']['title']='sent'
 elif family=='ATOM-1-2':events[-1]['response']=copy.deepcopy(events[0]['response'])
 elif family in ('EDGE-U','DIV-1'):
  events[-1]['status']=200
  for role,resource in [('create_after','item:created'),('update_after','item:1')]:
   e=copy.deepcopy(events[-1]);e.update(id='healthy-'+role,resource=resource,method='GET',response={'title':'x'});e['probe']['role']=role;events.append(e)
 elif family=='CASCADE-1':events[-1]['status']=404
 elif family in ('ADJ','KNOWN','IDEM'):events[-1]['status']=200
 elif family in ('REF-1','LINK-2','VIEW','LINK'):events[-1]['response']['ids']=[2]
 r=m.analyze(d)
 assert EXPECTED[family] not in labels(r)
 assert r['family_coverage'][family]['evaluated']==1

def test_reset_never_bridges():
 d=sample('IDEM');e=copy.deepcopy(d['events'][0]);e.update(id='reset',case_id='reset-case',role='reset');e.pop('probe');d['events'].insert(1,e)
 assert m.analyze(d)['family_coverage']['IDEM']['not_evaluable']==1

def test_duplicate_role_unknown():
 d=sample('IDEM');e=copy.deepcopy(d['events'][0]);e['id']='extra';d['events'].insert(1,e)
 assert m.analyze(d)['family_coverage']['IDEM']['not_evaluable']==1

def test_profile_preconditions_required():
 d=sample('EDGE-U');d['profile']['families']['EDGE-U'].pop('comparable_preconditions')
 assert m.analyze(d)['family_coverage']['EDGE-U']['not_evaluable']==1

def test_no_measured_family_not_zero_bugs():
 r=m.analyze(sample('RESPONSE'));assert r['family_coverage']['ATOM-1-2']=={'no_measurements':True}
@pytest.mark.parametrize('family',['RT-1','ATOM-1-2'])
def test_malformed_readback_not_a_find(family):
 d=sample(family);d['events'][-1]['response']='not-an-object'
 assert m.analyze(d)['family_coverage'][family]['not_evaluable']==1

def test_missing_known_response_not_matched_by_broad_regex():
 d=sample('KNOWN');d['events'][-1].pop('response');d['profile']['families']['KNOWN']['definition']['response_regex']='.*'
 assert m.analyze(d)['family_coverage']['KNOWN']['not_evaluable']==1
@pytest.mark.parametrize('version,reason,expected',[('28.1.0','email invalid',True),('28.2.0','email invalid',False),('28.1.0','permission denied',False)])
def test_known_bug_version_and_error_context(version,reason,expected):
 d=sample('EDGE-U');d['profile'].update(id='gitea',version=version)
 for e in d['events']:
  e['entity']='organization'
  if 'request' in e:e['request']={'email':'bad@email'};e['probe']['field']='email'
 d['events'][0]['response']={'email':'bad@email'}
 d['events'][-1].update(status=422,response={'message':reason})
 r=m.analyze(d);known={x for a in r['assessments'] for x in a.get('known_bugs',[])}
 assert ('GIT-C7' in known)==expected
