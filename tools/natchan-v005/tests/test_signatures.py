from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analyze_coverage import augment_gitea
from coverage_classifier import classify


def obs(facts,request=None,status=500):
    return dict(id='x',product='gitea',product_version='28.1.0',run_id='r',source={'file':'fixture'},
                entity='release',operation='create',status=status,request=request,facts=dict(entity='release',operation='create',**facts),fact_basis='recomputed')


class SignatureTests(unittest.TestCase):
    def test_c4_c5_c6_need_original_values_and_correlated_error(self):
        for id,key,request,family in [('GIT-C4','tag_name',{'tag_name':'bad tag'},'invalid_tag'),('GIT-C5','tag_name',{'tag_name':'a\x00b'},'git_argument_nul'),('GIT-C6','target_commitish',{'target_commitish':'bad target'},'parse_integer')]:
            o=obs({'correlated_error_family':family},request);augment_gitea([o])
            self.assertIn(id,classify([o],ROOT/'catalogs')['summary']['known_bug_ids'])
            o=obs({'correlated_error_family':family})
            self.assertNotIn(id,classify([o],ROOT/'catalogs')['summary']['known_bug_ids'])

    def test_explicit_conflicting_fact_is_not_missing_evidence(self):
        o=obs({'correlated_error_family':'missing_git_object'},{'tag_name':'normal'})
        augment_gitea([o]);r=classify([o],ROOT/'catalogs')
        for a in r['assessments']:
            self.assertNotIn('GIT-C4',[p['id'] for p in a['possible_known_bugs']])

    def test_c7_from_raw_request_pair_requires_preimage_and_same_actor(self):
        rows=[{'category':'research','logical_id':'Organization_EDGE_email_spaces','session':'A'},
              {'category':'research','method':'GET','path':'/orgs/existing','status':200,'session':'A'},
              {'category':'research','logical_id':'Organization_EDGEU_email_spaces','session':'A','path':'/orgs/existing'}]
        a=obs({}, {'email':'bad email'},201);a.update(id='a',entity='organization',operation='create');a['facts'].update(entity='organization');a['source']['record']=0
        b=obs({}, {'email':'bad email'},422);b.update(id='b',entity='organization',operation='update',response='Invalid email');b['facts'].update(entity='organization',operation='update');b['source']['record']=2
        augment_gitea([a,b],rows)
        self.assertIn('GIT-C7',classify([a,b],ROOT/'catalogs')['summary']['known_bug_ids'])
        rows[1]['session']='B';b['facts']={'entity':'organization','operation':'update'}
        augment_gitea([a,b],rows)
        self.assertNotIn('GIT-C7',classify([a,b],ROOT/'catalogs')['summary']['known_bug_ids'])


if __name__=='__main__':unittest.main()
