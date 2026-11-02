import io,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traffic import exchanges
from review_stories import producer_summary
import test_collection_semantics as collection_tests
import test_lifecycle as lifecycle_tests

class EvidenceV210Tests(unittest.TestCase):
    def parse(self,rows):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl';p.write_text('\n'.join(json.dumps(x) for x in rows));stats={}
            result=list(exchanges(p,'journal-jsonl','fixture',stats));return result,stats
    def raw(self,**kw):return {'category':'research','method':'GET','path':'/objects/1','status':200,'session':'A','response':'{"id":1}',**kw}
    def test_attempt_and_story_are_opaque_boundaries(self):
        r,s=self.parse([self.raw(story_id='x',attempt_id='x#1'),self.raw(story_id='x',attempt_id='x#2'),self.raw(story_id='y',attempt_id='y#1')])
        self.assertEqual(len({x['case_id'] for x in r}),3);self.assertTrue(all(x['epoch'] is None for x in r))
    def test_transport_gap_not_server_status_and_breaks_scope(self):
        for category in ['request-timeout','infrastructure-error']:
            r,s=self.parse([self.raw(),{'category':category,'status':500},self.raw()])
            self.assertEqual(len(r),2);self.assertEqual(s[category],1);self.assertNotEqual(r[0]['case_id'],r[1]['case_id'])
            self.assertTrue(all(x['status']==200 for x in r))
    def test_authentication_not_product_request(self):
        r,s=self.parse([self.raw(action='authenticate'),self.raw()]);self.assertEqual(len(r),1)
    def test_producer_observation_and_setup_not_findings(self):
        check={'check':'x','pass':False}
        r=producer_summary({'stories':[{'status':'SETUP_FAILED','failed_checks':[check]}, {'status':'COMPLETED','failed_checks':[{'pass':None}], 'observations':[{'pass':None}]}]})
        self.assertEqual(r['producer_check_candidates'],[]);self.assertEqual(r['producer_observations_not_failures'],1)
    def test_empty_intra_reference_is_excluded(self):
        r=producer_summary({'stories':[{'status':'COMPLETED','failed_checks':[{'check':'copy INTRA-REF x in y','pass':False,'expected':[],'observed':[],'detail':{'A':[],'B':[]}}]}]})
        self.assertEqual(r['producer_check_candidates'],[]);self.assertEqual(len(r['excluded_checks']),1)
    def test_extra_query_does_not_disable_declared_conjunction(self):
        v,a=collection_tests.CollectionTests().analyze([{'method':'GET','path':'/loans?userId=1&bookId=2&description=label&id=99','status':200,'response':[{'id':4,'userId':1,'bookId':3}]}])
        findings=[x for x in v if x['reason']=='CONJUNCTIVE_FILTER_VIOLATION'];self.assertEqual(len(findings),1)
        self.assertEqual(findings[0]['details']['additional_query_names'],['description','id'])
    def test_query_create_delete_link_as_observation(self):
        t=lifecycle_tests.LifecycleTests()
        for rows,reason in [([{'method':'POST','suffix':'?description=create','status':201,'response':{'id':7}}, {'suffix':'/7?description=read','status':404}],'CREATED_RESOURCE_NOT_READABLE'),
                            ([{'method':'DELETE','suffix':'/7?description=delete','status':204},{'suffix':'/7?description=read','status':200}],'DELETED_RESOURCE_STILL_READABLE')]:
            v=t.run_flow(rows);self.assertEqual(v[0]['reason'],reason);self.assertEqual(v[0]['value'],'policy_observation')
    def test_copy_observations_require_nonempty_reference_evidence(self):
        from test_relational_semantics import run,row
        rows=[row('GET','/objects/1',{'id':1,'parts':[],'steps':[]}),row('POST','/objects/1/copy',{'id':2,'parts':[],'steps':[]})]
        self.assertEqual(run(rows)[0],[])

    def test_enum_is_not_inferred_as_reference(self):
        from test_relational_semantics import context,row
        from traffic import normalize
        from judge import analyze
        c=context();op=next(o for o in c['operations'] if o['key']=='GET /entries/{id}')
        op['responses']['200']['fields']={'foodId':{'constraints':{'type':'integer','enum':[7]}}}
        rows=[normalize(dict(r,t_utc=f'2026-11-02T00:00:0{i}Z'),{'line_1based':i+1}) for i,r in enumerate([row('GET','/foods/7',{},404),row('GET','/entries/2',{'id':2,'foodId':7})])]
        buf=io.StringIO();a=analyze(rows,c,buf,capture={})
        self.assertNotIn('REFERENCE_TO_OBSERVED_ABSENT_RESOURCE',buf.getvalue())

if __name__=='__main__':unittest.main()
