import importlib.util,json,logging,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server_v001 import app_factory
from oracle_v001 import evaluate,read_trace
from analyze_v001 import freeze,analyze
logging.disable(logging.CRITICAL)

class Exchange:
 def __init__(self,client):self.c=client
 def req(self,method,path,body=None):return self.c.open(path,method=method,json=body)
 def create(self,path,body):
  r=self.req('POST',path,body)
  if r.status_code!=201:raise AssertionError((path,r.status_code,r.json))
  return r.json['id']
 def user(self,n):return self.create('/users',{'name':n})
 def book(self,n):return self.create('/books',{'title':n})

def scenario(code,c):
 x=Exchange(c)
 if code=='B1':
  b=x.book('book');x.req('GET','/books/'+str(b))
 elif code=='B2':
  b=x.book('book');x.req('DELETE','/books/'+str(b));x.req('GET','/books/'+str(b))
 elif code=='B3':
  u=x.user('one');v=x.user('two');b=x.book('book');x.create('/loans',{'userId':u,'bookId':b});x.req('POST','/loans',{'userId':v,'bookId':b});x.req('GET','/loans')
 elif code=='B4':
  u=x.user('one');v=x.user('two');a=x.book('a');b=x.book('b');x.create('/loans',{'userId':u,'bookId':a});x.create('/loans',{'userId':v,'bookId':b});x.req('GET',f'/loans?userId={u}&bookId={b}')
 elif code=='B5':
  u=x.user('one');a=x.book('a');b=x.book('b');h=x.create('/holds',{'userId':u,'bookId':a});x.create('/holds',{'userId':u,'bookId':b});x.req('DELETE','/holds/'+str(h));x.req('GET','/holds')
 elif code=='B6':
  u=x.user('one');b=x.book('book');x.req('DELETE','/books/'+str(b));x.req('POST','/loans',{'userId':u,'bookId':b})

class BenchmarkTest(unittest.TestCase):
 def capture(self,mutation,callback):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name);trace=root/'http.jsonl'
  with patch.dict(os.environ,{'LIBRARY_MUTATIONS':mutation}):
   gateway=app_factory(ROOT/('sut_baseline_v001.py' if mutation=='none' else 'sut_mutants_v001.py'),trace,ROOT/'openapi.json','secret')
  c=gateway.test_client();self.assertEqual(c.post('/__bench__/case',json={'case':'one'},headers={'X-Bench-Token':'secret'}).status_code,200)
  callback(c);return root,read_trace(trace)
 def test_ground_truth_matrix(self):
  matrix={}
  for mutation in ['none','B1','B2','B3','B4','B5','B6']:
   matrix[mutation]={}
   for case in ['B1','B2','B3','B4','B5','B6']:
    with self.subTest(mutation=mutation,case=case):
     _,rows=self.capture(mutation,lambda c:scenario(case,c));result=evaluate(rows);observed=result['confirmed_bug_ids'];matrix[mutation][case]=observed
     if mutation=='none':self.assertEqual(observed,[])
     if mutation==case:self.assertIn(case,observed)
     if mutation!='none':self.assertTrue(set(observed)<={mutation},observed)
 def test_baseline_deletes_empty_204_and_strict_rules(self):
  def check(c):
   x=Exchange(c);u=x.user('one');v=x.user('two');a=x.book('a');b=x.book('b');x.create('/loans',{'userId':u,'bookId':a})
   self.assertEqual(x.req('POST','/loans',{'userId':u,'bookId':b}).status_code,400)
   self.assertEqual(x.req('POST','/loans',{'userId':v,'bookId':a}).status_code,400)
   self.assertEqual(x.req('DELETE','/books/'+str(a)).status_code,400)
   h=x.create('/holds',{'userId':u,'bookId':a});x.create('/holds',{'userId':u,'bookId':a})
   r=x.req('DELETE','/holds/'+str(h));self.assertEqual((r.status_code,r.data),(204,b''))
   r=x.req('DELETE',f'/loans/{u}/{a}');self.assertEqual((r.status_code,r.data),(204,b''))
   r=x.req('DELETE','/books/'+str(b));self.assertEqual((r.status_code,r.data),(204,b''))
   r=x.req('DELETE','/users/'+str(v));self.assertEqual((r.status_code,r.data),(204,b''))
  self.capture('none',check)
 def test_schema_and_successful_baseline_responses(self):
  from jsonschema import Draft4Validator,RefResolver
  contract=json.loads((ROOT/'openapi.json').read_text());resolver=RefResolver.from_schema(contract)
  def check(c):
   x=Exchange(c);u=x.user('u');b=x.book('b');x.create('/loans',{'userId':u,'bookId':b});x.create('/holds',{'userId':u,'bookId':b});x.req('GET','/books/'+str(b));x.req('GET','/loans');x.req('GET','/holds')
  _,rows=self.capture('none',check)
  for row in rows:
   if row.get('role')!='tool':continue
   from urllib.parse import urlsplit
   path=urlsplit(row['url']).path
   if path.startswith('/books/'):path='/books/{book_id}'
   op=contract['paths'][path][row['method'].lower()];response=op['responses'][str(row['status'])]
   if 'content' in response:Draft4Validator(response['content']['application/json']['schema'],resolver=resolver).validate(row['response'])
 def test_boundary_isolation(self):
  def check(c):
   b=Exchange(c).book('b');c.post('/__bench__/case',json={'case':'two'},headers={'X-Bench-Token':'secret'});c.get('/books/'+str(b))
  _,rows=self.capture('B1',check);self.assertEqual(evaluate(rows)['confirmed_bug_ids'],[])
 def test_insufficient_readbacks_not_negative_score(self):
  _,rows=self.capture('B5',lambda c:Exchange(c).user('u'));r=evaluate(rows);self.assertEqual(r['coverage']['B5']['status'],'NOT_EVALUATED')
 def test_natchan_independent_raw_input(self):
  for mutation in ['none','B1','B2','B3','B4','B5','B6']:
   with self.subTest(mutation=mutation):
    folder,rows=self.capture(mutation,lambda c:scenario('B6' if mutation=='none' else mutation,c))
    engine=ROOT/'vendor/natchan-box-v009';f=folder/'freeze';freeze(ROOT/'openapi.json',engine,f);analyze(folder,ROOT/'openapi.json',engine,f,'sequence-local')
    result=json.loads((folder/'natchan-result/result.json').read_text());self.assertEqual(result['exit_code'],0);self.assertTrue(result['analyzer_version'].startswith('009'))
    raw=(folder/'natchan-traffic.jsonl').read_text();self.assertNotIn('confirmed_bug_ids',raw);self.assertNotIn('MUTATIONS',raw)
    request=json.loads((folder/'natchan-request.json').read_text());self.assertNotIn('oracle',json.dumps(request))
 def test_baseline_changes_only_successful_delete_statuses(self):
  original=(ROOT/'vendor/sut_original.py').read_text()
  for entity in ['User','Book','Loan','Hold']:
   original=original.replace('return jsonify({"message": "'+entity+' deleted"}), 200','return "", 204')
  self.assertEqual(original,(ROOT/'sut_baseline_v001.py').read_text())
 def test_catalog_and_model_integrity(self):
  original=(ROOT/'java/StrictGuidedRun.original.java').read_text().replace('\r\n','\n').rstrip('\n');patched=(ROOT/'java/StrictGuidedRun.java').read_text()
  boundary='    private static RunResult runScenario('
  self.assertEqual(original.split(boundary)[0],patched.split(boundary)[0])
  s=(ROOT/'model/spec/js/interfaces.library.js').read_text();self.assertEqual(s.count('hasExpectedCode(e, 204);'),4)
  self.assertNotIn('const pvg =',s);self.assertIn('pvg.rtv.set',s)
  self.assertIn('!hasLoanForUser',(ROOT/'model/spec/js/dal.js').read_text())
 def test_reject_reset_from_generator(self):
  def check(c):self.assertEqual(c.post('/reset',json={}).status_code,403)
  self.capture('none',check)

if __name__=='__main__':unittest.main(verbosity=2)
