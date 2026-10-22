import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'natchan-v005'))
from raw_sequences import update_state, augment
from coverage_classifier import classify


class RawStateTests(unittest.TestCase):
    def sequence(self):
        before = dict(id=4, title='old', milestone=None)
        after = dict(id=4, title='new', milestone=None)
        return [dict(method=m, path='/repos/u/r/issues/1', status=s, session='A', t_rel_ms=t,
                     response=json.dumps(b), input=req)
                for m,s,t,b,req in [('GET',200,1,before,None),('PATCH',500,2,{},dict(title='new',milestone=99)),('GET',200,3,after,None)]]

    def test_partial(self):
        result=update_state(*self.sequence())
        self.assertEqual(result['atomicity'],'partial')
        self.assertEqual(result['raw_changed_field_outcomes'],{'title':'applied','milestone':'kept'})

    def test_wrong_resource_rejected(self):
        rows=self.sequence();rows[2]['path']='/repos/u/r/issues/2'
        self.assertIsNone(update_state(*rows))

    def test_wrong_actor_rejected(self):
        rows=self.sequence();rows[2]['session']='B'
        self.assertIsNone(update_state(*rows))

    def test_reordered_clock_rejected(self):
        rows=self.sequence();rows[2]['t_rel_ms']=0
        self.assertIsNone(update_state(*rows))

    def test_missing_preimage_rejected(self):
        rows=self.sequence();rows[0]['response']='{}'
        self.assertIsNone(update_state(*rows))

    def test_unchanged_title_is_rollback(self):
        rows=self.sequence();rows[2]['response']=rows[0]['response']
        self.assertEqual(update_state(*rows)['atomicity'],'rolled_back')

    def test_unknown_value_is_not_partial(self):
        rows=self.sequence();rows[2]['response']=json.dumps(dict(id=4,title='third',milestone=None))
        self.assertEqual(update_state(*rows)['atomicity'],'unknown')

    def test_changed_identity_rejected(self):
        rows=self.sequence();rows[2]['response']=json.dumps(dict(id=5,title='new',milestone=None))
        self.assertIsNone(update_state(*rows))

    def test_intervening_write_prevents_join_and_producer_verdict_ignored(self):
        rows=self.sequence();rows.insert(2,dict(method='PATCH',path=rows[1]['path'],status=200,session='A',t_rel_ms=2.5,response='{}',input={}))
        rows=[dict(r,category='research') for r in rows]
        values=[dict(source={'record':i},facts={}) for i in range(len(rows))]
        augment(values,rows,None)
        self.assertNotIn('atomicity',values[1]['facts'])
        rows.append(dict(category='atomicity-check',verdict='partial'))
        augment(values,rows,None)
        self.assertNotIn('atomicity',values[1]['facts'])

    def test_c11_needs_actor_payload_and_correlated_log(self):
        rows=[dict(category='research',method='GET',path='/user',status=200,session='A',response='{"id":2,"login":"u"}'),dict(category='research',method='POST',path='/repos/u/r/pulls',status=500,session='A',input={'reviewers':['u']})]
        o=dict(source={'record':1},entity='pullrequest',operation='create',status=500,facts={},server_message="poster of pr can't be reviewer [user_id: 2, repo_id: 1]",correlated_log={'basis':'unique'})
        augment([o],rows,None);self.assertTrue(o['facts']['self_reviewer_error_verified'])
        for key,value in [('correlated_log',None),('server_message',"poster of pr can't be reviewer [user_id: 3]")]:
            changed=copy.deepcopy(o);changed['facts']={};changed[key]=value
            augment([changed],rows,None);self.assertNotIn('self_reviewer_error_verified',changed['facts'])

    def test_c11_catalog_is_version_qualified(self):
        o=dict(source={'file':'synthetic-control','record':0},id='x',product='gitea',product_version='28.1.0',run_id='r',entity='pullrequest',operation='create',status=500,fact_basis='recomputed',facts=dict(entity='pullrequest',operation='create',self_reviewer_error_verified=True))
        def ids(value):
            return {x['catalog_id'] for x in classify([value],Path(__file__).resolve().parents[1]/'catalogs')['assessments'] if x['status']=='matched'}
        self.assertIn('GIT-C11',ids(o))
        o['product_version']='unknown';self.assertNotIn('GIT-C11',ids(o))

    def test_pr_catalog_does_not_broaden_issue_signature(self):
        o=dict(source={'file':'synthetic-control','record':0},id='x',product='gitea',product_version='28.1.0',run_id='r',entity='pullrequest',operation='update',status=500,fact_basis='recomputed',facts=dict(entity='pullrequest',operation='update',correlated_error_family='missing_milestone'))
        ids={x['catalog_id'] for x in classify([o],Path(__file__).resolve().parents[1]/'catalogs')['assessments'] if x['status']=='matched'}
        self.assertIn('GIT-C2-PR',ids);self.assertNotIn('GIT-C2',ids)


if __name__=='__main__':unittest.main()
