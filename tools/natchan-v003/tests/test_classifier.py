import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from classifier import classify, derived, same, normalized_message


def obs(**kw):
    return dict(id='o1',product='library',product_version='issta-v006',run_id='r1',source={'member':'trace.jsonl','line':1},**kw)


def known(report):return report['summary']['known_bug_ids']
def patterns(report):return [a.get('catalog_id') for a in report['assessments']]


class ClassifierTests(unittest.TestCase):
    def test_library_known_bug5(self):
        o=obs(facts=dict(resource='holds',target_existed_before=True,non_target_removed=True,same_owner_non_target_removed=True),fact_basis='recomputed')
        r=classify([o]);self.assertEqual(['LIB-ISSTA-BUG-5'],known(r));self.assertIn('GEN-COLLATERAL_DELETE',patterns(r))

    def test_same_symptom_missing_owner_is_not_known(self):
        r=classify([obs(facts=dict(resource='holds',target_existed_before=True,non_target_removed=True),fact_basis='recomputed')])
        self.assertEqual([],known(r))
        self.assertTrue(any(a.get('possible_known_bugs') for a in r['assessments']))

    def test_version_and_product_not_interchangeable(self):
        o=obs(facts=dict(known_existing_book=True,existing_read_404=True),fact_basis='recomputed')
        self.assertEqual(['LIB-ISSTA-BUG-4'],known(classify([o])))
        o['product_version']='other';self.assertEqual([],known(classify([o])))
        o['product']='vikunja';self.assertEqual([],known(classify([o])))

    def test_imported_verdict_label_does_not_match(self):
        o=obs(facts=dict(known_existing_book=True,existing_read_404=True),fact_basis='imported_oracle')
        self.assertEqual([],known(classify([o])))

    def test_library_loan_rules_not_ambiguous(self):
        o=obs(facts=dict(legal_loan_rejected=True,active_for_user=3,prior_pair_loans=0),fact_basis='recomputed')
        self.assertEqual(['LIB-ISSTA-BUG-1'],known(classify([o])))
        o['facts'].update(active_for_user=0,prior_pair_loans=2)
        self.assertEqual(['LIB-ISSTA-BUG-2'],known(classify([o])))
        o['facts'].update(active_for_user=3)
        self.assertEqual([],known(classify([o])))

    def test_atomicity_and_error_both_reported(self):
        o=obs(status=500,before={'a':1,'b':2},request={'a':3,'b':4},after={'a':3,'b':2},state_evidence=dict(same_resource=True,same_actor=True,ordered=True,no_intervening_write=True,complete=True))
        o['product']='vikunja';r=classify([o]);self.assertIn('GEN-PARTIAL_WRITE',patterns(r));self.assertIn('GEN-SERVER_ERROR',patterns(r));self.assertEqual([],known(r))
        o['state_evidence']['no_intervening_write']=False
        self.assertNotIn('GEN-PARTIAL_WRITE',patterns(classify([o])))

    def test_readback_normalization_and_boolean(self):
        o=obs(status=200,request={'a':1,'date':'2026-01-01T00:00:00Z'},after={'a':1.0,'date':'2026-01-01T02:00:00+02:00'},readable_writable_fields=['a','date'],field_formats={'date':'date-time'},state_evidence=dict(same_resource=True,same_actor=True,ordered=True,no_intervening_write=True,complete=True))
        self.assertFalse(derived(o)['silent_change'])
        o['after']['a']=True;self.assertTrue(derived(o)['silent_change'])
        self.assertFalse(same(True,1))

    def test_accepted_bound_is_pattern_not_known_bug(self):
        o=obs(status=201,field='title',request={'title':''},contract={'field_constraints':{'minLength':1}})
        self.assertIn('GEN-BOUND_NOT_ENFORCED',patterns(classify([o])))
        self.assertEqual([],known(classify([o])))

    def test_draft_vikunja_does_not_match(self):
        o=obs(facts={'reported_f01_signature_verified':True},fact_basis='recomputed');o['product']='vikunja'
        r=classify([o]);self.assertEqual([],known(r));self.assertIn('VIK-F01',r['catalog_coverage']['draft_entries'])

    def test_grouping_across_runs_preserves_versions(self):
        a=obs(status=500);b=copy.deepcopy(a);b.update(id='o2',run_id='r2');r=classify([a,b]);self.assertEqual(2,r['groups'][0]['occurrence_count'])
        self.assertEqual(['r1','r2'],r['groups'][0]['runs'])
        b['product_version']='new';self.assertEqual(2,len(classify([a,b])['groups']))

    def test_duplicate_ids_fail(self):
        with self.assertRaisesRegex(ValueError,'Duplicate observation'):classify([obs(),obs()])

    def test_log_normalization_keeps_constraint_numbers(self):
        self.assertEqual('MaxSize 250 id=<id>',normalized_message('MaxSize 250 id=543'))

    def test_unknown_403_is_not_deleted(self):
        self.assertEqual([],known(classify([obs(status=403)])))

    def test_pair_requires_identity_and_compatible_preconditions(self):
        a=obs(operation='create',field='title',entity='task',status=201,request={'title':'x'},pair_id='p',pair_evidence=dict(same_schema_context=True,compatible_preconditions=True));a['product']='vikunja'
        b=copy.deepcopy(a);b.update(id='o2',operation='update',status=400)
        self.assertIn('GEN-CREATE_UPDATE_DIVERGENCE',patterns(classify([a,b])))
        b['pair_evidence']['compatible_preconditions']=False
        self.assertNotIn('GEN-CREATE_UPDATE_DIVERGENCE',patterns(classify([a,b])))

    def test_normalizer_does_not_promote_imported_oracle_claims(self):
        import tempfile
        from normalize import convert
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'log.jsonl';path.write_text('{"code":500,"oracle":{"non_target_removed":true}}')
            document=convert(path,dict(format='jsonl',defaults={'product':'gitea','run_id':'r'},fields={'status':'code','facts':'oracle'}))
            self.assertEqual(path.name,document['observations'][0]['source']['filename'])
            r=classify(document['observations']);self.assertIn('GEN-SERVER_ERROR',patterns(r));self.assertNotIn('GEN-COLLATERAL_DELETE',patterns(r))

    def test_malformed_catalog_never_silently_enabled(self):
        import tempfile
        from classifier import load_catalogs
        with tempfile.TemporaryDirectory() as folder:
            doc=json.loads((Path(__file__).resolve().parents[1]/'examples'/'bug-template.json').read_text())
            doc['entries'][0].update(status='active',all=[])
            Path(folder,'bad.json').write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'Unconditional'):load_catalogs(folder)
            doc['entries'][0]['all']=[dict(fact='x',op='eq',value=True)]
            Path(folder,'bad.json').write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'explicit product and versions'):load_catalogs(folder)

    def test_full_compound_pair_keeps_all_symptoms(self):
        doc=json.loads((Path(__file__).resolve().parents[1]/'examples'/'synthetic-vikunja-pair.json').read_text())
        report=classify(doc['observations'])
        ids=patterns(report)
        self.assertIn('GEN-CREATE-UPDATE-PARTIAL-COMPOUND',ids)
        self.assertIn('GEN-SERVER_ERROR',ids)
        self.assertIn('GEN-PARTIAL_WRITE',ids)
        self.assertIn('GEN-SILENT_CHANGE',ids)
        self.assertEqual([],known(report))

    def test_healthy_rollback_has_no_partial_write(self):
        o=obs(status=500,before={'a':'old','b':'old'},request={'a':'new','b':'new'},after={'a':'old','b':'old'},state_evidence=dict(same_resource=True,same_actor=True,ordered=True,no_intervening_write=True,complete=True))
        self.assertEqual('rolled_back',derived(o)['atomicity'])
        self.assertNotIn('GEN-PARTIAL_WRITE',patterns(classify([o])))

    def test_log_correlates_only_with_same_request_and_run(self):
        o=obs(status=500,request_id='req-1',server_log=dict(request_id='req-1',run_id='r1',message='database is locked'))
        self.assertIn('GEN-SERVER_LOCK_EVIDENCE',patterns(classify([o])))
        o['server_log']['run_id']='other'
        self.assertNotIn('GEN-SERVER_LOCK_EVIDENCE',patterns(classify([o])))

    def test_gitea_size_restriction_is_candidate_not_known_bug(self):
        o=obs(status=400,entity='organizations',field='name',request={'name':'long-name'},response={'error':'MaxSize exceeded'},contract={'field_constraints':{}});o['product']='gitea'
        self.assertIn('GITEA-ORG-NAME-RESTRICTION',patterns(classify([o])))
        self.assertEqual([],known(classify([o])))
