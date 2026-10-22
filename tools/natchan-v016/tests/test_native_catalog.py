"""Synthetic protocol traces test the existing catalog bridge, not a live SUT."""
import copy,importlib.util,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('bridge',ROOT/'analyze.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
PROFILE=json.loads((ROOT/'profiles/gitea-lifecycle.json').read_text())
def trace():
 rows=[]
 def add(role,method,path,status,request=None,response=None,actor='B'):
  rows.append(dict(group='g',role=role,method=method,path=path,status=status,request=request,response=response,actor=actor))
 path='/repos/a/r/issues/1'
 add('version','GET','/version',200,response={'version':'28.1.0'})
 add('root_fixture','POST','/user/repos',201,response={'id':19},actor='A')
 add('baseline_B','GET',path,200,response={'id':27,'body':'old','milestone':{'id':8},'repository':{'id':19}})
 add('transition_A','DELETE','/repos/a/r/milestones/8',204,actor='A')
 add('write_B','PATCH',path,500,{'milestone':8,'body':'new'},response={'message':''})
 for actor in ['A','B']:add('probe_'+actor,'GET',path,200,response={'id':27,'body':'new','milestone':None,'repository':{'id':19}},actor=actor)
 raw=('\n'.join('INFO SHARED_EVIDENCE '+json.dumps(r) for r in rows)+'\n').encode()
 log=b'2026/10/22 18:13:09 issue.go:817:EditIssue() [E] milestone does not exist [id: 8, repo_id: 19]\n2026/10/22 18:13:09 HTTPRequest [I] router: completed PATCH /api/v1/repos/a/r/issues/1 for 127.0.0.1:1, 500 Internal Server Error\n'
 return raw,log

def classify(raw,log,profile=PROFILE):
 observations=m.adapt(m.parse_native(raw),log,profile,'synthetic')
 return m.classifier.classify(observations,ROOT/'vendor/catalogs')
class Tests(unittest.TestCase):
 def test_existing_catalog_matches_c2_with_predicate_witnesses(self):
  raw,log=trace();r=classify(raw,log);matches=[x for x in r['assessments'] if x.get('catalog_id')=='GIT-C2']
  self.assertEqual(len(matches),1);self.assertTrue(all(c['satisfied'] for c in matches[0]['checks']))
  observation=next(o for o in r['observations'] if o['id']==matches[0]['observation_id'])
  self.assertTrue(observation['facts']['deleted_reference_context_verified'])
  self.assertTrue(observation['facts']['field_persisted_despite_error'])
  self.assertEqual({w['kind'] for w in observation['witnesses']},{'error_log','router_completion','root_identity','item_root_identity','before','persisted_readback','deleted_reference'})
 def test_missing_log_does_not_match(self):
  raw,log=trace();self.assertNotIn('GIT-C2',classify(raw,b'')['summary']['known_bug_ids'])
 def test_wrong_reference_field_does_not_match(self):
  raw,log=trace();rows=m.parse_native(raw);rows[4]['request']={'assignee':8,'body':'new'}
  obs=m.adapt(rows,log,PROFILE,'test');self.assertNotIn('GIT-C2',m.classifier.classify(obs,ROOT/'vendor/catalogs')['summary']['known_bug_ids'])
 def test_unknown_version_and_wrong_product_do_not_match(self):
  raw,log=trace();raw=raw.replace(b'28.1.0',b'99.9.9');self.assertNotIn('GIT-C2',classify(raw,log)['summary']['known_bug_ids'])
  raw,log=trace();profile=copy.deepcopy(PROFILE);profile['product']='vikunja';self.assertNotIn('GIT-C2',classify(raw,log,profile)['summary']['known_bug_ids'])
 def test_wrong_target_or_root_or_router_does_not_match(self):
  raw,log=trace()
  for wrong in [log.replace(b'id: 8,',b'id: 9,'),log.replace(b'repo_id: 19',b'repo_id: 20'),log.replace(b'/issues/1',b'/issues/2')]:
   self.assertNotIn('GIT-C2',classify(raw,wrong)['summary']['known_bug_ids'])
 def test_ambiguous_log_does_not_match(self):
  raw,log=trace();self.assertNotIn('GIT-C2',classify(raw,log+log)['summary']['known_bug_ids'])
 def test_404_is_not_known_server_error(self):
  raw,log=trace();raw=raw.replace(b'"status": 500',b'"status": 404');self.assertNotIn('GIT-C2',classify(raw,log)['summary']['known_bug_ids'])
 def test_one_occurrence_two_tags_and_cached_verdict_ignored(self):
  raw,log=trace()
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'input.zip'
   with zipfile.ZipFile(p,'w') as z:
    z.writestr('native.log',raw);z.writestr('sut.log',log);z.writestr('observations.json',json.dumps({'known_bugs':['GIT-C1'],'findings':[]}))
   r=m.analyze_archive(p);self.assertEqual(r['counts']['known_bug_occurrences'],1)
   self.assertEqual(r['findings'][0]['known_bugs'],['GIT-C2']);self.assertEqual(set(r['findings'][0]['tags']),{'SERVER_5XX','FIELD_PERSISTED_DESPITE_ERROR'})
 def test_successful_write_is_not_c2(self):
  raw,log=trace();raw=raw.replace(b'"status": 500',b'"status": 201');self.assertNotIn('GIT-C2',classify(raw,log)['summary']['known_bug_ids'])
 def test_tampered_manifest_rejected(self):
  raw,log=trace()
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'input.zip'
   with zipfile.ZipFile(p,'w') as z:
    z.writestr('native.log',raw);z.writestr('sut.log',log);z.writestr('EXPORT_g026.json',json.dumps({'sha256':{'native.log':'wrong'}}))
   with self.assertRaises(ValueError):m.analyze_archive(p)
if __name__=='__main__':unittest.main()
