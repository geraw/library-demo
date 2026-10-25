"""Synthetic, isolated positive/negative cases for each newly accepted evidence link."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_additions import verify
from coverage_engine import analyze

SRC={'sha256':'a'*64,'archive_sha256':'b'*64,'members':['gateway-journal.jsonl'],'file':'fixture.zip'}
CONTEXT=dict(id='fixture',product='example',version='1',tool='provengo',source=SRC)
IR={'entities':[dict(name='Resource',path='/parents/{parent}/items',detail='/parents/{parent}/items/{id}',create_method='post',update_method='patch')],
    'traps':{'edge':{'probes':[dict(entity='Resource',field='value',value='extreme',update=True)]}}}

def atom():
    row=dict(category='atomicity-check',index=10,kind='update',logical_id='opaque',method='PATCH',path='/parents/1/items/3',session='A',first_status=500,readback_status=200,
        fields=dict(value='kept',companion='applied'),collateral_changed=['timestamp'],verdict='partial',
        snapshots=dict(format='atom-snapshots/1',request_body=dict(value='extreme',companion='new'),first_response_body='error',
            before=dict(source='trap_read_before_write',body=dict(value='old',companion='old',timestamp=1)),
            after=dict(method='GET',path='/parents/1/items/3',status=200,body=dict(value='old',companion='new',timestamp=2))))
    raw=dict(category='research',index=11,logical_id='opaque',method='PATCH',path=row['path'],session='A',status=500,input=copy.deepcopy(row['snapshots']['request_body']),response='error')
    return [row,raw]

def div(cs=422,us=500):
    c=dict(category='research',index=10,action='edge_create',logical_id='opaque-create',method='POST',path='/parents/1/items',session='A',status=cs,input={'value':'extreme'},response='{}')
    control=dict(category='research',index=11,action='edge_uread',logical_id='opaque-update',method='GET',path='/parents/1/items/3',session='A',status=200,input=None,response='{}')
    u=dict(c,index=12,logical_id='opaque-update',action='edge_update',method='PATCH',path=control['path'],status=us)
    def side(r):return dict(logical_id=r['logical_id'],status=r['status'],write=dict(research_index=r['index'],**{k:r[k] for k in ['method','path','input','status','response']}),readback=None)
    summary=dict(category='divergence-check',index=13,evidence_format='div-evidence/1',rule='DIV-1',verdict='class_diverge' if cs//100!=us//100 else 'same',create=side(c),update=side(u))
    return [c,control,u,summary]

def run(rows,ir=IR):
    # Positions intentionally differ from producer indexes (10+).
    values=[]
    for pos,r in enumerate(rows):
        if r['category']=='research':values.append(dict(id='x'+str(pos),source=dict(SRC,record=pos),product='example',product_version='1',run_id='fixture',tool='provengo',facts={},method=r['method'],status=r['status']))
    result=verify(rows,ir,CONTEXT,values)
    return result,values

class AdditionsTests(unittest.TestCase):
    def assert_gap(self,rows,reason):
        result,_=run(rows);self.assertEqual(len(result['unknown_evidence']),1);self.assertIn(reason,result['unknown_evidence'][0]['reason']);self.assertFalse(result['resolved_measurements']);return result['unknown_evidence'][0]
    def test_atom_partial_recomputed(self):
        result,values=run(atom());self.assertEqual(result['resolved_measurements'][0]['computed']['verdict'],'partial');self.assertTrue(values[-1]['facts']['full_snapshots_verified'])
    def test_atom_rollback_and_commit_and_other_and_no_fields(self):
        for value,companion,wanted in [('old','old','rolled_back'),('extreme','new','committed_despite_error'),('third','new','other')]:
            rows=atom();r=rows[0];r['snapshots']['after']['body'].update(value=value,companion=companion)
            r['fields']={'value':'kept' if value=='old' else 'applied' if value=='extreme' else 'other','companion':'kept' if companion=='old' else 'applied'};r['verdict']=wanted
            self.assertEqual(run(rows)[0]['resolved_measurements'][0]['computed']['verdict'],wanted)
        rows=atom();r=rows[0];r['snapshots']['request_body']=dict(value='old');rows[1]['input']=dict(value='old');r.update(fields={},collateral_changed=['companion','timestamp'],verdict='no_judged_field')
        self.assertEqual(run(rows)[0]['resolved_measurements'][0]['computed']['verdict'],'no_judged_field')
    def test_atom_missing_after(self):
        rows=atom();rows[0]['snapshots'].pop('after');self.assert_gap(rows,'after_snapshot_missing')
    def test_atom_404(self):
        rows=atom();rows[0]['snapshots']['after']['status']=404;self.assert_gap(rows,'after_snapshot_not_readable')
    def test_atom_nonobject_after(self):
        rows=atom();rows[0]['snapshots']['after']['body']='redacted';self.assert_gap(rows,'after_snapshot_not_readable')
    def test_atom_null_before(self):
        rows=atom();rows[0]['snapshots']['before']=None;self.assert_gap(rows,'before_snapshot_or_source_missing')
    def test_atom_null_before_source(self):
        rows=atom();rows[0]['snapshots']['before']['source']=None;self.assert_gap(rows,'before_snapshot_or_source_missing')
    def test_atom_cached_source_not_described_as_immediate(self):
        rows=atom();rows[0]['snapshots']['before']['source']='last_2xx_representation';a=run(rows)[0]['resolved_measurements'][0];self.assertFalse(a['immediate_preimage_asserted']);self.assertFalse(a['background_concurrency_excluded'])
    def test_atom_field_contradiction_is_not_classified(self):
        rows=atom();rows[0]['fields']['value']='applied';g=self.assert_gap(rows,'atomicity_measurement_mismatch');self.assertEqual(g['status'],'PRODUCER_EVIDENCE_CONTRADICTION');self.assertIn('computed',g)
        self.assertEqual(len(run(rows)[1]),1)
    def test_atom_collateral_contradiction(self):
        rows=atom();rows[0]['collateral_changed']=[];self.assert_gap(rows,'collateral_changed')
    def test_atom_verdict_contradiction(self):
        rows=atom();rows[0]['verdict']='rolled_back';self.assert_gap(rows,'verdict')
    def test_atom_ambiguous_request(self):
        rows=atom();rows.append(dict(rows[1],index=12));self.assert_gap(rows,'raw_write_missing_or_ambiguous')
    def test_atom_body_mismatch(self):
        rows=atom();rows[1]['input']={};self.assert_gap(rows,'raw_write_body_mismatch')
    def test_atom_status_mismatch(self):
        rows=atom();rows[1]['status']=201;self.assert_gap(rows,'raw_write_status_mismatch')
    def test_atom_response_mismatch(self):
        rows=atom();rows[1]['response']='other';self.assert_gap(rows,'first_response_mismatch')
    def test_atom_after_wrong_resource(self):
        rows=atom();rows[0]['snapshots']['after']['path']='/other';self.assert_gap(rows,'after_resource_mismatch')
    def test_atom_actor_mismatch(self):
        rows=atom();rows[1]['session']='B';self.assert_gap(rows,'actor_unbound')
    def test_atom_unknown_version(self):
        rows=atom();rows[0]['snapshots']['format']='atom-snapshots/2';self.assert_gap(rows,'unsupported_atomicity_format')
    def test_atom_old_format_not_handled(self):
        rows=atom();rows[0].pop('snapshots');self.assertEqual(run(rows)[0]['handled_records'],[])
    def test_atom_create_keeps_gap(self):
        rows=atom();rows[0]['kind']='create';self.assert_gap(rows,'kind_not_supported')
    def test_div_raw_class_difference(self):
        a,v=run(div());self.assertEqual(a['resolved_measurements'][0]['computed_verdict'],'class_diverge');self.assertTrue(v[-1]['facts']['create_update_diverge'])
    def test_div_equal_non2xx_is_not_a_finding(self):
        a,v=run(div(422,422));self.assertEqual(a['resolved_measurements'][0]['computed_verdict'],'same');self.assertFalse(v[-1]['facts']['create_update_diverge'])
    def test_div_field_from_ir_not_logical_id(self):
        self.assertEqual(run(div())[0]['resolved_measurements'][0]['field'],'value')
    def test_div_pointer_wrong_record(self):
        rows=div();rows[-1]['create']['write']['research_index']=11;self.assert_gap(rows,'write_copy_differs')
    def test_div_pointer_duplicate_index(self):
        rows=div();rows.insert(0,dict(rows[0]));self.assert_gap(rows,'index_missing_or_ambiguous')
    def test_div_wrong_input(self):
        rows=div();rows[-1]['create']['write']['input']={'value':'other'};self.assert_gap(rows,'write_copy_differs')
    def test_div_wrong_summary_status(self):
        rows=div();rows[-1]['create']['status']=201;self.assert_gap(rows,'summary_status_mismatch')
    def test_div_wrong_reported_verdict(self):
        rows=div();rows[-1]['verdict']='same';self.assert_gap(rows,'divergence_verdict_mismatch')
    def test_div_no_ir_not_fabricated(self):
        a,_=run(div(),{});self.assertFalse(a['resolved_measurements'])
    def test_div_ambiguous_field(self):
        rows=div();ir=copy.deepcopy(IR);ir['traps']['edge']['probes'].append(dict(entity='Resource',field='second',value='extreme',update=True))
        for r in [rows[0],rows[2]]:r['input']['second']='extreme'
        a,_=run(rows,ir);self.assertEqual(a['unknown_evidence'][0]['reason'],'tested_field_not_unique_in_contract_traps')
    def test_div_other_actor(self):
        rows=div();rows[2]['session']='B';self.assert_gap(rows,'pair_actor_unbound')
    def test_div_control_missing(self):
        rows=div();rows[1]['status']=404;self.assert_gap(rows,'control_missing')
    def test_div_old_format_not_handled(self):
        rows=div();rows[-1].pop('evidence_format');self.assertEqual(run(rows)[0]['handled_records'],[])
    def test_div_unknown_version(self):
        rows=div();rows[-1]['evidence_format']='div-evidence/2';self.assert_gap(rows,'unsupported_divergence_format')
    def successful(self):
        rows=div(201,200);summary=rows.pop()
        for r in [rows[0],rows[2]]:
            index=14 if r['action']=='edge_create' else 15
            rb=dict(category='roundtrip-check',index=index,action=r['action'],logical_id=r['logical_id'],method=r['method'],path=r['path'],session='A',type='Resource',fields=['value'],mismatches={},readback_status=200)
            rows.append(rb);summary['create' if r['action']=='edge_create' else 'update']['readback']=dict(record_index=index,category='roundtrip-check')
        summary['index']=16;rows.append(summary);return rows
    def test_div_2xx_compares_measurements_without_claiming_full_state(self):
        a,v=run(self.successful());row=a['resolved_measurements'][0];self.assertEqual(row['status'],'PRODUCER_MEASUREMENT_COMPARED');self.assertFalse(row['independent_raw_state_verified']);self.assertFalse(v[2]['facts']['create_update_diverge'])
    def test_div_2xx_missing_readback(self):
        rows=self.successful();rows[-1]['create']['readback']=None;self.assert_gap(rows,'readback_pointer_missing')
    def test_div_2xx_wrong_readback(self):
        rows=self.successful();rows[-1]['update']['readback']['record_index']=14;self.assert_gap(rows,'readback_write_binding_mismatch')
    def test_div_2xx_stored_difference(self):
        rows=self.successful();rows[4]['mismatches']={'value':{'class':'changed','sent':'extreme','stored':'trimmed'}};rows[-1]['verdict']='stored_diverge'
        a,v=run(rows);self.assertEqual(a['resolved_measurements'][0]['computed_verdict'],'stored_diverge');self.assertTrue(v[2]['facts']['create_update_diverge'])
    def test_div_2xx_unmeasured_field(self):
        rows=self.successful();rows[4]['fields']=[];self.assert_gap(rows,'tested_field_not_in_readback')
    def test_div_body_boolean_not_number(self):
        rows=div();rows[-1]['create']['write']['input']={'value':True};rows[0]['input']={'value':1};self.assert_gap(rows,'write_copy_differs')
    def test_exact_record_coverage_reconciliation(self):
        rows=atom();result,values=run(rows)
        d=analyze([('fixture',dict(observations=values,runs=[],original_oracles=[],evidence_additions=result))]);self.assertEqual(d['unknown_evidence'],[]);self.assertEqual(d['rule_occurrences']['GEN-PARTIAL_WRITE'],1)

    def reference_pair(self,cs=201,us=200):
        rows=div(cs,us)
        for pos,action in [(0,'ref_create'),(1,'ref_uread'),(2,'ref_update')]:rows[pos]['action']=action
        for pos in [0,2]:rows[pos]['input']={'value':9}
        for side,pos in [('create',0),('update',2)]:rows[-1][side]['write']['input']={'value':9}
        ir=copy.deepcopy(IR);ir['traps']={'refs':{'refs':[dict(entity='Resource',field='value',paths=['create','update'])]}}
        return rows,ir
    def test_ref_class_difference_uses_same_numeric_value(self):
        rows,ir=self.reference_pair(201,500)
        a,_=run(rows,ir);self.assertEqual(a['resolved_measurements'][0]['computed_verdict'],'class_diverge')
    def test_ref_different_identifiers_not_equated_by_mode(self):
        rows,ir=self.reference_pair(201,500);rows[2]['input']={'value':10};rows[-1]['update']['write']['input']={'value':10}
        a,_=run(rows,ir);self.assertEqual(a['unknown_evidence'][0]['reason'],'tested_field_values_differ')
    def test_ref_different_parent_scope_stays_unknown(self):
        rows,ir=self.reference_pair(201,500);rows[2]['path']='/parents/2/items/3';rows[-1]['update']['write']['path']=rows[2]['path']
        a,_=run(rows,ir);self.assertEqual(a['unknown_evidence'][0]['reason'],'pair_parent_context_differs')
    def test_ref_successful_retained_projections(self):
        rows,ir=self.reference_pair();summary=rows.pop()
        for pos,index in [(0,14),(2,15)]:
            raw=rows[pos];rows.append(dict(category='reference-check',index=index,logical_id=raw['logical_id'],action=raw['action'],path=raw['path'],session='A',status=raw['status'],type='Resource',readback_status=200,field='value',sent=[9],stored=[9]))
            summary['create' if pos==0 else 'update']['readback']=dict(category='reference-check',record_index=index)
        rows.append(summary);a,_=run(rows,ir);self.assertEqual(a['resolved_measurements'][0]['computed_verdict'],'same');self.assertFalse(a['resolved_measurements'][0]['independent_raw_state_verified'])
    def test_readback_index_preceding_write_is_rejected(self):
        rows=self.successful();rows[4]['index']=9;rows[-1]['update']['readback']['record_index']=9
        # Physical order, rather than numeric sort, is authoritative. Move readback before write.
        rb=rows.pop(4);rows.insert(0,rb);self.assert_gap(rows,'readback_order_invalid')
    def test_conflicting_new_record_is_a_gap_in_common_analysis(self):
        rows=atom();rows[0]['verdict']='rolled_back';a,values=run(rows)
        d=analyze([('fixture',dict(observations=values,runs=[],original_oracles=[],evidence_additions=a))])
        self.assertNotIn('GEN-PARTIAL_WRITE',d['rule_occurrences']);self.assertEqual(d['unknown_evidence'][0]['status'],'PRODUCER_EVIDENCE_CONTRADICTION')

if __name__=='__main__':unittest.main()
