import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('box',HERE/'natchan.py');box=importlib.util.module_from_spec(spec);spec.loader.exec_module(box)

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.evidence=self.root/'observations.json'
        self.observation=dict(id='http-1',product='gitea',product_version='28.1.0',tool='provengo',run_id='original',source={'file':'raw.log','sha256':'a'*64,'record':1},method='PATCH',path='/x',status=500)
        self.evidence.write_text(json.dumps({'schema_version':'natchan-observations/1','observations':[self.observation]}))
        self.request={'schema_version':'natchan-request/1','run':{'id':'pipeline-1','product':'gitea','product_version':'28.1.0','tool':'provengo'},'evidence':{'adapter':'normalized-observations','observations':'observations.json'}}
        self.path=self.root/'request.json'
    def invoke(self):
        self.path.write_text(json.dumps(self.request));return box.run(self.path,self.root/'output')
    def test_actual_classifier_and_output_protocol(self):
        r=self.invoke();self.assertEqual(r['exit_code'],0);self.assertEqual(r['status'],'COMPLETE')
        self.assertGreater(r['counts']['finding_occurrences'],0)
        self.assertEqual(r['counts']['known_bug_occurrences'],0)
        for name,meta in r['artifacts'].items():self.assertEqual(box.sha(self.root/'output'/name),meta['sha256'])
        self.assertEqual(r['new_sut_requests'],0)
    def test_unknown_adapter(self):
        self.request['evidence']['adapter']='restler-arbitrary';r=self.invoke();self.assertEqual(r['exit_code'],3);self.assertEqual(r['status'],'FAILED')
    def test_unsupported_schema(self):
        self.request['schema_version']='natchan-request/99';self.assertEqual(self.invoke()['exit_code'],3)
    def test_unknown_request_field(self):
        self.request['guess']=True;self.assertEqual(self.invoke()['exit_code'],2)
    def test_missing_evidence(self):
        self.evidence.unlink();self.assertEqual(self.invoke()['exit_code'],2)
    def test_hash_pin(self):
        self.request['evidence']['sha256']='0'*64;self.assertEqual(self.invoke()['exit_code'],2)
    def test_hash_pin_positive(self):
        self.request['evidence']['sha256']=box.sha(self.evidence);self.assertEqual(self.invoke()['exit_code'],0)
    def test_version_conflict(self):
        self.request['run']['product_version']='9.9.9';self.assertEqual(self.invoke()['exit_code'],2)
    def test_tool_conflict(self):
        self.request['run']['tool']='evomaster';self.assertEqual(self.invoke()['exit_code'],2)
    def test_product_conflict(self):
        self.request['run']['product']='vikunja';self.assertEqual(self.invoke()['exit_code'],2)
    def test_duplicate_keys(self):
        self.path.write_text('{"run":{},"run":{}}');r=box.run(self.path,self.root/'output');self.assertEqual(r['exit_code'],2)
    def test_invalid_json_preserves_diagnostics(self):
        self.path.write_text('{');r=box.run(self.path,self.root/'output');self.assertEqual(r['exit_code'],2);self.assertTrue((self.root/'output/diagnostics.json').exists())
    def test_refuse_overwrite(self):
        self.invoke()
        with self.assertRaises(box.InputError):box.run(self.path,self.root/'output')
    def test_engine_failure_is_not_zero_findings_success(self):
        with patch.object(box,'execute',side_effect=box.EngineError('failure')):r=self.invoke()
        self.assertEqual(r['exit_code'],4);self.assertEqual(r['status'],'FAILED');self.assertNotIn('counts',r)
    def test_input_mutation_rejected(self):
        original=box.execute
        def mutate(*args):
            report,engine=original(*args);self.evidence.write_text('{}');return report,engine
        with patch.object(box,'execute',side_effect=mutate):r=self.invoke()
        self.assertEqual(r['exit_code'],2)
    def test_no_evidence_inside_output(self):
        self.path.write_text(json.dumps(self.request))
        with self.assertRaises(box.InputError):box.run(self.path,self.root)
    def test_missing_profile_not_silent_default(self):
        self.request['configuration']={'profile':'missing.json'};self.assertEqual(self.invoke()['exit_code'],3)
    def test_mixed_requires_no_conflicting_assertion(self):
        self.request['run']['tool']='mixed';self.assertEqual(self.invoke()['exit_code'],0)
    def test_imported_semantic_label_does_not_create_known_bug(self):
        self.observation.update(status=200,facts={'correlated_error_family':'missing_milestone','server_error':True},known_bugs=['GIT-C2'])
        self.evidence.write_text(json.dumps({'schema_version':'natchan-observations/1','observations':[self.observation]}))
        self.assertEqual(self.invoke()['counts']['known_bug_occurrences'],0)
    def test_historical_corpus_uses_real_raw_gateway(self):
        archive=self.root/'review_synthetic.zip'
        row={'category':'research','method':'PATCH','path':'/repos/a/r/issues/1','status':500,'input':{'milestone':123},'response':{'message':'error'},'action':'update','logical_id':'Issue_probe'}
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('gateway-journal.jsonl',json.dumps(row)+'\n')
            z.writestr('generated/contract-ir.json',json.dumps({'entities':[{'name':'Issue','path':'/repos/{owner}/{repo}/issues','detail':'/repos/{owner}/{repo}/issues/{index}','create_method':'post','update_method':'patch','update_schema':{'properties':{'milestone':{'type':'integer'}}}}]}))
            z.writestr('result_test.json',json.dumps({'sut_version':'28.1.0','requests':1,'status':'COMPLETED'}))
            z.writestr('native.log','INFO [RUN synthetic fixture')
        manifest={'schema_version':'natchan-corpus/1','datasets':[{'id':'synthetic','adapter':'gitea-review-bundle','path':archive.name}],'locked_sources':[{'path':archive.name,'sha256':box.sha(archive)}]}
        (self.root/'corpus.json').write_text(json.dumps(manifest))
        self.request['evidence']={'adapter':'historical-corpus','manifest':'corpus.json','root':'.'}
        r=self.invoke();self.assertEqual(r['exit_code'],0)
        self.assertEqual(r['counts']['known_bug_occurrences'],0)
        self.assertTrue((self.root/'output/engine-report.html').exists())
        self.assertGreater(r['counts']['finding_occurrences'],0)
    def test_missing_server_log_is_partial(self):
        archive=self.root/'native.zip'
        version={'method':'GET','path':'/version','status':200,'response':{'version':'28.1.0'},'actor':'A','group':'global','role':'version'}
        with zipfile.ZipFile(archive,'w') as z:z.writestr('native.log','SHARED_EVIDENCE '+json.dumps(version)+'\n')
        self.request['evidence']={'adapter':'provengo-native-lifecycle','archive':archive.name}
        r=self.invoke();self.assertEqual(r['exit_code'],0);self.assertEqual(r['status'],'PARTIAL')
        self.assertIn('SERVER_LOG_MISSING',[x['code'] for x in box.read(self.root/'output/coverage.json')['gaps']])
    def test_zip_windows_paths_and_traversal(self):
        z=self.root/'test.zip'
        with zipfile.ZipFile(z,'w') as f:f.writestr('rep1\\run-meta.json','{}')
        box.unpack(z,self.root/'unpacked');self.assertTrue((self.root/'unpacked/rep1/run-meta.json').exists())
        with zipfile.ZipFile(z,'w') as f:f.writestr('../escaped','x')
        with self.assertRaises(box.InputError):box.unpack(z,self.root/'unsafe')
    def test_zip_case_collision(self):
        z=self.root/'test.zip'
        with zipfile.ZipFile(z,'w') as f:f.writestr('A.txt','a');f.writestr('a.txt','b')
        with self.assertRaises(box.InputError):box.unpack(z,self.root/'unsafe')
    def test_output_not_created_inside_evidence(self):
        self.request['evidence']={'adapter':'gitea-native-tools','directory':'.'};self.request['run']['tool']='evomaster'
        self.path.write_text(json.dumps(self.request))
        with self.assertRaises(box.InputError):box.run(self.path,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

if __name__=='__main__':unittest.main()

