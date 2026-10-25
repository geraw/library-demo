import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import toolkit_adapter as tk
from login_evidence import fingerprint,lock_links,retained_equal
from toolkit_formats import UnsupportedEvidence


def pack(files):
    s=io.BytesIO()
    with zipfile.ZipFile(s,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in files.items():z.writestr(name,raw if isinstance(raw,(str,bytes)) else json.dumps(raw))
    return s.getvalue()


def fixture(status='V1_LOGIN_SAMPLE_COMPLETED',encoding='utf-16'):
    # Deliberately tiny FORMAT fixture, not reconstructed 1369-request work evidence.
    c=dict(category='research',session='A',t_utc='2026-10-25T10:54:28.000Z')
    rows=[dict(c,action='authenticate',method='POST',path='/login',input={'credentials':'[REDACTED]'},status=200,response='{"token":"[REDACTED]"}'),
          dict(c,action='create',logical_id='task',method='PUT',path='/projects/1/tasks',input={'title':'x'},status=201,response='{"id":9,"title":"x"}'),
          dict(c,action='create',logical_id='opaque-view',method='PUT',path='/projects/1/views',input={'title':' padded '},status=201,response='{"id":5,"title":"padded"}'),
          dict(category='roundtrip-check',session='A',action='create',logical_id='opaque-view',method='PUT',path='/projects/1/views',type='ModelsProjectView',readback_status=200,fields=['title'],mismatches={'title':{'class':'changed','sent':' padded ','stored':'padded'}},verdict='ok'),
          dict(category='known-failure',session='A',action='update',logical_id='opaque-view',method='POST',path='/projects/1/views/5',status=500,response='Internal Server Error',known_failure='VIK-F01',attempt=1,t_utc='2026-10-25T10:54:29Z'),
          dict(c,action='update',logical_id='opaque-view',method='POST',path='/projects/1/views/5',input={'title':'padded'},status=200,response='{"id":5,"title":"padded"}'),
          dict(c,action='adjacency_probe',logical_id='other-view',method='POST',path='/projects/1/views/6',input={'title':'x'},status=500,response='Internal Server Error',t_utc='2026-10-25T10:54:31Z'),
          dict(category='authentication-validation',session='A',phase='before-checkpoint',status=200,user_id=1),
          dict(category='model-invariant',session='B',case_id='negative-1',phase='BASELINE_EQUAL_BEFORE_CHECKPOINT',baseline_sha256='b'*64),
          dict(category='recovery-phase',session='B',case_id='negative-1',phase='checkpoint-saved',hashes={'db':'a'*64}),
          dict(c,action='negative_attempt',session='B',case_id='negative-1',logical_id='opaque-view',method='POST',path='/projects/1/views/5',input={'title':42},before={'id':5,'title':'padded'},status=400,response='{"message":"Invalid model"}'),
          dict(category='post-write-observation',session='B',case_id='negative-1',path='/projects/1/views/5',status=200,response='{"id":5,"title":"padded"}'),
          dict(category='recovery',session='B',case_id='negative-1',outcome=dict(actual_status=400,prefix_before={'view':{'title':'padded'}},prefix_restored={'view':{'title':'padded'}},api_prefix_equal=True,snapshot_restored=True)),
          dict(category='trap-wait',session='A',ms=5)]
    for i,r in enumerate(rows):r['index']=i
    recovery=rows[12]['outcome'];recovery['prefix_before_sha256']=fingerprint(recovery['prefix_before']);recovery['prefix_restored_sha256']=fingerprint(recovery['prefix_restored'])
    ir=dict(entities=[dict(name='ModelsTask',path='/projects/{project}/tasks',detail='/tasks/{id}',create_method='put',update_method='post',create_schema={'properties':{'title':{'type':'string'}}}),dict(name='ModelsProjectView',path='/projects/{project}/views',detail='/projects/{project}/views/{id}',create_method='put',update_method='post',create_schema={'properties':{'title':{'type':'string'}}},update_schema={'properties':{'title':{'type':'string'}}},read_schema={'properties':{'title':{'type':'string'}}})])
    coverage=dict(planned_workflows=2,completed_workflows=2,selected_negative_cases=[{'case_id':'negative-1'}],completed_negative_case_ids=['negative-1'],selected_not_completed=[],stable_boundary=True,complete_selected_model=True,full_contract_coverage=False)
    result=dict(version='v1-login',sut='vikunja',run_seed=1,fixture_seed=1,status=status,native_execution=True,live_execution=True,native_exit=0,recorded_http_requests=sum(r['category']=='research' for r in rows),coverage=coverage,negative_checks=[dict(caseId='negative-1',pass_=True)],findings=[])
    conf=dict(name='vikunja',api=dict(base_path='/api/v1',expected_version='v2.6.0'),logs=dict(locked_pattern='database is locked|poisoned'))
    files={'sut.json':json.dumps(conf).encode(),'native.log':b'INFO Test Result: SUCCESS','generated/contract-ir.json':json.dumps(ir).encode(),'result_v1.json':json.dumps(result).encode(),'coverage_v1.json':json.dumps(coverage).encode(),'gateway-journal.jsonl':('\n'.join(json.dumps(r) for r in rows)+'\n').encode(),'snapshot-adapter.json':b'{"kind":"WINDOWS_BIND_COLD_COPY_V023"}','recovery-ledger.json':json.dumps([recovery]).encode(),'restore-verification-v010.json':b'{"strict_equality":true}'}
    files['manifest_v1.json']=json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in files.items()}).encode()
    log='time=2026-10-25T10:54:29Z level=ERROR method=POST uri=/api/v1/projects/1/views/5 status=500 latency=1ms err="database is locked"\ntime=2026-10-25T10:54:31Z level=ERROR method=POST uri=/api/v1/projects/1/views/6 status=500 latency=1ms err="database is locked"\n'
    outer={'sut.json':files['sut.json'],'ENV_v1_login.txt':'sut=vikunja\nkind=login\nsut_version=v2.6.0\nseeds=1\nseed1_locked_lines=2\nresult=V1_LOGIN_MODEL_COMPLETE\n'.encode(encoding),'result_v1_s1.json':files['result_v1.json'],'review_v1_s1.zip':pack(files),'sut_locked_s1.txt':log.encode(encoding)}
    return outer,files,rows


def change(outer,files,rows=None):
    if rows is not None:files['gateway-journal.jsonl']=('\n'.join(map(json.dumps,rows))+'\n').encode()
    files['manifest_v1.json']=json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in files.items() if k!='manifest_v1.json'}).encode()
    outer['review_v1_s1.zip']=pack(files);outer['result_v1_s1.json']=files['result_v1.json'];return outer


class LoginTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def read(self,outer):
        path=self.root/'evidence.zip';path.write_bytes(pack(outer));return tk.Reader(path).finish()
    def cli(self,outer,product='vikunja',version='v2.6.0'):
        archive=self.root/'input.zip';archive.write_bytes(pack(outer));request=self.root/'request.json'
        request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='test',tool='provengo',product=product,product_version=version),evidence=dict(adapter='toolkit-v1',archive=str(archive)))))
        out=self.root/'output';p=subprocess.run([sys.executable,str(ROOT/'natchan.py'),'--request',str(request),'--output',str(out)],capture_output=True,text=True)
        return p,json.loads((out/'result.json').read_text()),out
    def test_utf16_outer_metadata_and_version_from_env(self):
        d=self.read(fixture()[0]);self.assertEqual(d['runs'][0]['version'],'v2.6.0');self.assertEqual(d['runs'][0]['seed'],1)
        self.assertNotIn('SUT_VERSION_UNKNOWN',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_isolated_subprocess_never_depends_on_gitea_import_side_effects(self):
        p,result,out=self.cli(fixture()[0]);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(result['wrapper_version'],'natchan-box/5.0.0');self.assertEqual(result['status'],'PARTIAL')
        self.assertNotIn('tse_products',(out/'diagnostics.json').read_text())
    def test_recorded_retries_are_not_extra_research_responses(self):
        d=self.read(fixture()[0]);self.assertEqual(d['evidence_summary']['http_records'],6);self.assertEqual(d['runs'][0]['recorded_retry_attempts'],1)
        self.assertEqual(d['runs'][0]['http_5xx'],1);self.assertEqual(d['runs'][0]['retry_attempt_5xx'],1)
        self.assertEqual(d['rule_occurrences']['GEN-SERVER_ERROR'],2)
    def test_filtered_log_is_not_treated_as_missing_or_full(self):
        d=self.read(fixture()[0]);g=[g['code'] for g in d['toolkit_coverage_gaps']]
        self.assertIn('SERVER_LOG_FILTERED_ONLY',g);self.assertNotIn('SERVER_LOG_MISSING',g)
        self.assertFalse(d['runs'][0]['full_server_http_totals_available']);self.assertNotIn('sut_log_completed_requests',d['runs'][0]['log_pattern_counts'])
    def test_controls_do_not_become_unsupported_or_http(self):
        d=self.read(fixture()[0]);self.assertFalse(any(g.get('code')=='UNSUPPORTED_JOURNAL_CATEGORY' for g in d['toolkit_coverage_gaps']))
        self.assertEqual(d['evidence_summary']['http_records'],6)
    def test_rt_recomputes_difference_despite_forged_ok_verdict(self):
        d=self.read(fixture()[0]);self.assertEqual(d['rule_occurrences']['GEN-SILENT_CHANGE'],1)
        o=next(o for o in d['observations'] if o['facts'].get('silent_change'))
        self.assertEqual(o['evidence_tier'],'producer_readback_values');self.assertFalse(o['facts']['roundtrip_full_state_verified'])
    def test_rt_readonly_or_unreadable_field_is_not_promoted(self):
        for mode in ('readonly','unreadable'):
            outer,files,rows=fixture();ir=json.loads(files['generated/contract-ir.json'])
            if mode=='readonly':ir['entities'][1]['create_schema']['properties']['title']['readOnly']=True
            else:ir['entities'][1].pop('read_schema')
            files['generated/contract-ir.json']=json.dumps(ir).encode();d=self.read(change(outer,files,rows))
            self.assertNotIn('GEN-SILENT_CHANGE',d['rule_occurrences']);self.assertIn('ROUNDTRIP_FIELD_SCHEMA_NOT_QUALIFIED',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_multi_seed_log_sources_are_kept_separate(self):
        outer,files,rows=fixture();files2=copy.deepcopy(files);rows2=copy.deepcopy(rows);rows2[0]['input']['seed_witness']=2
        r=json.loads(files2['result_v1.json']);r['run_seed']=2;files2['result_v1.json']=json.dumps(r).encode()
        second={};change(second,files2,rows2)
        outer['review_v1_s2.zip']=second['review_v1_s1.zip'];outer['result_v1_s2.json']=files2['result_v1.json'];outer['sut_locked_s2.txt']=outer['sut_locked_s1.txt']
        outer['ENV_v1_login.txt']='sut=vikunja\nkind=login\nsut_version=v2.6.0\nseeds=1,2\nseed1_locked_lines=2\nseed2_locked_lines=2\nresult=V1_LOGIN_MODEL_COMPLETE\n'.encode('utf-16')
        d=self.read(outer);self.assertEqual(len(d['runs']),2);self.assertEqual(d['evidence_summary']['http_records'],12)
        logs=[r['filtered_server_log_source']['members'][-1] for r in d['runs']];self.assertEqual(logs,['sut_locked_s1.txt','sut_locked_s2.txt'])
    def test_repeated_writes_bind_to_their_own_immediately_preceding_exchange(self):
        outer,files,rows=fixture();raw=copy.deepcopy(rows[2]);rt=copy.deepcopy(rows[3]);raw['index']=14;rt['index']=15
        rows.extend([raw,rt]);r=json.loads(files['result_v1.json']);r['recorded_http_requests']+=1;files['result_v1.json']=json.dumps(r).encode()
        d=self.read(change(outer,files,rows));self.assertEqual(d['rule_occurrences']['GEN-SILENT_CHANGE'],2)
    def test_rt_unbound_measurement_stays_gap(self):
        outer,files,rows=fixture();rows[3]['session']='B';d=self.read(change(outer,files,rows))
        self.assertNotIn('GEN-SILENT_CHANGE',d['rule_occurrences']);self.assertIn('ROUNDTRIP_MEASUREMENT_UNBOUND_OR_UNREADABLE',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_rt_sent_mismatch_is_contradiction(self):
        outer,files,rows=fixture();rows[3]['mismatches']['title']['sent']='wrong';d=self.read(change(outer,files,rows));self.assertNotIn('GEN-SILENT_CHANGE',d['rule_occurrences'])
        self.assertIn('ROUNDTRIP_MEASUREMENT_CONTRADICTION',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_rt_equal_retained_values_do_not_force_finding(self):
        outer,files,rows=fixture();rows[3]['mismatches']['title']['stored']=' padded ';d=self.read(change(outer,files,rows));self.assertNotIn('GEN-SILENT_CHANGE',d['rule_occurrences'])
    def test_literal_v_version_retained_with_audited_catalog_alias(self):
        d=self.read(fixture()[0]);self.assertEqual(d['rule_occurrences']['VIK-F01'],2)
        self.assertTrue(all(o['product_version']=='v2.6.0' for o in d['observations']));self.assertEqual(d['catalog_version_aliases'][0]['catalog'],'2.6.0')
    def test_reported_known_id_alone_does_not_match_known_bug(self):
        outer,files,rows=fixture();outer.pop('sut_locked_s1.txt');d=self.read(outer);self.assertNotIn('VIK-F01',d['rule_occurrences']);self.assertIn('GEN-SERVER_ERROR',d['rule_occurrences'])
    def test_recovery_prefix_hashes_and_status_are_recomputed(self):
        d=self.read(fixture()[0]);a=next(x for x in d['login_evidence_audit'] if x['category']=='recovery');self.assertTrue(a['prefix_equal']);self.assertFalse(a['storage_restore_independently_verified'])
    def test_recovery_forged_hash_not_accepted(self):
        outer,files,rows=fixture();rows[12]['outcome']['prefix_before_sha256']='0'*64;d=self.read(change(outer,files,rows));self.assertIn('RECOVERY_PREFIX_HASH_CONTRADICTION',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_recovery_equal_flag_not_trusted(self):
        outer,files,rows=fixture();rows[12]['outcome']['api_prefix_equal']=False;d=self.read(change(outer,files,rows));self.assertIn('RECOVERY_PREFIX_EQUALITY_CONTRADICTION',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_recovery_missing_prefix_not_inferred(self):
        outer,files,rows=fixture();rows[12]['outcome'].pop('prefix_before');d=self.read(change(outer,files,rows));self.assertIn('RECOVERY_PREFIX_BODIES_MISSING',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_already_accepted_sample_not_labeled_run_incomplete(self):
        d=self.read(fixture()[0]);self.assertNotIn('RUN_NOT_COMPLETED',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_budget_cutoff_is_supported_partial_evidence(self):
        d=self.read(fixture('V1_LOGIN_TIME_BUDGET_STABLE_PARTIAL')[0]);self.assertIn('TIME_BUDGET_SELECTED_PREFIX',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_static_ready_is_not_claimed_live(self):
        d=self.read(fixture('V1_LOGIN_STATIC_READY')[0]);self.assertIn('STATIC_ONLY_NO_LIVE_RUN',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_not_accepted_keeps_observed_prefix(self):
        d=self.read(fixture('NOT_ACCEPTED')[0]);self.assertEqual(d['evidence_summary']['http_records'],6);self.assertIn('RUN_NOT_COMPLETED',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_false_completion_flags_leave_gap(self):
        outer,files,rows=fixture();r=json.loads(files['result_v1.json']);r['native_execution']=False;files['result_v1.json']=json.dumps(r).encode();d=self.read(change(outer,files));self.assertIn('NATIVE_COMPLETION_NOT_VERIFIED',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_run_seed_mismatch_rejected(self):
        outer,files,_=fixture();r=json.loads(files['result_v1.json']);r['run_seed']=2;files['result_v1.json']=json.dumps(r).encode()
        with self.assertRaisesRegex(ValueError,'Seed filename'):self.read(change(outer,files))
    def test_recorded_request_count_mismatch_rejected(self):
        outer,files,_=fixture();r=json.loads(files['result_v1.json']);r['recorded_http_requests']=99;files['result_v1.json']=json.dumps(r).encode()
        with self.assertRaisesRegex(ValueError,'request count'):self.read(change(outer,files))
    def test_locked_line_metadata_mismatch_rejected(self):
        outer,_,_=fixture();outer['sut_locked_s1.txt']=b''
        with self.assertRaisesRegex(ValueError,'locked-line count'):self.read(outer)
    def test_coverage_copies_disagree_rejected(self):
        outer,files,_=fixture();files['coverage_v1.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'coverage copies'):self.read(change(outer,files))
    def test_unknown_package_kind_returns_exit3(self):
        p,r,out=self.cli({'ENV_v1_future.txt':b'sut=vikunja\nkind=future\n'});self.assertEqual(p.returncode,3);self.assertEqual(r['exit_code'],3);self.assertIn('UNSUPPORTED_INPUT',(out/'diagnostics.json').read_text())
    def test_unknown_run_version_returns_exit3(self):
        outer,files,_=fixture();r=json.loads(files['result_v1.json']);r['version']='v77-login';files['result_v1.json']=json.dumps(r).encode();p,r,out=self.cli(change(outer,files));self.assertEqual(p.returncode,3)
    def test_unknown_login_status_returns_exit3(self):
        p,r,_=self.cli(fixture('V1_LOGIN_FUTURE')[0]);self.assertEqual(p.returncode,3)
    def test_internal_engine_error_is_not_hidden_as_unsupported(self):
        import natchan
        from unittest.mock import patch
        with patch.object(natchan.subprocess,'run',return_value=subprocess.CompletedProcess([],4,'','ModuleNotFoundError')):
            with self.assertRaises(natchan.EngineError):natchan.launch(['toolkit_adapter.py'])
    def test_bare_login_does_not_guess_version_from_expected_config(self):
        _,files,_=fixture();d=self.read(files);self.assertIsNone(d['runs'][0]['version']);self.assertIn('SUT_VERSION_UNKNOWN',[g['code'] for g in d['toolkit_coverage_gaps']])
    def test_bare_unknown_product_subprocess_import_is_fixed(self):
        # This path previously passed in-process tests only after a Gitea import polluted sys.path.
        files={'result_v1.json':json.dumps(dict(version='v1',sut='widget',sut_version='1',seed=1,status='COMPLETED',native_exit=0,requests=1)),
               'gateway-journal.jsonl':json.dumps(dict(category='research',method='GET',path='/widgets/1',status=500,input=None,response='{}')),'native.log':'Test Result: SUCCESS','generated/contract-ir.json':'{}','sut.json':'{"name":"widget","logs":{}}'}
        p,r,_=self.cli(files,'widget','1');self.assertEqual(p.returncode,0,p.stderr)
    def test_unique_log_time_join_and_ambiguity(self):
        rows=[dict(category='research',method='POST',path='/x',status=500,t_utc='2026-10-25T10:00:00Z')]
        log='time=2026-10-25T10:00:00Z method=POST uri=/api/v1/x status=500 err="database is locked"'
        self.assertEqual(len(lock_links(rows,log,'/api/v1')),1)
        self.assertEqual(lock_links(rows+copy.deepcopy(rows),log,'/api/v1'),{})
        self.assertEqual(lock_links(rows,log+'\n'+log,'/api/v1'),{})
    def test_rt_normalizes_instants_and_request_object_keys(self):
        self.assertTrue(retained_equal('2026-10-25T12:00:00+02:00','2026-10-25T10:00:00Z'))
        self.assertTrue(retained_equal({'x':1},{'x':1.0,'server':99}))
        self.assertFalse(retained_equal(True,1));self.assertFalse(retained_equal([1,2],[2,1]))
    def test_infrastructure_and_failed_auth_are_visible_gaps(self):
        outer,files,rows=fixture();rows[7]['status']=401;rows.append(dict(category='infrastructure-error',error='timeout',index=14))
        d=self.read(change(outer,files,rows));codes=[g['code'] for g in d['toolkit_coverage_gaps']]
        self.assertIn('AUTHENTICATION_VALIDATION_FAILED',codes);self.assertIn('RECORDED_TRANSPORT_OR_ORACLE_ERROR',codes)
    def test_unrelated_or_timeless_log_not_assigned(self):
        rows=[dict(category='research',method='POST',path='/x',status=500,t_utc='2026-10-25T10:00:00Z')]
        self.assertEqual(lock_links(rows,'time=2026-10-25T10:00:05Z method=POST uri=/api/v1/x status=500 err="database is locked"','/api/v1'),{})

if __name__=='__main__':unittest.main()
