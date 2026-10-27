import copy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from coverage_engine import analyze, raw_pair, applicable_coverage

SRC=dict(sha256='a'*64,members=['review_v1_s1.zip','gateway-journal.jsonl'],archive_sha256='b'*64,file='fixture.zip')
def observation(product='gitea'):
    return dict(id='x',product=product,product_version='28.1.0',run_id='run',tool='provengo',source=dict(SRC,record=0),facts={},fact_basis='recomputed')
def part(row):return [('fixture',dict(observations=[observation()],runs=[],original_oracles=[dict(source=dict(SRC,record=1),payload=row)]))]
def ref(**kw):
    row=dict(category='reference-check',status=201,readback_status=200,sent=9,stored=9,field='milestone',type='Issue');row.update(kw);return row

class CoverageTests(unittest.TestCase):
    def test_gitea_does_not_report_vikunja_coverage(self):
        d=analyze([('gitea',dict(observations=[observation()],runs=[],original_oracles=[]))]);self.assertEqual(d['rule_coverage'],[])
        self.assertEqual(d['coverage_audit']['not_applicable_rules'][0]['catalog_id'],'VIK-O09')
    def test_applicability_filter_is_idempotent(self):
        d=analyze([('gitea',dict(observations=[observation()],runs=[],original_oracles=[]))]);before=copy.deepcopy(d);applicable_coverage(d);self.assertEqual(d,before)
    def test_wrapper_exposes_resolved_pairs_without_unknown_gaps(self):
        import natchan
        d=analyze(self.pairs());c=natchan.coverage(d,'toolkit-v1',None)
        self.assertFalse(c['gaps']);self.assertEqual(len(c['coverage_audit']['resolved_measurements']),2)
    def test_vikunja_keeps_coverage_gap(self):
        d=analyze([('vik',dict(observations=[observation('vikunja')],runs=[],original_oracles=[]))]);self.assertEqual(d['rule_coverage'][0]['catalog_id'],'VIK-O09')
    def test_mixed_keeps_vikunja_coverage(self):
        a=observation();b=observation('vikunja');b['source']=dict(SRC,record=2)
        d=analyze([('mix',dict(observations=[a,b],runs=[],original_oracles=[]))]);self.assertEqual(len(d['rule_coverage']),1)
    def test_equal_numeric_scalar_is_observable(self):
        d=analyze(part(ref()));self.assertEqual(d['unknown_evidence'],[])
        self.assertNotIn('MEASURED-REFERENCE-DIFFERENCE',d['rule_occurrences'])
    def test_equal_string_scalar_is_observable(self):
        d=analyze(part(ref(sent='alice',stored='alice')));self.assertEqual(d['unknown_evidence'],[])
    def test_scalar_difference_is_measurement_not_business_proof(self):
        d=analyze(part(ref(sent=9,stored=10)));self.assertEqual(d['rule_occurrences']['MEASURED-REFERENCE-DIFFERENCE'],1)
        o=next(o for o in d['observations'] if o['source']['record']==1)
        self.assertEqual(o['evidence_tier'],'producer_id_projection');self.assertIs(o['facts']['full_snapshots_verified'],False)
    def test_explicit_null_is_distinct_from_absent_key(self):
        d=analyze(part(ref(stored=None)));self.assertIn('MEASURED-REFERENCE-DIFFERENCE',d['rule_occurrences'])
        row=ref();row.pop('stored');self.assertEqual(len(analyze(part(row))['unknown_evidence']),1)
    def test_missing_projection_marker_remains_unknown(self):
        d=analyze(part(ref(stored={'missing':'id'})));self.assertEqual(len(d['unknown_evidence']),1)
    def test_unreadable_projection_remains_unknown(self):
        d=analyze(part(ref(readback_status=404)));self.assertEqual(len(d['unknown_evidence']),1)
    def test_array_behavior_preserved(self):
        d=analyze(part(ref(sent=[1],stored=[])));self.assertEqual(d['rule_occurrences']['MEASURED-REFERENCE-DIFFERENCE'],1)
    def test_boolean_is_not_integer_reference(self):
        d=analyze(part(ref(sent=1,stored=True)));self.assertEqual(len(d['unknown_evidence']),1)
    def test_atomicity_without_snapshots_is_not_suppressed(self):
        row=dict(category='atomicity-check',fields={'a':'applied','b':'kept'},first_status=500,readback_status=200,verdict='rolled_back')
        d=analyze(part(row));self.assertEqual(d['rule_occurrences']['MEASURED-PARTIAL-FIELDS'],1)
        self.assertEqual(d['unknown_evidence'][0]['reason'],'full_before_after_snapshots_missing')
    def pairs(self):
        # Feed the existing raw detector, not hand-authored qualified verdicts.
        import analyze_coverage as old
        from raw_sequences import augment
        rows=[];steps=[];oracles=[]
        for pair,mode,value,cs,us in [(1,'own','alice',201,201),(2,'missing','absent',422,500)]:
            for phase,method,status in [('create','POST',cs),('update','PATCH',us)]:
                index=len(steps);identity=pair
                spec=dict(role='probe',pair=pair,phase=phase,entity='Issue',field='assignee',mode=mode,method=method)
                path='/repos/a/r/issues' if method=='POST' else '/repos/a/r/issues/'+str(identity)
                body={'id':identity,'assignee':{'login':value}}
                if status>=400:body={}
                rows.append(dict(category='research',method=method,path=path,input={'assignee':value},response=body,status=status,logical_id='G014_STEP_'+str(index),session='A',t_rel_ms=index+1))
                steps.append(spec);readspec=dict(spec,role='readback',method='GET',projection='assignee.login')
                rows.append(dict(category='research',method='GET',path='/repos/a/r/issues/'+str(identity),input=None,response={'id':identity,'assignee':{'login':value}},status=200,logical_id='G014_STEP_'+str(index+1),session='A',t_rel_ms=index+2));steps.append(readspec)
            oracles.append(dict(source=dict(SRC,record=100+pair),payload={'category':'divergence-check','pair':pair,'create':dict(status=cs,sent=value),'update':dict(status=us,sent=value,field='assignee'),'verdict':'same'}))
        ir={'entities':[dict(name='Issue',path='/repos/{owner}/{repo}/issues',detail='/repos/{owner}/{repo}/issues/{index}',create_method='post',update_method='patch',create_schema={'properties':{'assignee':{'type':'string'}}},update_schema={'properties':{'assignee':{'type':'string'}}})]}
        values,_=old.baseline.gitea_observations(dict(id='run',product='gitea',version='28.1.0',tool='provengo',source=SRC),dict(records=rows,ir=ir,sut_log=''))
        augment(values,rows,{'steps':steps})
        return [('pair',dict(observations=values,runs=[],original_oracles=oracles))]
    def test_raw_pair_reconciles_same_and_different_pairs(self):
        d=analyze(self.pairs());self.assertEqual(d['rule_occurrences']['GEN-CREATE_UPDATE_DIVERGENCE'],1)
        self.assertEqual(d['unknown_evidence'],[]);resolved=d['coverage_audit']['resolved_measurements'];self.assertEqual(len(resolved),2)
        self.assertEqual([r['response_classes_differ'] for r in resolved],[False,True])
    def test_missing_control_is_not_resolved(self):
        p=self.pairs()
        for o in p[0][1]['observations']:o['facts'].pop('raw_pair_controls_verified',None)
        self.assertEqual(len(analyze(p)['unknown_evidence']),2)
    def test_missing_create_witness_is_not_resolved(self):
        p=self.pairs()
        for o in p[0][1]['observations']:o['witnesses']=[]
        self.assertEqual(len(analyze(p)['unknown_evidence']),2)
    def test_unrelated_summary_is_not_resolved(self):
        p=self.pairs();p[0][1]['original_oracles'][1]['source']['sha256']='c'*64
        self.assertEqual(len(analyze(p)['unknown_evidence']),1)
    def test_wrong_summary_status_does_not_erase_missing_evidence(self):
        p=self.pairs();p[0][1]['original_oracles'][1]['payload']['create']['status']=200
        d=analyze(p);self.assertEqual(len(d['unknown_evidence']),1);self.assertEqual(d['rule_occurrences']['GEN-CREATE_UPDATE_DIVERGENCE'],1)
    def test_ambiguous_pair_does_not_resolve(self):
        p=self.pairs();values=p[0][1]['observations'];update=next(o for o in values if o['facts'].get('raw_pair_id')==2)
        duplicate=copy.deepcopy(update);duplicate['source']['record']=88;values.append(duplicate)
        self.assertEqual(len(analyze(p)['unknown_evidence']),1)

if __name__=='__main__':unittest.main()

