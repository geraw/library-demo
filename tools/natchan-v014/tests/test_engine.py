import sys,json,copy,hashlib
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import combine,enrich,oracle_measurements,analyze
from render import view
from run import collect

def obs(**kw):
 d=dict(id='x',product='vikunja',product_version='2.6.0',run_id='run',tool='provengo',source=dict(sha256='a'*64,record=1),facts={},fact_basis='recomputed')
 d.update(kw);return d

def test_dedup_and_conflict():
 a=obs(facts={'x':True});b=copy.deepcopy(a)
 assert len(combine([('a',{'observations':[a]}),('b',{'observations':[b]})])[0])==1
 b['facts']['x']=False
 with pytest.raises(ValueError,match='Conflicting'):combine([('a',{'observations':[a]}),('b',{'observations':[b]})])

@pytest.mark.parametrize('cover,expected',[(999999,True),(-1,True),(0,False),(None,False)])
def test_cover_context(cover,expected):
 a=obs(request={'cover_image_attachment_id':cover},response={'code':4020},facts={'accepted_cover_then_noop_rejected':True})
 enrich([a]);assert a['facts'].get('invalid_cover_reference_observed',False)==expected

def test_blur_requires_original_creation():
 a=obs(request={},response={'id':7},facts={'blur_hash_ignored_on_update':True})
 enrich([a]);assert 'client_create_value_retained' not in a['facts']
 c=obs(operation='create',entity='projects',request={'background_blur_hash':'client'},response={'id':7,'background_blur_hash':'client'},facts={'readback_verified':True},source=dict(sha256='a'*64,record=0))
 enrich([c,a]);assert a['facts']['client_create_value_retained'] is True

def test_timestamp_policy_preserves_business_field():
 a=obs(facts={'changed_fields':['updated','background_blur_hash'],'silent_change':True})
 b=obs(facts={'changed_fields':['updated'],'silent_change':True})
 enrich([a,b]);assert a['facts']['changed_fields']==['background_blur_hash'];assert b['facts']['silent_change'] is False

def test_producer_verdict_is_not_trusted():
 a={'source':{'sha256':'a','record':1},'payload':{'category':'atomicity-check','verdict':'partial','readback_status':200,'first_status':500,'fields':{'a':'kept','b':'kept'}}}
 records,unknown=oracle_measurements([a]);assert records[0]['facts']['measured_field_outcome']=='unchanged';assert unknown
 a['payload']['fields']={};assert oracle_measurements([a])[0]==[]

def test_lock_mutation_rejected(tmp_path):
 (tmp_path/'raw').write_text('changed')
 with pytest.raises(ValueError,match='Original input changed'):collect({'datasets':[],'locked_sources':[{'path':'raw','sha256':hashlib.sha256(b'original').hexdigest()}]},tmp_path,tmp_path)

def test_render_parity_and_no_analyst_document():
 d=analyze([('test',{'observations':[obs()]})]);view(d)
 d['rule_occurrences']={'invented':1}
 with pytest.raises(ValueError,match='parity'):view(d)
 d['analyst_narrative_used']=True
 with pytest.raises(ValueError,match='common-engine'):view(d)

def test_native_not_http():
 d=analyze([('test',{'observations':[obs(tool='evomaster',method='POST',status=500)]})]);assert d['evidence_summary']['http_records']==0;assert d['evidence_summary']['native_evidence_records']==1

def matches(a):
 return set(analyze([('test',{'observations':[a]})])['rule_occurrences'])

@pytest.mark.parametrize('missing',[None,'nul_request_verified','postgres_nul_error_correlated','server_error'])
def test_postgres_rule_needs_payload_and_log(missing):
 f=dict(nul_request_verified=True,postgres_nul_error_correlated=True,server_error=True)
 if missing:f[missing]=False
 rules=matches(obs(product='gitea',product_version='28.1.0',facts=f))
 assert ('GIT-PG-NUL-ERROR' in rules)==(missing is None)

def test_unknown_version_gets_generic_not_c8():
 a=obs(product='gitea',product_version='29.0.0+dev',facts={'stored_reference_then_failed_rename':True,'server_error':True})
 rules=matches(a);assert 'OBS-STORED-REF-RENAME-ERROR' in rules;assert 'GIT-C8' not in rules

def test_worker_rejects_manual_markdown(tmp_path):
 import subprocess
 path=tmp_path/'NOTE.md';path.write_text('{}')
 task=dict(adapter='coverage-v005',manifest='NOTE.md',evidence_root='.')
 r=subprocess.run([sys.executable,str(ROOT/'worker.py'),json.dumps(task),str(tmp_path),str(tmp_path/'out.json')],capture_output=True,text=True)
 assert r.returncode!=0;assert 'Analyst Markdown is not an accepted evidence input' in r.stderr

def test_f04_classifier_requires_invalid_reference():
 base=dict(accepted_cover_then_noop_rejected=True,response_code=4020)
 assert 'VIK-F04' not in matches(obs(facts=base))
 assert 'VIK-F04' in matches(obs(facts=dict(base,invalid_cover_reference_observed=True)))

def test_o05_classifier_requires_creation_witness():
 base=dict(entity='projects',blur_hash_ignored_on_update=True,readback_verified=True)
 assert 'VIK-O05' not in matches(obs(entity='projects',facts=base))
 assert 'VIK-O05' in matches(obs(entity='projects',facts=dict(base,client_create_value_retained=True)))

@pytest.mark.parametrize('identifier,status,expected',[(0,200,True),(0,404,False),(999999999,200,False)])
def test_o07_zero_signature(identifier,status,expected):
 a=obs(method='DELETE',path=f'/projects/14/shares/{identifier}',status=status)
 assert ('VIK-O07' in matches(a))==expected

@pytest.mark.parametrize('password,response,expected',[('long-secret',{'invalid_fields':['password long-secret']},True),('long-secret',{'invalid_fields':['password too long']},False),('<100 chars>',{'invalid_fields':['<100 chars>']},False),('',{'invalid_fields':['']},False)])
def test_o09_exact_password_no_summary(password,response,expected):
 a=obs(method='POST',path='/register',status=412,request={'password':password},response=response)
 assert ('VIK-O09' in matches(a))==expected

def test_exact_nightly_version_is_qualified():
 a=obs(product='gitea',product_version='29.0.0+dev-175-g33610142c3',entity='issue',operation='update',status=500,facts={'entity':'issue','operation':'update','correlated_error_family':'missing_milestone'})
 assert 'GIT-C2' in matches(a)
 a['product_version']='29.0.0+dev-other';assert 'GIT-C2' not in matches(a)

def test_alias_same_event_counted_once_in_report():
 from presentation import project_findings
 a={'catalog_id':'GIT-C9','observation_id':'one'}
 b={'catalog_id':'GIT-PG-NUL-ERROR','observation_id':'one'}
 c={'catalog_id':'GIT-PG-NUL-ERROR','observation_id':'other'}
 rows=project_findings([a,b,c]);assert len(rows)==2
 primary=next(r for r in rows if r['catalog_id']=='GIT-C9')
 assert primary['supporting_labels']==['GIT-PG-NUL-ERROR']
 assert c in rows  # Generic-only evidence is not silently discarded.
 assert 'supporting_labels' not in a

def test_alias_canonical_projection_verified():
 a=obs(product='gitea',product_version='28.1.0',facts={'server_error':True,'nul_request_verified':True,'postgres_nul_error_correlated':True})
 d=analyze([('test',{'observations':[a]})]);_,groups,rows=view(d)
 assert 'GIT-C9' in groups and 'GIT-PG-NUL-ERROR' not in groups
 assert d['rule_occurrences']['GIT-PG-NUL-ERROR']==1
 d['report_findings']=[]
 with pytest.raises(ValueError,match='projection'):view(d)

def test_o07_comparison_retains_positive_id_and_fixed_control():
 values=[obs(method='DELETE',path='/projects/14/shares/'+str(identifier),status=status,product_version=version,response={'message':'Successfully deleted.' if status==200 else 'The project share does not exist.'},source={'sha256':'b'*64,'record':i}) for i,(version,identifier,status) in enumerate([('2.6.0',0,200),('2.6.0',999999999,200),('2.7.0',0,404),('2.7.0',999999999,404)])]
 d=analyze([('test',{'observations':values})]);assert len(d['share_delete_cases'])==4;assert d['rule_occurrences']['VIK-O07']==1
 assert not any(x['independent_absence_verified'] for x in d['share_delete_cases'])

def test_o09_missing_evidence_visible_and_not_confirmed(tmp_path):
 from render import write_report
 d=analyze([('test',{'observations':[obs()]})]);d['corpus_sha256']='test'
 p=tmp_path/'analysis.json';p.write_text(json.dumps(d));write_report(p,tmp_path)
 assert 'VIK-O09' not in d['rule_occurrences']
 html=(tmp_path/'report.html').read_text();assert 'ממצא היסטורי' in html;assert 'לא ניתן לאימות מהראיות הזמינות' in html;assert 'VIK-O09' in html
