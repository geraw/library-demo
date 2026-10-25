import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import work_v001 as w


def zip_bytes(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,value in files.items():z.writestr(name,value if isinstance(value,(str,bytes)) else json.dumps(value))
    return stream.getvalue()


def package(path, *, stopped=False, count=1, jar=None, version='28.1.0'):
    files={'ENV_v1_model.txt':'sut=gitea\nkind=model\nresult='+('STOPPED' if stopped else 'V1_MODEL_COMPLETE')+'\nsut_version=28.1.0\n'}
    if not stopped:
        rows=[dict(index=0,category='research',status=500),dict(index=1,category='atomicity-check',snapshots={'format':'atom-snapshots/1'}),dict(index=2,category='divergence-check',evidence_format='div-evidence/1')]
        files['review_v1_s1.zip']=zip_bytes({'result_v1.json':dict(requests=count,sut='gitea',sut_version=version,seed=1,jar_sha256=jar or w.PINS['provengo_jar_sha256'],status='STOPPED_AT_FIRST_FAILURE',native_exit=1),'gateway-journal.jsonl':'\n'.join(map(json.dumps,rows))})
    path.write_bytes(zip_bytes(files));return path


class WorkTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_inspects_nested_model_evidence(self):
        p=package(self.root/'model.zip');d=w.inspect_package(p)
        self.assertEqual(d['runs'][0]['http_records'],1);self.assertEqual(d['runs'][0]['atom_snapshots_v1'],1);self.assertEqual(d['runs'][0]['div_evidence_v1'],1)
        self.assertTrue(d['runs'][0]['frozen_jar_hash_matches']);self.assertEqual(d['package_sha256'],w.sha(p))
    def test_stopped_is_missing_evidence_not_zero_findings(self):
        d=w.inspect_package(package(self.root/'model.zip',stopped=True));self.assertTrue(d['no_run_evidence']);self.assertEqual(d['runs'],[]);self.assertNotIn('findings',d)
    def test_request_count_mismatch_fails(self):
        with self.assertRaisesRegex(w.IntegrationError,'count disagreement'):w.inspect_package(package(self.root/'m.zip',count=9))
    def test_version_conflict_fails(self):
        with self.assertRaisesRegex(w.IntegrationError,'more than one'):w.inspect_package(package(self.root/'m.zip',version='29'))
    def test_harness_jar_not_accepted_as_frozen(self):
        d=w.inspect_package(package(self.root/'m.zip',jar='0'*64))
        self.assertFalse(d['runs'][0]['frozen_jar_hash_matches']);self.assertEqual(w.native_assessment('native-provengo-model',d),'NOT_CONFIRMED_JAR_MISMATCH')
    def test_existing_package_does_not_claim_observed_execution(self):
        d=w.inspect_package(package(self.root/'m.zip'));self.assertEqual(w.native_assessment('existing-package',d),'NOT_ASSERTED_EXISTING_PACKAGE')
    def test_native_prefix_not_mislabeled_complete_schedule(self):
        d=w.inspect_package(package(self.root/'m.zip'));self.assertEqual(w.native_assessment('native-provengo-model',d),'NATIVE_PREFIX_RECORDED')
        d['runs'][0]['native_status']='NATIVE_ERROR';self.assertEqual(w.native_assessment('native-provengo-model',d),'INCOMPLETE_NATIVE_EXECUTION')
    def test_expansion_budget_enforced(self):
        p=package(self.root/'m.zip')
        with patch.object(w,'MAX_BYTES',1),self.assertRaisesRegex(w.IntegrationError,'limit exceeded'):w.inspect_package(p)
    def test_only_exact_new_package_selected(self):
        a,b=self.root/'a',self.root/'b';self.assertEqual(w.new_package([a],[a,b]),b)
    def test_missing_package_cannot_reuse_old_file(self):
        with self.assertRaises(w.IntegrationError):w.new_package(['old'],['old'])
    def test_two_new_packages_are_ambiguous(self):
        with self.assertRaises(w.IntegrationError):w.new_package([],['a','b'])
    def output(self):
        out=self.root/'output';out.mkdir();w.write(out/'coverage.json',dict(gaps=[]))
        result=dict(wrapper_version='natchan-box/4.0.0',status='PARTIAL',exit_code=0,artifacts={'coverage.json':dict(path='coverage.json',sha256=w.sha(out/'coverage.json'))})
        w.write(out/'result.json',result);return out
    def test_result_hash_and_version_verified(self):self.assertEqual(w.check_result(self.output(),0)['status'],'PARTIAL')
    def test_missing_final_marker_is_failure(self):
        with self.assertRaises(w.IntegrationError):w.check_result(self.root,0)
    def test_modified_output_rejected(self):
        out=self.output();(out/'coverage.json').write_text('{}')
        with self.assertRaisesRegex(w.IntegrationError,'artifact hash'):w.check_result(out,0)
    def test_artifact_outside_output_rejected(self):
        out=self.output();external=self.root/'secret';external.write_text('x');r=w.read(out/'result.json');r['artifacts']['bad']=dict(path='../secret',sha256=w.sha(external));w.write(out/'result.json',r)
        with self.assertRaises(w.IntegrationError):w.check_result(out,0)
    def test_exit_code_disagreement_rejected(self):
        with self.assertRaises(w.IntegrationError):w.check_result(self.output(),4)
    def export_inputs(self):
        out=self.output();w.write(out/'provenance.json',{'local_path':r'C:\Users\someone\private\file.json'})
        result=w.read(out/'result.json');result['artifacts']['provenance.json']=dict(path='provenance.json',sha256=w.sha(out/'provenance.json'));w.write(out/'result.json',result)
        p=package(self.root/'model.zip');rc=self.root/'run-config.local.json';w.write(rc,{'token':'must-never-be-exported'})
        w.write(self.root/'analysis-request.json',{'evidence':{'adapter':'toolkit-v1','archive':str(p),'sha256':w.sha(p)},'configuration':{'toolkit_repo':'private'}})
        w.write(self.root/'integration-status.json',{'state':'ANALYZED'});return p,rc
    def test_export_keeps_originals_and_rehashes_sanitized_copy(self):
        p,rc=self.export_inputs();before=w.sha(self.root/'output/result.json')
        with patch.object(w,'command') as call:bundle=w.make_share(self.root,p,rc,[(r'C:\Users\someone','<profile>')])
        self.assertEqual(w.sha(self.root/'output/result.json'),before);self.assertTrue(bundle.is_file())
        copied=w.read(self.root/'share/analysis/output/provenance.json');self.assertIn('<profile>',copied['local_path']);self.assertNotIn('someone',copied['local_path'])
        self.assertEqual(w.check_result(self.root/'share/analysis/output',0)['status'],'PARTIAL')
        self.assertIn('--run-config',call.call_args.args[0]);self.assertEqual(call.call_args.args[0][-1],self.root/'share')
        with zipfile.ZipFile(bundle) as z:
            self.assertEqual(z.read('evidence/model.zip'),p.read_bytes());self.assertNotIn('run-config.local.json',z.namelist())
            self.assertFalse(any('console' in n for n in z.namelist()))
    def test_failed_leak_check_never_produces_upload_zip(self):
        p,rc=self.export_inputs()
        with patch.object(w,'command',side_effect=w.IntegrationError('leak')),self.assertRaises(w.IntegrationError):w.make_share(self.root,p,rc,[])
        self.assertFalse((self.root/'natchan-work-v001-review.zip').exists())
    def test_checkout_uses_new_detached_worktree(self):
        original=self.root/'repo';(original/'.git').mkdir(parents=True);pin=w.PINS['producer']
        def fake(args,**kw):
            text=pin['repository'] if 'get-url' in args else pin['commit'] if 'rev-parse' in args else ''
            return subprocess.CompletedProcess(args,0,text+'\n' if text else '', '')
        with patch.object(w,'command',side_effect=fake) as call:w.checkout(original,pin,self.root/'new')
        commands=[c.args[0] for c in call.call_args_list];self.assertTrue(any('worktree' in c and '--detach' in c for c in commands));self.assertFalse(any('reset' in c or 'checkout' in c for c in commands))
    def test_wrong_remote_cannot_mutate_checkout(self):
        original=self.root/'repo';(original/'.git').mkdir(parents=True)
        with patch.object(w,'command',return_value=subprocess.CompletedProcess([],0,'https://other/repo.git\n','')) as call,self.assertRaises(w.IntegrationError):w.checkout(original,w.PINS['producer'],self.root/'new')
        self.assertEqual(call.call_count,1)
    def test_experiment_lock_prevents_second_launcher(self):
        with w.experiment_lock(self.root):
            with self.assertRaises(w.IntegrationError):
                with w.experiment_lock(self.root):pass
        self.assertFalse((self.root/'work-v001-active.lock').exists())
    def test_interrupt_keeps_experiment_lock_for_producer_cleanup(self):
        with self.assertRaises(KeyboardInterrupt):
            with w.experiment_lock(self.root):raise KeyboardInterrupt()
        self.assertTrue((self.root/'work-v001-active.lock').exists())
    def test_normal_failure_releases_experiment_lock(self):
        with self.assertRaises(w.IntegrationError):
            with w.experiment_lock(self.root):raise w.IntegrationError('before producer start')
        self.assertFalse((self.root/'work-v001-active.lock').exists())
    def test_timeout_does_not_echo_argv(self):
        with patch.object(w.subprocess,'run',side_effect=subprocess.TimeoutExpired(['safe','secret'],1)):
            try:w.command(['safe','secret'])
            except w.IntegrationError as exc:self.assertNotIn('secret',str(exc))
            else:self.fail('Expected timeout')
    def test_streaming_preserves_child_exit_and_local_log(self):
        p=self.root/'console.log';code=w.stream_package([sys.executable,'-c','print("LOCAL_PROGRESS")'],self.root,dict(w.os.environ),p)
        self.assertEqual(code,0);self.assertIn('LOCAL_PROGRESS',p.read_text())

if __name__=='__main__':unittest.main()
