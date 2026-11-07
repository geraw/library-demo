"""Long-history controls: typed IDs, interference, re-creation and scope barriers."""
import copy,io,json,unittest
from contract_context import derive
from common import canonical,digest
from judge import analyze
from traffic import normalize

class LifecycleHistoryTests(unittest.TestCase):
    def run_case(self, rows, kind='integer', declared_query=False, resource='widgets'):
        item={'type':'object','properties':{'id':{'type':kind}}}
        param={'in':'path','name':'id','required':True,'schema':{'type':kind}}
        doc={'openapi':'3.0.3','info':{'description':'Creation is synchronously visible; completed deletion removes the exposed resource.'},'paths':{
          '/'+resource:{'post':{'summary':'Create object','responses':{'201':{'content':{'application/json':{'schema':item}}}}},'get':{'parameters':[{'in':'query','name':'q','schema':{'type':'string'}}],'responses':{'200':{}}}},
          '/'+resource+'/{id}':{'parameters':[param],'get':{'responses':{'200':{'content':{'application/json':{'schema':item}}},'404':{}}},'delete':{'responses':{'204':{}}},'put':{'responses':{'200':{}}}}}}
        if declared_query:doc['paths']['/'+resource+'/{id}']['get']['parameters']=[{'in':'query','name':'view','schema':{'type':'string'}}]
        c=derive(doc,digest(canonical(doc)));raw=[]
        for i,r in enumerate(copy.deepcopy(rows)):
            suffix=r.pop('suffix','');raw.append(normalize({'actor':'a','epoch':1,'case_id':'c','url':'http://local/'+resource+suffix,'method':'GET','status':200,**r},{'line_1based':i+1}))
        out=io.StringIO();analyze(raw,c,out,capture={'complete':True,'exclusive':True,'ordering':'serial'})
        return [v for v in map(json.loads,out.getvalue().splitlines()) if v.get('details',{}).get('lifecycle') and v['value'] in ('violation','policy_observation')]
    def create(self,id=7):return {'method':'POST','status':201,'response':{'id':id}}
    def test_integer_leading_zeros_and_neutral_names(self):
        for r in ('widgets','tasks','assets'):
            v=self.run_case([self.create(),{'suffix':'/0007','status':404}],resource=r)
            self.assertEqual(len(v),1);self.assertEqual(v[0]['value'],'violation')
    def test_string_identity_keeps_leading_zeros(self):
        self.assertEqual(self.run_case([self.create('7'),{'suffix':'/0007','status':404}],kind='string'),[])
    def test_other_query_read_does_not_erase_history(self):
        self.assertEqual(len(self.run_case([self.create(),{'suffix':'?q=x'},{'suffix':'/7','status':404}])),1)
    def test_declared_item_view_does_not_supply_readback(self):
        self.assertEqual(self.run_case([self.create(),{'suffix':'/7?view=other','status':404}],declared_query=True),[])
    def test_intervening_rejections_are_only_conditional(self):
        for method,suffix,status in [('POST','',400),('PUT','/7',405),('DELETE','/7',400)]:
            v=self.run_case([self.create(),{'method':method,'suffix':suffix,'status':status},{'suffix':'/7','status':404}])
            self.assertEqual(v[0]['value'],'policy_observation');self.assertEqual(v[0]['details']['intervening_mutations'],1)
    def test_successful_same_identity_write_invalidates(self):
        self.assertEqual(self.run_case([self.create(),{'method':'PUT','suffix':'/7','status':200},{'suffix':'/7','status':404}]),[])
    def test_other_creation_keeps_deletion_hypothesis(self):
        v=self.run_case([{'method':'DELETE','suffix':'/7','status':204},self.create(8),{'suffix':'/7'}]);self.assertEqual(v[0]['reason'],'DELETED_RESOURCE_STILL_READABLE');self.assertEqual(v[0]['value'],'policy_observation')
    def test_recreation_same_numeric_identity_cancels_deletion(self):
        self.assertEqual(self.run_case([{'method':'DELETE','suffix':'/0007','status':204},self.create(),{'suffix':'/7'}]),[])
    def test_ambiguous_successful_create_is_barrier(self):
        self.assertEqual(self.run_case([{'method':'DELETE','suffix':'/7','status':204},{'method':'POST','status':201,'response':{}},{'suffix':'/7'}]),[])
    def test_server_error_missing_answer_async_and_unknown_success_barriers(self):
        for method,suffix,status in [('POST','',500),('POST','',None),('POST','',202),('PATCH','/other/action',200)]:
            self.assertEqual(self.run_case([self.create(),{'method':method,'suffix':suffix,'status':status},{'suffix':'/7','status':404}]),[])
    def test_scope_changes_do_not_cross(self):
        for kw in [{'actor':'b'},{'epoch':2},{'case_id':'d'},{'url':'http://other/widgets/7'}]:
            self.assertEqual(self.run_case([self.create(),{'suffix':'/7','status':404,**kw}]),[])
    def test_repaired_readbacks_remove_findings(self):
        self.assertEqual(self.run_case([self.create(),{'method':'POST','status':400},{'suffix':'/0007','status':200}]),[])
        self.assertEqual(self.run_case([{'method':'DELETE','suffix':'/7','status':204},self.create(8),{'suffix':'/7','status':404}]),[])
