import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import toolkit_adapter as tk
from toolkit_formats import InvalidEvidence,UnsupportedEvidence


def pack(files):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for name,value in files.items():z.writestr(name,value)
    return b.getvalue()


def ref_rows(stale=False,write_status=200):
    sid='DELREF_object_targetId'
    rows=[('POST','/targets',{},201,{'id':'t'}),('GET','/targets/t',None,200,{'id':'t'}),
          ('POST','/objects',{'targetId':'t'},201,{'id':'r','targetId':'t'}),
          ('GET','/objects/r',None,200,{'id':'r','targetId':'t'}),
          ('DELETE','/targets/t',None,200,{})]
    if stale:rows.append(('PUT','/objects/r',{'targetId':'t'},write_status,{}))
    rows.extend([('GET','/targets/t',None,404,{}),('GET','/objects/r',None,200,{'id':'r','targetId':'t' if write_status==200 else None})])
    return [dict(category='research',index=i,session='A',method=m,path=p,input=b,status=s,response=json.dumps(r),logical_id=f'{sid}_{i+1} operation') for i,(m,p,b,s,r) in enumerate(rows)]


def files(rows,product='widget',native=None):
    ids=sorted({r['logical_id'].rsplit('_',1)[0] for r in rows})
    result=dict(version='stories-dev',sut=product,runner='provengo',requests=len(rows),
        stories=[dict(story=s,status='COMPLETED',exit=0,failed_checks=[]) for s in ids],
        http_5xx=[{} for r in rows if r['status']>=500])
    out={'result_stories.json':json.dumps(result).encode(),
         'gateway-journal.jsonl':'\n'.join(json.dumps(r) for r in rows).encode()}
    if native is not None:out['compiled/'+ids[0]+'/native.log']=native.encode()
    return out


def aggregate_rows():
    steps=[('POST','/parents',{},201,{'id':'p1'},'create P1'),
        ('GET','/parents/p1/values',None,200,{'energy':0},'read aggregate P1 baseline'),
        ('POST','/children',{'parent':'p1'},201,{'id':'c1'},'create C1'),
        ('GET','/children/c1/values',None,200,{'energy':7},'read view C1'),
        ('GET','/parents/p1/values',None,200,{'energy':7},'read aggregate P1 after the first child'),
        ('POST','/children',{'parent':'p1'},201,{'id':'c2'},'create C2'),
        ('GET','/children/c2/values',None,200,{'energy':11},'read view C2'),
        ('GET','/parents/p1/values',None,200,{'energy':18},'read aggregate P1 after the second child'),
        ('POST','/parents',{},201,{'id':'p2'},'create P2'),
        ('GET','/parents/p2/values',None,200,{'energy':0},'read aggregate P2 baseline'),
        ('PATCH','/children/c2',{'parent':'p2'},200,{'id':'c2','parent':'p2'},'move C2 to P2'),
        ('GET','/parents/p1/values',None,200,{'energy':18},'read aggregate P1 after moving C2 away'),
        ('GET','/parents/p2/values',None,200,{'energy':11},'read aggregate P2 after moving C2 in')]
    return [dict(category='research',index=i,session='A',method=m,path=p,input=b,status=s,response=json.dumps(r),logical_id=f'AGG_child_parent_{i+1} {label}') for i,(m,p,b,s,r,label) in enumerate(steps)]


class StoriesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
    def read(self,f):
        p=self.base/'input.zip';p.write_bytes(pack(f));return tk.Reader(p).finish()
    def cli(self,f,product='widget'):
        p=self.base/'input.zip';p.write_bytes(pack(f));q=self.base/'request.json'
        q.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='test',tool='provengo',product=product,product_version='unknown'),evidence=dict(adapter='toolkit-v1',archive=str(p)))))
        cmd=subprocess.run([sys.executable,str(ROOT/'natchan.py'),'--request',str(q),'--output',str(self.base/'output')],capture_output=True,text=True)
        return cmd,json.loads((self.base/'output/result.json').read_text())
    def test_raw_dangling_reference_without_producer_fail_flags(self):
        a=self.read(files(ref_rows()));self.assertEqual(a['rule_occurrences']['STORY-DANGLING-REFERENCE'],1)
        self.assertEqual(a['evidence_summary']['http_records'],7)
    def test_stale_write_recomputed(self):
        a=self.read(files(ref_rows(stale=True)));self.assertEqual(a['rule_occurrences']['STORY-STALE-REFERENCE'],1)
    def test_rejected_stale_write_is_not_a_retained_dangling_reference(self):
        a=self.read(files(ref_rows(stale=True,write_status=500)))
        self.assertNotIn('STORY-DANGLING-REFERENCE',a['rule_occurrences'])
        self.assertEqual(a['rule_occurrences']['STORY-MISSING-REFERENCE-5XX'],1)
    def test_forbidden_target_read_does_not_prove_absence(self):
        rows=ref_rows();rows[-2]['status']=403
        a=self.read(files(rows));self.assertNotIn('STORY-DANGLING-REFERENCE',a['rule_occurrences'])
    def test_actor_conflict_not_promoted(self):
        rows=ref_rows();rows[-1]['session']='B'
        self.assertNotIn('STORY-DANGLING-REFERENCE',self.read(files(rows))['rule_occurrences'])
    def test_no_successful_preimage_not_promoted(self):
        rows=ref_rows();rows[3]['status']=404
        self.assertNotIn('STORY-DANGLING-REFERENCE',self.read(files(rows))['rule_occurrences'])
    def test_recreated_target_not_promoted(self):
        rows=ref_rows();rows.insert(-1,dict(rows[1],method='PUT',input={'id':'t'},status=200,index=22,logical_id='DELREF_object_targetId_7 operation'))
        rows[-1]['logical_id']='DELREF_object_targetId_8 operation'
        self.assertNotIn('STORY-DANGLING-REFERENCE',self.read(files(rows))['rule_occurrences'])
    def test_duplicate_http_index_is_invalid(self):
        rows=ref_rows();rows[-1]['index']=0
        with self.assertRaises(InvalidEvidence):self.read(files(rows))
    def test_duplicate_step_is_explicit_ambiguity(self):
        rows=ref_rows();rows[-1]['logical_id']=rows[0]['logical_id']
        a=self.read(files(rows));self.assertNotIn('STORY-DANGLING-REFERENCE',a['rule_occurrences'])
        self.assertIn('STORY_RETRY_OR_STEP_ASSOCIATION_AMBIGUOUS',[g['code'] for g in a['toolkit_coverage_gaps']])
    def test_bad_request_count_is_exit_2(self):
        f=files(ref_rows());r=json.loads(f['result_stories.json']);r['requests']=88;f['result_stories.json']=json.dumps(r)
        p,r=self.cli(f);self.assertEqual(p.returncode,2);self.assertEqual(r['exit_code'],2)
    def test_isolated_cli_reads_stories(self):
        p,r=self.cli(files(ref_rows()));self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(r['counts']['finding_occurrences'],1)
    def test_unknown_result_format_is_exit_3(self):
        f=files(ref_rows());r=json.loads(f['result_stories.json']);r['version']='stories-future';f['result_stories.json']=json.dumps(r)
        p,r=self.cli(f);self.assertEqual(p.returncode,3);self.assertEqual(r['exit_code'],3)
    def test_unknown_journal_layout_is_exit_3(self):
        p,r=self.cli({'gateway-journal.jsonl':'{}\n'});self.assertEqual(p.returncode,3)
    def test_unknown_runner_is_unsupported(self):
        f=files(ref_rows());r=json.loads(f['result_stories.json']);r['runner']='future';f['result_stories.json']=json.dumps(r)
        with self.assertRaises(UnsupportedEvidence):self.read(f)
    def test_summary_flags_do_not_change_raw_findings(self):
        f=files(ref_rows());a=self.read(f);r=json.loads(f['result_stories.json']);r['stories'][0]['failed_checks']=[{'pass':True,'expected':'all good'}];f['result_stories.json']=json.dumps(r)
        self.assertEqual(a['rule_occurrences'],self.read(f)['rule_occurrences'])
    def test_wrapped_folder_preserves_exact_member_path(self):
        f={'folder/'+k:v for k,v in files(ref_rows()).items()};a=self.read(f)
        self.assertEqual(a['observations'][0]['source']['members'],['folder/gateway-journal.jsonl'])
    def test_nested_story_archive_is_read(self):
        a=self.read({'review_stories.zip':pack(files(ref_rows()))})
        self.assertEqual(a['evidence_summary']['http_records'],7)
    def test_missing_journal_is_not_zero_http(self):
        f=files(ref_rows());del f['gateway-journal.jsonl'];a=self.read(f)
        self.assertIsNone(a['evidence_summary']['http_records'])
        self.assertIsNone(a['stories_evidence_audit'][0]['retained_research_requests'])
    def native(self,c):
        f=files(ref_rows());del f['gateway-journal.jsonl'];f['compiled/x/native.log']='STORY_CHECK '+json.dumps(c)+'\nSTORY_DONE\nTest Result: SUCCESS\n';return f
    def test_contribution_measurement_recomputed_without_trusting_pass(self):
        c=dict(story='DELREF_object_targetId',check='add quantity x0.5',expected=19,observed=20,detail=dict(previous=17,source_sum=4,scale=0.5),**{'pass':True})
        a=self.read(self.native(c));self.assertEqual(a['rule_occurrences']['STORY-MEASURED-CONTRIBUTION'],1)
        o=a['observations'][0];self.assertEqual(o['evidence_tier'],'producer_story_measurements');self.assertIsNone(a['evidence_summary']['http_records'])
    def test_forged_contribution_expectation_not_promoted(self):
        c=dict(story='DELREF_object_targetId',check='add quantity x0.5',expected=99,observed=20,detail=dict(previous=17,source_sum=4,scale=0.5),**{'pass':False})
        self.assertNotIn('STORY-MEASURED-CONTRIBUTION',self.read(self.native(c))['rule_occurrences'])
    def test_projection_difference_recomputed(self):
        c=dict(story='DELREF_object_targetId',check='copy response INTRA-REF $.b[].refs[].id in $.a[]',expected=[],observed=['bad'],detail=dict(A=['ok'],B=['bad']),**{'pass':True})
        self.assertEqual(self.read(self.native(c))['rule_occurrences']['STORY-MEASURED-INTRA-REF'],1)
    def test_forged_projection_not_promoted(self):
        c=dict(story='DELREF_object_targetId',check='copy INTRA-REF projection',expected=[],observed=['invented'],detail=dict(A=['ok'],B=['ok']),**{'pass':False})
        self.assertNotIn('STORY-MEASURED-INTRA-REF',self.read(self.native(c))['rule_occurrences'])
    def test_harness_not_presented_as_native(self):
        f=files(ref_rows());r=json.loads(f['result_stories.json']);r['runner']='harness';f['result_stories.json']=json.dumps(r)
        a=self.read(f);self.assertEqual(a['runs'][0]['tool'],'story-harness')
        self.assertIn('STORIES_HARNESS_NOT_NATIVE_PROVENGO',[g['code'] for g in a['toolkit_coverage_gaps']])
    def test_expected_config_version_is_not_observed_version(self):
        f=files(ref_rows());f['sut.json']=json.dumps(dict(name='widget',api=dict(expected_version='99')))
        a=self.read(f);self.assertIsNone(a['runs'][0]['version'])
    def test_correct_projection_does_not_produce_finding(self):
        c=dict(story='DELREF_object_targetId',check='copy INTRA-REF projection',expected=[],observed=[],detail=dict(A=['ok'],B=['ok']),**{'pass':False})
        self.assertNotIn('STORY-MEASURED-INTRA-REF',self.read(self.native(c))['rule_occurrences'])
    def test_generic_aggregate_move_recomputed(self):
        a=self.read(files(aggregate_rows()));self.assertEqual(a['rule_occurrences']['STORY-AGGREGATE-MOVE'],1)
        o=next(o for o in a['observations'] if o.get('facts',{}).get('story_aggregate_after_move_mismatch'))
        self.assertEqual(o['facts']['aggregate_expected'],{'energy':7.0})
    def test_repaired_old_parent_aggregate_not_flagged(self):
        rows=aggregate_rows();rows[-2]['response']=json.dumps({'energy':7})
        self.assertNotIn('STORY-AGGREGATE-MOVE',self.read(files(rows))['rule_occurrences'])
    def test_failed_aggregate_control_not_promoted(self):
        rows=aggregate_rows();rows[4]['response']=json.dumps({'energy':90})
        a=self.read(files(rows));self.assertNotIn('STORY-AGGREGATE-MOVE',a['rule_occurrences'])
    def test_wrong_parent_read_path_not_promoted(self):
        rows=aggregate_rows();rows[-2]['path']='/parents/other/values'
        self.assertNotIn('STORY-AGGREGATE-MOVE',self.read(files(rows))['rule_occurrences'])
    def test_unsuccessful_move_not_promoted(self):
        rows=aggregate_rows();rows[-3]['status']=409
        self.assertNotIn('STORY-AGGREGATE-MOVE',self.read(files(rows))['rule_occurrences'])
    def test_move_response_must_confirm_new_parent(self):
        rows=aggregate_rows();rows[-3]['response']=json.dumps({'id':'c2','parent':'p1'})
        self.assertNotIn('STORY-AGGREGATE-MOVE',self.read(files(rows))['rule_occurrences'])
    def test_different_aggregate_actor_not_promoted(self):
        rows=aggregate_rows();rows[-2]['session']='B'
        self.assertNotIn('STORY-AGGREGATE-MOVE',self.read(files(rows))['rule_occurrences'])
    def test_stories_env_observed_version_read(self):
        f=files(ref_rows());f['ENV_stories_run.txt']='sut=widget\nsut_version=1.2.3\n'
        self.assertEqual(self.read(f)['runs'][0]['version'],'1.2.3')
    def test_stories_manifest_hash_verified(self):
        f=files(ref_rows());f['manifest_stories.json']=json.dumps({'gateway-journal.jsonl':hashlib.sha256(f['gateway-journal.jsonl']).hexdigest()})
        self.assertNotIn('STORIES_MANIFEST_MISSING',[g['code'] for g in self.read(f)['toolkit_coverage_gaps']])
    def test_stories_manifest_tampering_is_invalid_input(self):
        f=files(ref_rows());f['manifest_stories.json']=json.dumps({'gateway-journal.jsonl':'0'*64})
        p,r=self.cli(f);self.assertEqual(p.returncode,2)
    def test_two_creates_with_same_identity_are_not_distinct_resources(self):
        rows=ref_rows();rows.insert(3,dict(rows[2],index=55,logical_id='DELREF_object_targetId_4 another create'))
        for i,r in enumerate(rows):r['logical_id']=f'DELREF_object_targetId_{i+1} operation'
        a=self.read(files(rows));self.assertIn('STORY_REFERRER_FIXTURES_SHARE_IDENTITY',[g['code'] for g in a['toolkit_coverage_gaps']])
    def test_candidate_is_not_counted_as_version_confirmed_bug(self):
        rows=ref_rows()
        for r in rows:r['path']=r['path'].replace('/objects','/api/households/shopping/items')
        p,r=self.cli(files(rows,product='mealie'),product='mealie')
        self.assertEqual(p.returncode,0);self.assertEqual(r['counts']['known_bug_occurrences'],0)
        a=json.loads((self.base/'output/analysis.json').read_text())
        self.assertEqual(a['story_known_bug_candidates'][0]['candidate_id'],'M-D1')
        self.assertFalse(a['story_known_bug_candidates'][0]['version_confirmed'])
    def test_outer_result_does_not_hide_nested_raw_journal(self):
        inner=files(ref_rows());outer={'result_stories.json':inner['result_stories.json'],'review_stories.zip':pack(inner)}
        a=self.read(outer);self.assertEqual(a['evidence_summary']['http_records'],7)
        self.assertEqual(a['observations'][0]['source']['members'],['review_stories.zip','gateway-journal.jsonl'])
    def test_outer_inner_story_result_conflict_is_invalid(self):
        inner=files(ref_rows());r=json.loads(inner['result_stories.json']);r['requests']=99
        p,result=self.cli({'result_stories.json':json.dumps(r),'review_stories.zip':pack(inner)})
        self.assertEqual(p.returncode,2)


if __name__=='__main__':unittest.main()
