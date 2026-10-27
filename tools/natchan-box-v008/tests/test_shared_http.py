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

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import test_semantic_stories as fixtures
import test_stories as old
import test_login as login
from http_evidence import TrafficReader,restler_records
from toolkit_formats import InvalidEvidence,UnsupportedEvidence
from log_correlation import correlate
import natchan as box


def payload(rows,tool='evomaster'):
    cleaned=[{k:v for k,v in r.items() if k not in ('logical_id','action','category','index')} for r in rows]
    return dict(schema_version='natchan-http-evidence/1',sut='widget',tool=tool,contract_sha256=fixtures.HASH,records=cleaned)


def contribution(broken=True):
    spec=fixtures.metadata();spec['projections']=[]
    spec['contributions']=[dict(method='POST',action_template='/folders/{folder}/add/{source}',source_template='/sources/{id}',container_template='/folders/{id}',container_bindings={'id':'folder'},source_bindings={},source_action_parameter='source',source_id_field='id',scale_field='factor',quantity='qty',source_items='$.items[]',container_items='$.items[]',source_keys=[['key']],container_keys=[['key']],sign=1)]
    steps=[('GET','/sources/7',None,200,dict(id=7,items=[dict(key='K',qty=2),dict(key='K',qty=2)]),'source'),('GET','/folders/101',None,200,dict(id=101,items=[dict(key='K',qty=13)]),'before'),('POST','/folders/101/add/7',dict(factor=0.5),200,{},'act'),('GET','/folders/101',None,200,dict(id=101,items=[dict(key='K',qty=16 if broken else 15)]),'after')]
    return fixtures.rows_from(steps,'CONTRIB_source_folder'),spec


def copying(broken=True):
    spec=fixtures.metadata();spec['projections']=[];spec['copies']=[dict(method='POST',action_template='/sources/{id}/copy',source_template='/sources/{id}',source_bindings={'id':'id'},identity_items='$.parts[]',reference_items='$.steps[].refs[]',field='key')]
    source=dict(id=7,parts=[dict(key='a')],steps=[dict(refs=[dict(key='a')])]);new=dict(id=8,parts=[dict(key='b')],steps=[dict(refs=[dict(key='a' if broken else 'b')])])
    steps=[('GET','/sources/7',None,200,source,'source'),('POST','/sources/7/copy',{},201,new,'copy'),('GET','/sources/8',None,200,new,'copy readback')]
    return fixtures.rows_from(steps,'COPY_source'),spec


def reference(empty=True):
    spec=fixtures.metadata();spec['projections']=[];spec['entities']['tag']=fixtures.entity('/tags');spec['entities']['entry']['refs']=[dict(field='tags',target='tag',shape='array')]
    steps=[('POST','/tags',{},201,dict(id=6),'create tag'),('GET','/tags/6',None,200,dict(id=6),'read tag'),('POST','/entries',dict(tags=[6]),201,dict(id=11,tags=[] if empty else [dict(id=6)]),'create entry'),('GET','/entries/11',None,200,dict(id=11,tags=[] if empty else [dict(id=6)]),'read entry'),('DELETE','/tags/6',None,204,{},'delete tag'),('GET','/tags/6',None,404,{},'absent'),('GET','/entries/11',None,200,dict(id=11,tags=[]),'read entry after')]
    return fixtures.rows_from(steps,'DELREF_entry_tags'),spec


class SharedHttpTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.counter=0
    def read(self,rows,spec,tool='evomaster',extra=None):
        self.counter+=1;p=self.base/f'input{self.counter}.zip';files={'http-evidence.json':json.dumps(payload(rows,tool)),'story-semantics.json':json.dumps(spec)};files.update(extra or {});p.write_bytes(old.pack(files));return TrafficReader(p).finish()
    def test_identical_move_judge_for_four_tools_without_story_ids(self):
        found=[]
        for tool in ('provengo','evomaster','schemathesis','restler'):
            a=self.read(fixtures.projection(),fixtures.metadata(),tool);found.append(a['rule_occurrences']['STORY-MOVE-PROJECTION']);self.assertEqual(a['shared_semantic_audit'][0]['engine'],'shared-http-semantics/1')
        self.assertEqual(found,[2,2,2,2])
    def test_identical_arithmetic_judge_for_four_tools(self):
        rows,spec=fixtures.arithmetic()
        self.assertEqual([self.read(rows,spec,t)['rule_occurrences']['STORY-ARITHMETIC-DISCREPANCY'] for t in ('provengo','evomaster','schemathesis','restler')],[1]*4)
    def test_identical_contribution_judge_for_four_tools(self):
        rows,spec=contribution()
        self.assertEqual([self.read(rows,spec,t)['rule_occurrences']['RAW-CONTRIBUTION-DISCREPANCY'] for t in ('provengo','evomaster','schemathesis','restler')],[1]*4)
    def test_correct_contribution(self):
        rows,spec=contribution(False);a=self.read(rows,spec);self.assertNotIn('RAW-CONTRIBUTION-DISCREPANCY',a['rule_occurrences']);self.assertEqual(a['shared_semantic_audit'][0]['operation_counts']['CONTRIB']['passed'],1)
    def test_identical_copy_judge_for_four_tools(self):
        rows,spec=copying();self.assertEqual([self.read(rows,spec,t)['rule_occurrences']['RAW-COPY-INTERNAL-REFERENCE'] for t in ('provengo','evomaster','schemathesis','restler')],[2]*4)
    def test_correct_copy(self):
        rows,spec=copying(False);self.assertNotIn('RAW-COPY-INTERNAL-REFERENCE',self.read(rows,spec)['rule_occurrences'])
    def test_bad_source_is_not_misattributed_to_copy(self):
        rows,spec=copying();b=json.loads(rows[0]['response']);b['steps'][0]['refs'][0]['key']='missing';rows[0]['response']=json.dumps(b)
        a=self.read(rows,spec);self.assertNotIn('RAW-COPY-INTERNAL-REFERENCE',a['rule_occurrences']);self.assertIn('COPY_SOURCE_REFERENCE_PRECONDITION_NOT_ESTABLISHED',[g['code'] for g in a['toolkit_coverage_gaps']])
    def test_missing_copy_body_not_a_pass(self):
        rows,spec=copying();rows[1]['response']=None;rows[2]['status']=404;a=self.read(rows,spec);self.assertEqual(a['shared_semantic_audit'][0]['operation_counts']['COPY']['not_evaluable'],1)
    def test_missing_source_not_a_contribution_pass(self):
        rows,spec=contribution();rows[0]['status']=403;a=self.read(rows,spec);self.assertEqual(a['shared_semantic_audit'][0]['operation_counts']['CONTRIB']['not_evaluable'],1)
    def test_intervening_mutation_not_a_contribution_proof(self):
        rows,spec=contribution();rows.insert(3,dict(rows[2],path='/unrelated',input={}))
        self.assertNotIn('RAW-CONTRIBUTION-DISCREPANCY',self.read(rows,spec)['rule_occurrences'])
    def test_rejected_action_not_a_contribution_failure(self):
        rows,spec=contribution();rows[2]['status']=422;self.assertNotIn('RAW-CONTRIBUTION-DISCREPANCY',self.read(rows,spec)['rule_occurrences'])
    def test_passing_reference_story_without_precondition_is_flagged(self):
        rows,spec=reference(True);a=self.read(rows,spec);self.assertEqual(a['rule_occurrences']['STORY-REFERENCE-PRECONDITION-FAILED'],1);self.assertEqual(a['shared_semantic_audit'][0]['reference_precondition_counts'],{'not_established':1})
    def test_established_reference_cleared_is_evaluable(self):
        rows,spec=reference(False);a=self.read(rows,spec);self.assertNotIn('STORY-REFERENCE-PRECONDITION-FAILED',a['rule_occurrences']);self.assertEqual(a['shared_semantic_audit'][0]['reference_postcondition_counts'],{'reference_cleared':1})
    def test_established_reference_dangling_is_detected_for_baseline(self):
        rows,spec=reference(False);rows[-1]['response']=json.dumps(dict(id=11,tags=[dict(id=6)]));self.assertEqual(self.read(rows,spec)['rule_occurrences']['STORY-DANGLING-REFERENCE'],1)
    def test_reset_epoch_does_not_borrow_preimage(self):
        rows=fixtures.projection();rows[5]['epoch']=1;rows[6]['epoch']=1;rows[7]['epoch']=1
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(rows,fixtures.metadata())['rule_occurrences'])
    def test_no_actor_means_no_same_actor_credit(self):
        rows=fixtures.projection()
        for r in rows:r.pop('session',None)
        a=self.read(rows,fixtures.metadata());self.assertNotIn('STORY-MOVE-PROJECTION',a['rule_occurrences']);self.assertIn('HTTP_ACTOR_NOT_RECORDED',[g['code'] for g in a['toolkit_coverage_gaps']])
    def test_forged_input_facts_are_ignored(self):
        rows=fixtures.projection(broken=False)
        for r in rows:r['facts']={'story_move_projection_mismatch':True};r['pass']=False
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(rows,fixtures.metadata())['rule_occurrences'])
    def test_har_uses_same_rules(self):
        entries=[]
        for r in fixtures.projection():entries.append(dict(_actor='A',request=dict(method=r['method'],url='http://sut'+r['path'],headers=[],postData=dict(text=json.dumps(r['input']))),response=dict(status=r['status'],content=dict(text=r['response']))))
        p=self.base/'har.zip';p.write_bytes(old.pack({'traffic.har':json.dumps({'log':{'entries':entries}}),'traffic-meta.json':json.dumps(dict(sut='widget',tool='schemathesis',contract_sha256=fixtures.HASH)),'story-semantics.json':json.dumps(fixtures.metadata())}))
        self.assertEqual(TrafficReader(p).finish()['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_native_restler_network_reader(self):
        lines=[]
        for r in fixtures.projection():
            request=r['method']+' '+r['path']+' HTTP/1.1\r\nHost: sut\r\n\r\n'+json.dumps(r['input']);response='HTTP/1.1 '+str(r['status'])+' OK\r\nContent-Type: application/json\r\n\r\n'+r['response'];lines += ['2026-10-27 01:00:00: Sending: '+repr(request),'2026-10-27 01:00:01: Received: '+repr(response)]
        p=self.base/'restler.zip';p.write_bytes(old.pack({'network.testing.1.txt':'\n'.join(lines),'traffic-meta.json':json.dumps(dict(sut='widget',tool='restler',default_actor='A',contract_sha256=fixtures.HASH)),'story-semantics.json':json.dumps(fixtures.metadata())}))
        a=TrafficReader(p).finish();self.assertEqual(a['evidence_summary']['http_records'],8);self.assertEqual(a['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_console_file_is_not_a_network_log(self):
        with self.assertRaises(UnsupportedEvidence):restler_records(b'Finished fuzzing',{},lambda *a,**k:None)
    def test_restler_repr_is_data_not_code(self):
        with self.assertRaises(InvalidEvidence):restler_records(b'Sending: __import__("os")',{},lambda *a,**k:None)
    def test_interleaved_restler_never_fabricates_pairing(self):
        raw='Sending: '+repr('GET /one HTTP/1.1\r\n\r\n')+'\nSending: '+repr('GET /two HTTP/1.1\r\n\r\n')+'\nReceived: '+repr('HTTP/1.1 500 Error\r\n\r\n{}')
        result=restler_records(raw.encode(),{},lambda *a,**k:None);self.assertTrue(all(r['status'] is None for r in result))
    def test_raw_adapter_cli(self):
        p=self.base/'raw.zip';p.write_bytes(old.pack({'http-evidence.json':json.dumps(payload(fixtures.projection())),'story-semantics.json':json.dumps(fixtures.metadata())}));request=self.base/'request.json';request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='baseline',tool='evomaster',product='widget',product_version='unknown'),evidence=dict(adapter='http-traffic',archive=str(p)))))
        r=box.run(request,self.base/'output');self.assertEqual(r['exit_code'],0);self.assertEqual(r['counts']['finding_occurrences'],2)
    def test_deliberate_unexpected_engine_error_is_exit_four(self):
        evidence=self.base/'raw.json';evidence.write_text(json.dumps(payload(fixtures.projection())));request=self.base/'request.json';request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='fault-injection',tool='evomaster',product='widget',product_version='unknown'),evidence=dict(adapter='http-traffic',observations=str(evidence)))))
        with patch.object(box,'execute',side_effect=RuntimeError('intentional internal failure')):result=box.run(request,self.base/'output')
        self.assertEqual(result['exit_code'],4);self.assertEqual(result['status'],'FAILED');d=json.loads((self.base/'output/diagnostics.json').read_text());self.assertEqual(d['items'][0]['code'],'ENGINE_ERROR');self.assertEqual(json.loads((self.base/'output/findings.json').read_text())['findings'],[])
    def test_login_roundtrip_counter_is_separate(self):
        outer,files,rows=login.fixture();sample=next(r for r in rows if r['category']=='roundtrip-check');count=sum(r['category']=='roundtrip-check' for r in rows)
        for i in range(294-count):rows.append(dict(sample,index=len(rows)))
        outer=login.change(outer,files,rows);p=self.base/'login.zip';p.write_bytes(login.pack(outer));request=self.base/'request.json';request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='format-fixture',tool='provengo',product='vikunja',product_version='v2.6.0'),evidence=dict(adapter='toolkit-v1',archive=str(p)))))
        r=box.run(request,self.base/'output');self.assertEqual(r['exit_code'],0);self.assertEqual(r['counts']['roundtrip_check_records'],294);self.assertEqual(r['counts']['research_records'],6);self.assertEqual(r['counts']['known_failure_records'],1)
    def test_unique_log_id_join(self):
        row=dict(_position=0,method='GET',path='/x',status=500,request_id='r1');obs=dict(_position=0,source={'record':0});logs=[(json.dumps(dict(request_id='r1',method='GET',path='/x',status=500,message='database error')),{'sha256':'a'*64})]
        a=correlate([row],[obs],logs,{},lambda *a,**k:None);self.assertEqual(len(a['joins']),1);self.assertFalse(a['joins'][0]['root_cause_proven'])
    def test_ambiguous_log_join_is_not_claimed(self):
        row=dict(_position=0,method='GET',path='/x',status=500,request_id='r1');obs=dict(_position=0,source={'record':0});line=json.dumps(dict(request_id='r1',method='GET',path='/x',status=500))
        self.assertEqual(correlate([row],[obs],[(line+'\n'+line,{})],{},lambda *a,**k:None)['joins'],[])
    def test_log_time_join_requires_opt_in_and_unique_tuple(self):
        row=dict(_position=0,method='GET',path='/x',status=500,t_utc='2026-10-27T00:00:00Z');obs=dict(_position=0,source={});logs=[(json.dumps(dict(method='GET',path='/x',status=500,timestamp='2026-10-27T00:00:00Z')),{})]
        self.assertEqual(correlate([row],[obs],logs,{},lambda *a,**k:None)['joins'],[]);self.assertEqual(len(correlate([row],[obs],logs,{'allow_time_join':True},lambda *a,**k:None)['joins']),1)

    def test_roleless_aggregate_judge_for_four_tools(self):
        spec=fixtures.metadata();spec['projections']=[];spec['entities']={'parent':fixtures.entity('/parents'),'child':fixtures.entity('/children',[dict(field='parent',target='parent',shape='scalar')])};spec['aggregates']=[dict(child='child',parent='parent',reference_field='parent',child_view='/children/{id}/values',parent_view='/parents/{id}/values',fields=['energy'])]
        rows=old.aggregate_rows()
        self.assertEqual([self.read(rows,spec,t)['rule_occurrences']['STORY-AGGREGATE-MOVE'] for t in ('provengo','evomaster','schemathesis','restler')],[1]*4)
    def test_roleless_reference_judge_for_four_tools(self):
        rows,spec=reference(False);rows[-1]['response']=json.dumps(dict(id=11,tags=[dict(id=6)]))
        self.assertEqual([self.read(rows,spec,t)['rule_occurrences']['STORY-DANGLING-REFERENCE'] for t in ('provengo','evomaster','schemathesis','restler')],[1]*4)
    def test_freeze_prepares_without_reading_run_evidence(self):
        from evaluation_freeze import create,verify
        f=create();self.assertTrue(verify(f));self.assertFalse(f['held_out_validation_performed'])
    def test_freeze_rejects_code_manifest_drift(self):
        from evaluation_freeze import create,verify
        f=create();f['code'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):verify(f)
    def test_freeze_rejects_unregistered_semantic_profile(self):
        from evaluation_freeze import create,verify
        f=create()
        with self.assertRaises(ValueError):verify(f,['0'*64])
    def test_freeze_registered_external_profile_runs(self):
        from evaluation_freeze import create
        archive=self.base/'raw.zip';archive.write_bytes(old.pack({'http-evidence.json':json.dumps(payload(fixtures.projection()))}))
        profile=self.base/'semantics.json';profile.write_text(json.dumps(fixtures.metadata()));freeze=self.base/'freeze.json';freeze.write_text(json.dumps(create([profile])))
        request=self.base/'request.json';request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='freeze-test',tool='evomaster',product='widget',product_version='unknown'),evidence=dict(adapter='http-traffic',archive=str(archive)),configuration=dict(story_semantics=str(profile),evaluation_freeze=str(freeze)))))
        result=box.run(request,self.base/'output');self.assertEqual(result['exit_code'],0)
        provenance=json.loads((self.base/'output/provenance.json').read_text());self.assertTrue(provenance['evaluation_freeze_verified']);self.assertFalse(provenance['held_out_validation_proven'])

    def test_api_base_path_keeps_captured_path_and_common_judge(self):
        rows=fixtures.projection();spec=fixtures.metadata();spec['api_base_path']='/api/v1'
        for row in rows:row['path']='/api/v1'+row['path']
        a=self.read(rows,spec);self.assertEqual(a['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
        self.assertTrue(all(o['captured_path'].startswith('/api/v1/') for o in a['observations']))

    def test_encoded_restler_body_is_explicitly_unavailable(self):
        gaps=[];raw='Sending: '+repr('GET /x HTTP/1.1\r\n\r\n')+'\nReceived: '+repr('HTTP/1.1 500 Error\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n')
        rows=restler_records(raw.encode(),{},lambda code,**kw:gaps.append(code));self.assertEqual(rows[0]['status'],500);self.assertIsNone(rows[0]['response']);self.assertIn('RESTLER_HTTP_BODY_ENCODING_UNSUPPORTED',gaps)

    def test_missing_collection_is_not_an_empty_observed_collection(self):
        rows,spec=contribution();rows[-1]['response']=json.dumps({'id':101});a=self.read(rows,spec)
        self.assertNotIn('RAW-CONTRIBUTION-DISCREPANCY',a['rule_occurrences']);self.assertEqual(a['shared_semantic_audit'][0]['operation_counts']['CONTRIB']['not_evaluable'],1)

    def test_missing_reference_field_is_not_a_cleared_reference(self):
        rows,spec=reference(False);rows[-1]['response']=json.dumps({'id':11});a=self.read(rows,spec)
        self.assertEqual(a['shared_semantic_audit'][0]['reference_postcondition_counts'],{'not_evaluable':1})

    def test_correlated_error_signature_does_not_prove_root_cause(self):
        row=dict(_position=0,method='GET',path='/x',captured_path='/api/v1/x',status=500,request_id='r1');obs=dict(_position=0,source={},status=500)
        line=json.dumps(dict(request_id='r1',method='GET',path='/api/v1/x',status=500,message='database is locked'))
        a=correlate([row],[obs],[(line,{})],dict(signatures={'db_lock':'database is locked'}),lambda *a,**k:None)
        self.assertTrue(obs['facts']['server_reported_error_signature']);self.assertEqual(a['joins'][0]['server_reported_signatures'],['db_lock']);self.assertFalse(a['joins'][0]['root_cause_proven'])

    def test_invalid_har_is_input_error(self):
        p=self.base/'bad.har';p.write_text(json.dumps({'log':{'entries':[None]}}))
        with self.assertRaises(InvalidEvidence):TrafficReader(p).finish()

    def test_invalid_optional_profile_is_input_error(self):
        rows,spec=contribution();spec['copies']=[None]
        with self.assertRaises(InvalidEvidence):self.read(rows,spec)

    def test_missing_action_binding_is_not_an_engine_error(self):
        rows,spec=copying();spec['copies'][0]['source_bindings']={'id':'unknown'};a=self.read(rows,spec)
        self.assertEqual(a['shared_semantic_audit'][0]['operation_counts']['COPY']['not_evaluable'],1)

    def test_toolkit_baseline_runs_common_judge_beside_native_report(self):
        from toolkit_adapter import Reader
        meta=dict(tool='schemathesis',sut_version='1.0',contract_sha256=fixtures.HASH)
        files={'ENV_v1_baselines.txt':'sut=widget\nkind=baselines\nsut_version=1.0\n','rep1/run-meta.json':json.dumps(meta),'rep1/sut.log':'','rep1/http-evidence.json':json.dumps(payload(fixtures.projection(),'schemathesis')),'rep1/story-semantics.json':json.dumps(fixtures.metadata()),'rep1/junit-test.xml':'<testsuite><testcase name="x"><failure/></testcase></testsuite>'}
        p=self.base/'baseline.zip';p.write_bytes(old.pack(files));a=Reader(p).finish()
        self.assertEqual(a['rule_occurrences']['STORY-MOVE-PROJECTION'],2);self.assertTrue(any(o.get('evidence_tier')=='native_tool_report' for o in a['observations']));self.assertNotIn('SEMANTIC_HTTP_TRAFFIC_MISSING',[g['code'] for g in a['toolkit_coverage_gaps']])

    def test_toolkit_model_research_uses_same_common_judge(self):
        from toolkit_adapter import Reader
        rows=fixtures.projection();result=dict(version='v1',sut='widget',sut_version='1.0',contract_sha256=fixtures.HASH,requests=len(rows),status='COMPLETED',native_exit=0)
        for row in rows:row['category']='research'
        p=self.base/'model.zip';p.write_bytes(old.pack({'result_v1.json':json.dumps(result),'gateway-journal.jsonl':'\n'.join(map(json.dumps,rows)),'native.log':'Test Result: SUCCESS','story-semantics.json':json.dumps(fixtures.metadata())}));a=Reader(p).finish()
        self.assertEqual(a['rule_occurrences']['STORY-MOVE-PROJECTION'],2);self.assertEqual(a['shared_semantic_audit'][0]['transport_records'],8)

if __name__=='__main__':unittest.main()
