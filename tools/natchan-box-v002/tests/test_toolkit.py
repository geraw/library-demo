import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import toolkit_adapter as tk
spec=importlib.util.spec_from_file_location('toolkit_box',ROOT/'natchan.py');box=importlib.util.module_from_spec(spec);spec.loader.exec_module(box)

def pack(files):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for name,raw in files.items():z.writestr(name,raw)
    return b.getvalue()

def run_files(product='gitea',version='28.1.0',seed=1,campaign=False,verdict='partial'):
    base='/repos/a/r/issues/1'
    common=dict(category='research',session='A',t_utc='2026-10-23T12:00:00+00:00')
    rows=[dict(common,method='GET',path=base,status=200,input=None,response=json.dumps({'id':1,'body':'old','milestone':{'id':99}}),t_rel_ms=1,action='read',logical_id='Issue_1'),
          dict(common,method='PATCH',path=base,status=500,input={'body':'new','milestone':99},response='{}',t_rel_ms=2,action='update',logical_id='Issue_1'),
          dict(common,method='GET',path=base,status=200,input=None,response=json.dumps({'id':1,'body':'new','milestone':{'id':99}}),t_rel_ms=3,action='read',logical_id='Issue_1')]
    ir={'entities':[{'name':'Issue','path':'/repos/{owner}/{repo}/issues','detail':'/repos/{owner}/{repo}/issues/{index}','create_method':'post','update_method':'patch','update_schema':{'properties':{'body':{'type':'string'},'milestone':{'type':'integer'}}}}]}
    result={'version':'v1-campaign' if campaign else 'v1','sut':product,'sut_version':version,'seed':seed,'status':'COMPLETED' if campaign else 'STOPPED_AT_FIRST_FAILURE','native_exit':0,'requests':3}
    files={'native.log':'INFO [RUN] Test Result: SUCCESS','sut.log':'2026/10/23 12:00:00 EditIssue() [E] InternalServerError: milestone does not exist [id: 99, repo_id: 2]\n2026/10/23 12:00:00 router: completed PATCH /api/v1/repos/a/r/issues/1 for 172.17.0.2:8, 500 Internal Server Error\n','generated/contract-ir.json':json.dumps(ir)}
    if campaign:
        plan=[];expanded=[]
        for i,r in enumerate(rows):
            r['logical_id']='G014_STEP_'+str(i)
            role='probe' if i==1 else 'readback'
            plan.append(dict(method=r['method'],role=role,entity='Issue',field='milestone',pair=1,phase='update',mode='missing'))
            expanded += [r,dict(category='g014-sequence',step=i,role=role,method=r['method'],path=r['path'],request=r['input'],status=r['status'],response=json.loads(r['response']))]
        rows=expanded;result.update(completed_steps=3,planned_steps=3,fixture_failures=[]);files['generated/plan.json']=json.dumps({'steps':plan});files['profile.json']='{}'
    else:rows.append(dict(category='atomicity-check',fields={'body':'kept','milestone':'kept'},readback_status=200,first_status=500,verdict=verdict))
    files['gateway-journal.jsonl']='\n'.join(json.dumps(r) for r in rows)+'\n';files['result_v1.json']=json.dumps(result)
    encoded={k:v.encode() for k,v in files.items()}
    encoded['input_hashes.json' if campaign else 'manifest_v1.json']=json.dumps({k:tk.digest(v) for k,v in encoded.items()}).encode()
    return encoded

class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def read(self,files,**kwargs):
        p=self.root/'evidence.zip';p.write_bytes(pack(files));return tk.Reader(p,**kwargs).finish()
    def test_E2_version_from_result_without_native_version_event(self):
        r=self.read(run_files());self.assertEqual(r['evidence_summary']['http_records'],3)
        self.assertEqual(r['runs'][0]['version'],'28.1.0');self.assertIn('GIT-C2',r['rule_occurrences'])
        self.assertTrue(all(o['product']=='gitea' for o in r['observations']))
    def test_E1_nested_seeds_and_source_chain(self):
        inner=run_files();r=self.read({'ENV_v1_model.txt':b'sut=gitea\nkind=model\nsut_version=28.1.0\nseeds=1\nresult=V1_MODEL_COMPLETE\n','review_v1_s1.zip':pack(inner),'result_v1_s1.json':inner['result_v1.json']})
        self.assertEqual(r['evidence_summary']['http_records'],3)
        self.assertEqual(r['observations'][0]['source']['members'],['review_v1_s1.zip','gateway-journal.jsonl'])
    def test_E4_sequence_is_not_an_extra_http_exchange(self):
        r=self.read(run_files(campaign=True));self.assertEqual(r['evidence_summary']['http_records'],3)
        self.assertEqual(r['runs'][0]['completed_steps'],3)
        self.assertNotIn('SEQUENCE_HTTP_ASSOCIATION_INCOMPLETE',[g['code'] for g in r['toolkit_coverage_gaps']])
    def test_E3_outer_campaign(self):
        r=self.read({'ENV_v1_campaign.txt':b'sut=gitea\nsut_version=28.1.0\nkind=campaign\nresult=V1_CAMPAIGN_COMPLETE\n','review_v1_s1.zip':pack(run_files(campaign=True))});self.assertEqual(r['runs'][0]['planned_steps'],3)
    def test_stopped_package_is_no_evidence_not_clean_zero(self):
        p=self.root/'stopped.zip';p.write_bytes(pack({'ENV_v1_model.txt':b'sut=gitea\nkind=model\nresult=STOPPED\n','STOPPED_v1_model.txt':b'Nothing changed'}))
        request={'schema_version':'natchan-request/1','run':dict(id='stopped',product='gitea',tool='provengo',product_version='28.1.0'),'evidence':dict(adapter='toolkit-v1',archive=str(p))}
        q=self.root/'request.json';q.write_text(json.dumps(request));r=box.run(q,self.root/'out')
        self.assertEqual(r['status'],'PARTIAL');self.assertIsNone(r['counts']['known_bug_occurrences'])
    def test_manifest_tampering_rejected(self):
        files=run_files();files['native.log']=b'altered'
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.read(files)
    def test_outer_inner_version_conflict(self):
        with self.assertRaisesRegex(ValueError,'metadata conflict'):
            self.read({'ENV_v1_model.txt':b'sut=gitea\nsut_version=9.0\n','review_v1_s1.zip':pack(run_files())})
    def test_outer_result_copy_conflict(self):
        with self.assertRaisesRegex(ValueError,'copies disagree'):
            self.read({'ENV_v1_model.txt':b'sut=gitea','review_v1_s1.zip':pack(run_files()),'result_v1_s1.json':b'{}'})
    def test_forged_verdict_cannot_force_partial_measurement(self):
        r=self.read(run_files(verdict='partial'));self.assertIn('MEASURED-UNCHANGED-FIELDS',r['rule_occurrences']);self.assertNotIn('MEASURED-PARTIAL-FIELDS',r['rule_occurrences'])
        self.assertEqual(r['producer_measurements'][0]['recomputed_from_retained_measurements'],'rolled_back')
    def test_unknown_product_not_mislabeled_gitea(self):
        r=self.read(run_files(product='widget',version='1.0'));self.assertTrue(all(o['product']=='widget' for o in r['observations']))
        self.assertFalse(any(k.startswith('GIT-') for k in r['rule_occurrences']))
    def test_missing_expected_seed(self):
        r=self.read({'ENV_v1_model.txt':b'sut=gitea\nseeds=1,2\n','review_v1_s1.zip':pack(run_files())})
        self.assertIn('SEED_ARCHIVE_MISSING',[g['code'] for g in r['toolkit_coverage_gaps']])
    def test_embedded_sut_configuration_in_outer_package(self):
        config=json.dumps({'name':'gitea','logs':{'error_pattern':'[E]','request_pattern':'router: completed','http500_pattern':' 500 Internal Server Error'}}).encode()
        r=self.read({'ENV_v1_model.txt':b'sut=gitea\nseeds=1\n','sut.json':config,'review_v1_s1.zip':pack(run_files())})
        self.assertNotIn('SUT_CONFIGURATION_MISSING',[g['code'] for g in r['toolkit_coverage_gaps']])
        self.assertEqual(r['runs'][0]['log_pattern_counts']['sut_log_500'],1)
    def test_E5_generic_names_without_gitea_alias(self):
        meta=dict(tool='schemathesis',sut_version='1.0',sut_log_completed_requests=1,sut_log_500=1,sut_log_E=1,sut_log_reach=0)
        conf={'name':'widget','logs':dict(request_pattern='request:',http500_pattern='status 500',error_pattern='error:',reach_regex='unreachable')}
        files={'ENV_v1_baselines.txt':b'sut=widget\nkind=baselines\nsut_version=1.0\n','sut.json':json.dumps(conf).encode(),'schemathesis_rep1/run-meta.json':json.dumps(meta).encode(),'schemathesis_rep1/sut.log':b'request: status 500 error: failure\n','schemathesis_rep1/report-round1/junit-test.xml':b'<testsuite><testcase name="x"><failure/></testcase></testsuite>'}
        r=self.read(files);self.assertEqual(r['runs'][0]['product'],'widget');self.assertEqual(r['observations'][0]['facts']['native_failed_testcases'],1)
        self.assertFalse(any(k.startswith('GIT-') for k in r['rule_occurrences']))
    def test_E5_generic_legacy_alias_conflict_rejected(self):
        meta={'tool':'evomaster','sut_version':'28.1.0','gitea':'9.0'}
        with self.assertRaisesRegex(ValueError,'aliases conflict'):
            self.read({'ENV_v1_baselines.txt':b'sut=gitea','evomaster_rep1/run-meta.json':json.dumps(meta).encode(),'evomaster_rep1/sut.log':b''})
    def test_config_pin_rejected(self):
        p=self.root/'sut.json';p.write_text('{"name":"gitea"}')
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):self.read(run_files(),sut_config=p,sut_config_sha256='0'*64)
    def test_local_git_config_uses_recorded_commit_not_checkout(self):
        import subprocess
        repo=self.root/'producer';repo.mkdir()
        def git(*args):
            p=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);return p.stdout.strip()
        git('init');conf=repo/'toolkit/v1/configs/gitea/sut.json';conf.parent.mkdir(parents=True)
        conf.write_text(json.dumps({'name':'gitea','logs':{}}));git('add','.')
        git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture');head=git('rev-parse','HEAD')
        conf.write_text('{"name":"wrong-checkout"}')
        r=self.read({'ENV_v1_model.txt':('sut=gitea\ngit_head='+head+'\n').encode(),'review_v1_s1.zip':pack(run_files())},toolkit_repo=repo)
        self.assertEqual(r['toolkit_configurations'][0]['binding'],'verified_local_git_snapshot')
        self.assertEqual(r['toolkit_configurations'][0]['git_head'],head)
    def test_stopped_outer_retains_real_prefix_and_status(self):
        r=self.read({'ENV_v1_campaign.txt':b'sut=gitea\nresult=STOPPED\n','review_v1_s1.zip':pack(run_files(campaign=True))})
        self.assertEqual(r['evidence_summary']['http_records'],3);self.assertIn('PACKAGE_STOPPED',[g['code'] for g in r['toolkit_coverage_gaps']])
    def test_missing_native_version_is_not_guessed(self):
        files=run_files();r=document= json.loads(files['result_v1.json']);r.pop('sut_version');files['result_v1.json']=json.dumps(r).encode();files.pop('manifest_v1.json')
        r=self.read(files);self.assertIsNone(r['runs'][0]['version']);self.assertNotIn('GIT-C2',r['rule_occurrences'])

if __name__=='__main__':unittest.main()
