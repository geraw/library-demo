from pathlib import Path
import sys
import unittest
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from providers import evaluate, instant
from analyze_coverage import scoped_lock_links, parse_trap_context
from classify_measurements import analyze

CONTEXT={k:True for k in ['same_run','ordered','complete','same_resource','same_actor','no_intervening_write','same_pair','compatible_preconditions','relationship_verified','actor_scope_verified','trigger_scope_verified','no_intervening_trigger','view_scope_verified']}
SOURCE={'file':'fixture','sha256':'fixture','record':1}

def probe(family,**kwargs):return dict(family=family,source=SOURCE,context=CONTEXT,**kwargs)


class ProviderTests(unittest.TestCase):
    def test_published_provider_contract_matches_runtime_requirements(self):
        contract=json.loads((Path(__file__).resolve().parents[1]/'PROVIDER_CONTRACT.json').read_text())
        for family,required in contract['families'].items():
            self.assertEqual(set(evaluate({'family':family,'source':SOURCE})['missing']),set(required))
    def test_timestamp_precision_and_timezone_are_deterministic(self):
        self.assertNotEqual(instant('2026-10-21T10:00:00.000000001Z'),instant('2026-10-21T10:00:00.000000002Z'))
        self.assertEqual(instant('2026-10-21T10:00:00+02:00'),instant('2026-10-21T08:00:00Z'))
        with self.assertRaises(ValueError):instant('2026-10-21T10:00:00')
    def test_response_and_explicit_bound(self):
        self.assertTrue(evaluate(probe('RESPONSE',status=None,transport_error='timeout'))['facts']['transport_failure'])
        r=evaluate(probe('EDGE-1',status=201,value='x'*251,constraints={'maxLength':250}))
        self.assertTrue(r['facts']['explicit_bound_violated'])

    def test_readback_subtypes_and_time_equivalence(self):
        p=probe('RT-1',status=200,sent={'s':'ABCDE','m':'x','d':'2026-10-21T10:00:00+02:00'},readback={'s':'ABC','d':'2026-10-21T08:00:00Z'},readable_fields=['s','m','d'],field_formats={'d':'date-time'})
        r=evaluate(p);self.assertEqual(r['facts']['change_subtypes'],{'s':'truncation','m':'dropped'})
        p['context']={};self.assertEqual(evaluate(p)['status'],'not_evaluable')

    def test_partial_and_missing_snapshot(self):
        p=probe('ATOM-1-2',status=500,operation='update',before={'a':0,'b':0},after={'a':1,'b':0},request={'a':1,'b':1})
        self.assertEqual(evaluate(p)['facts']['atomicity'],'partial')
        del p['before'];p['verdict']='partial'
        self.assertEqual(evaluate(p)['status'],'not_evaluable')

    def test_create_duplicate_and_delete_commit(self):
        self.assertEqual(evaluate(probe('ATOM-1-2',status=500,operation='create',before=0,after=2,request={}))['facts']['atomicity'],'duplicate')
        self.assertEqual(evaluate(probe('ATOM-1-2',status=500,operation='delete',before=True,after=False,request={}))['facts']['atomicity'],'committed_despite_error')

    def test_pair_needs_actual_values(self):
        p=probe('EDGE-U',create={'status':201},update={'status':422})
        self.assertEqual(evaluate(p)['status'],'not_evaluable')
        p['create']['sent']='x';p['update']['sent']='x'
        self.assertTrue(evaluate(p)['facts']['update_rejects_create_accepted'])
        p['update']['sent']='y';self.assertEqual(evaluate(p)['status'],'not_evaluable')

    def test_known_failure_is_not_suppressed(self):
        p=probe('KNOWN',status=500,response='Internal Server Error',operation='update',trigger_time='2026-10-21T10:00:00Z',request_time='2026-10-21T10:00:02Z',definition={'statuses':[500],'operations':['update'],'window_seconds':10,'response_regex':'Internal'})
        f=evaluate(p)['facts'];self.assertTrue(f['known_failure_signature_match']);self.assertFalse(f['suppress_failure'])

    def test_cascade_and_view_require_policy(self):
        p=probe('CASCADE-1',parent_delete_status=204,child_read_status=200,cascade_required=True)
        self.assertTrue(evaluate(p)['facts']['child_still_present'])
        p['context']=dict(CONTEXT,relationship_verified=False);self.assertEqual(evaluate(p)['status'],'not_evaluable')
        v=probe('VIEW',expected_ids=[1,2],actual_ids=[1],membership_required=True)
        self.assertTrue(evaluate(v)['facts']['view_missing'])
        p=probe('CASCADE-1',parent_delete_status=204,child_read_status=403,cascade_required=True)
        self.assertEqual(evaluate(p)['status'],'not_evaluable')

    def test_adjacency_does_not_prove_causation(self):
        p=probe('ADJ',status=500,trigger_time='2026-10-21T10:00:00Z',request_time='2026-10-21T10:00:01Z',window_seconds=2)
        f=evaluate(p)['facts'];self.assertTrue(f['adjacency_qualified']);self.assertFalse(f['causation_proven'])

    def test_idempotency_and_links(self):
        p=probe('IDEM',status=500,first_request={'x':True},second_request={'x':1})
        self.assertFalse(evaluate(p)['facts']['repeated_write_qualified'])
        link=probe('LINK',operation='add_again',target_id=1,actual_ids=[1,1])
        self.assertTrue(evaluate(link)['facts']['link_violation'])

    def test_unique_scoped_log_and_ambiguous_join(self):
        row={'category':'research','method':'PUT','path':'/projects/1/tasks','status':500}
        line='time=2026-10-21T10:00:00Z method=PUT uri=/api/v1/projects/1/tasks status=500 err="database is locked"'
        self.assertIn(0,scoped_lock_links([row],line))
        self.assertEqual(scoped_lock_links([row,row],line),{})
        self.assertEqual(scoped_lock_links([row],line+'\n'+line),{})

    def test_context_name_never_supplies_actual_request(self):
        c=parse_trap_context('Release_EDGE_tag_name_nul')
        self.assertEqual(c['field'],'tag_name');self.assertIn('absent',c['evidence_level'])
        self.assertIsNone(parse_trap_context('GIT-C5'))

    def test_complete_email_pair_can_match_c7(self):
        p=probe('EDGE-U',id='p',product='gitea',product_version='28.1.0',run_id='r',entity='organization',field='email',create={'status':201,'sent':'invalid'},update={'status':422,'sent':'invalid'})
        r=analyze({'schema_version':'natchan-measurements/1','measurements':[p]})
        self.assertIn('GIT-C7',r['summary']['known_bug_ids'])
        del p['update']['sent'];r=analyze({'schema_version':'natchan-measurements/1','measurements':[p]})
        self.assertNotIn('GIT-C7',r['summary']['known_bug_ids'])


if __name__=='__main__':unittest.main()
