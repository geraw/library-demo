import io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contract_context import derive
from common import canonical,digest
from judge import analyze
from traffic import normalize

class LifecycleTests(unittest.TestCase):
 def run_flow(self, rows, resource='widgets', capture=None):
  schema={'type':'object','properties':{'id':{'type':'integer'},'name':{'type':'string'}}}
  doc={'openapi':'3.0.3','paths':{
   '/'+resource:{'post':{'summary':'Create a resource','responses':{'201':{'description':'Created','content':{'application/json':{'schema':schema}}}}}},
   '/'+resource+'/{id}':{'get':{'responses':{'200':{'description':'OK','content':{'application/json':{'schema':schema}}},'404':{'description':'Absent'}}},'delete':{'responses':{'204':{'description':'Deleted'},'202':{'description':'Accepted'}}}}
  }}
  context=derive(doc,digest(canonical(doc))); out=io.StringIO()
  raw=[]
  for i,row in enumerate(rows):
   d={'actor':'tester','epoch':1,'case_id':'a','url':'http://localhost/'+resource+row.pop('suffix',''),'method':'GET','status':200,**row}
   raw.append(normalize(d,{'line_1based':i+1,'sha256':'abc'}))
  analyze(raw,context,out,capture=capture or {'complete':True,'exclusive':True,'ordering':'serial'})
  return [json.loads(x) for x in out.getvalue().splitlines() if json.loads(x)['reason'].startswith(('CREATED_RESOURCE','DELETED_RESOURCE'))]
 def create(self):return {'method':'POST','status':201,'response':{'id':7,'name':'x'}}
 def test_create_missing_generic_names(self):
  for name in ['widgets','tasks','projects','documents']:
   v=self.run_flow([self.create(),{'suffix':'/7','status':404}],name);self.assertEqual(v[0]['value'],'policy_observation')
 def test_create_control(self):self.assertEqual(self.run_flow([self.create(),{'suffix':'/7'}])[0]['value'],'consistent')
 def test_delete_violation(self):self.assertEqual(self.run_flow([{'suffix':'/7','method':'DELETE','status':204},{'suffix':'/7'}])[0]['value'],'policy_observation')
 def test_delete_control(self):self.assertEqual(self.run_flow([{'suffix':'/7','method':'DELETE','status':204},{'suffix':'/7','status':404}])[0]['value'],'consistent')
 def test_malformed_route(self):self.assertEqual(self.run_flow([self.create(),{'suffix':'/7/7','status':404}]),[])
 def test_reset(self):self.assertEqual(self.run_flow([self.create(),{'suffix':'/7','status':404,'epoch':2}]),[])
 def test_actor(self):self.assertEqual(self.run_flow([self.create(),{'suffix':'/7','status':404,'actor':'other'}]),[])
 def test_async(self):self.assertEqual(self.run_flow([{'suffix':'/7','method':'DELETE','status':202},{'suffix':'/7'}]),[])
 def test_recreate(self):self.assertEqual(self.run_flow([{'suffix':'/7','method':'DELETE','status':204},self.create(),{'suffix':'/7'}])[0]['value'],'consistent')
 def test_query(self):
  v=self.run_flow([self.create(),{'suffix':'/7?view=other','status':404}])
  self.assertEqual(v[0]['value'],'policy_observation');self.assertFalse(v[0]['details']['query_semantics_established'])
 def test_concurrency(self):self.assertEqual(self.run_flow([self.create(),{'suffix':'/7','status':404}],capture={'complete':True,'exclusive':True,'ordering':'concurrent'}),[])
if __name__=='__main__':unittest.main()
