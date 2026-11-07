import io,json,tempfile,unittest
from pathlib import Path
import test_state_semantics as state_tests
from traffic import exchanges
from contract_context import derive
from common import canonical,digest
from judge import analyze
import test_lifecycle as lifecycle_tests


class Step2Acceptance(unittest.TestCase):
    def test_journal_decodes_and_whitelists(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            p.write_text('\n'.join(json.dumps(r) for r in [
                {'category':'check','pass':False},
                {'category':'research','method':'POST','path':'/__sbt/session','status':200},
                {'category':'research','method':'GET','path':'/things/1','status':200,'session':'A',
                 'response':'{"id":1}', 'oracle':'B1','known_bug_id':'B2','pass':False}]))
            stats={};rows=list(exchanges(p,'journal-jsonl','fixture',stats))
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['response'],{'id':1})
            self.assertIsNotNone(rows[0]['actor']);self.assertIsNone(rows[0]['epoch'])
            self.assertNotIn('oracle',rows[0]);self.assertEqual(stats['ignored_non_http'],2)

    def test_nested_lifecycle_preserves_parent_identity(self):
        v=lifecycle_tests.LifecycleTests().run_flow([
            {'method':'POST','status':201,'response':{'id':7}},
            {'suffix':'/7','status':404}],resource='spaces/4/widgets')
        self.assertEqual(v[0]['reason'],'CREATED_RESOURCE_NOT_READABLE')

    def test_identity_wrong_type_not_tracked(self):
        self.assertEqual(lifecycle_tests.LifecycleTests().run_flow([
            {'method':'POST','status':201,'response':{'id':'7'}},
            {'suffix':'/7','status':404}]),[])

    def test_contradicted_serial_disables_lifecycle(self):
        self.assertEqual(lifecycle_tests.LifecycleTests().run_flow([
            {'method':'POST','status':201,'response':{'id':7}},
            {'suffix':'/7','status':404}],capture={'complete':True,'exclusive':True,'ordering':'serial','_contradicted_serial':True}),[])

    def test_intervening_mutation_downgrades_lifecycle(self):
        result=lifecycle_tests.LifecycleTests().run_flow([
            {'method':'POST','status':201,'response':{'id':7}},
            {'method':'POST','status':201,'response':{'id':8}},
            {'suffix':'/7','status':404}])
        self.assertEqual(result[0]['value'],'policy_observation')
        self.assertEqual(result[0]['details']['intervening_mutations'],1)

    def test_policy_requires_affirmative_whole_sentence(self):
        from semantic_policy import derive_policies
        self.assertEqual(derive_policies({'info':{'description':'It is not true that creation is synchronously visible.'}}),{})
        self.assertIn('creation_visible',derive_policies({'info':{'description':'Creation is synchronously visible.'}}))

    def test_legacy_provider_matches_frozen_source(self):
        import hashlib
        e=Path(__file__).resolve().parents[1]
        p=json.loads((e/'historical-provider-provenance.json').read_text())
        self.assertEqual(hashlib.sha256((e/'historical_providers.py').read_bytes()).hexdigest(),p['sha256'])


class HistoricalIntegration(unittest.TestCase):
    setUp = state_tests.StateTests.setUp
    refreeze = state_tests.StateTests.refreeze
    rows = state_tests.StateTests.rows
    invoke = state_tests.StateTests.invoke
    verdicts = state_tests.StateTests.verdicts
    prepare = state_tests.StateTests.prepare
    row = state_tests.StateTests.row
    flow = state_tests.StateTests.flow
    semantic = state_tests.StateTests.semantic
    def test_failed_400_partial_and_rollback(self):
        for stored,reason in [({'title':'new','owner_id':1},'FAILED_WRITE_PARTIAL'),({'title':'old','owner_id':1},'FAILED_WRITE_UNCHANGED')]:
            v,_=self.semantic(self.flow(status=400,stored=stored),'S5',reason)
            self.assertEqual(v[0]['reason'],reason)
            self.assertEqual(v[0]['details']['historical_provider'],'ATOM-1-2')

    def test_old_capture_observation_never_claims_isolation(self):
        rows=self.flow(status=500,stored={'title':'new','owner_id':1})
        for i,r in enumerate(rows):r.pop('epoch');r['t_utc']=f'2026-11-02T00:00:0{i}Z'
        self.rows(rows);result,out=self.invoke('old-capture')
        self.assertEqual(result['exit_code'],0)
        v=[r for r in self.verdicts(out) if r['reason']=='OBSERVED_FAILED_WRITE_PARTIAL']
        self.assertEqual(len(v),1);self.assertEqual(v[0]['value'],'policy_observation')
        self.assertFalse(v[0]['details']['background_concurrency_excluded'])

    def test_old_capture_cross_actor_not_correlated(self):
        rows=self.flow(status=500,stored={'title':'new','owner_id':1})
        for i,r in enumerate(rows):r.pop('epoch');r['t_utc']=f'2026-11-02T00:00:0{i}Z'
        rows[-1]['actor']='other';self.rows(rows);_,out=self.invoke('old-cross-actor')
        self.assertFalse(any(v['reason'].startswith('OBSERVED_FAILED') for v in self.verdicts(out)))


class FrozenLibraryEvidence(unittest.TestCase):
    def test_frozen_raw_witnesses_and_controls(self):
        import hashlib
        home=Path(__file__).parent/'fixtures/step2'
        manifest=json.loads((home/'manifest.json').read_text())
        cb=(home/'contract.json').read_bytes()
        self.assertEqual(hashlib.sha256(cb).hexdigest(),manifest['contract_sha256'])
        context=derive(json.loads(cb),manifest['contract_sha256'])
        for case in manifest['cases']:
            with self.subTest(file=case['file']):
                path=home/case['file'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),case['sha256'])
                out=io.StringIO();a=analyze(exchanges(path,'http-jsonl',case['sha256'],{}),context,out,capture=case['capture'])
                violations=[v for v in map(json.loads,out.getvalue().splitlines()) if v['property']!='S7' and v['value']=='violation']
                if case['expected_reason']:
                    self.assertIn(case['expected_reason'],[v['reason'] for v in violations])
                else:self.assertEqual(violations,[])

if __name__=='__main__':unittest.main()
