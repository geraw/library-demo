import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_contract_track as f
from common import loads, read, write


class StateTests(unittest.TestCase):
    setUp = f.ContractTrackTests.setUp
    refreeze = f.ContractTrackTests.refreeze
    rows = f.ContractTrackTests.rows
    invoke = f.ContractTrackTests.invoke
    verdicts = f.ContractTrackTests.verdicts

    def prepare(self):
        self.req['evidence']['capture'] = {'complete': True, 'exclusive': True, 'ordering': 'serial'}

    def row(self, method='GET', status=200, input=None, response=None, **kw):
        row = {'method': method, 'path': '/api/v1/items/7', 'status': status, 'actor': 'capture-principal-A', 'epoch': 0}
        if input is not None:
            row['input'] = input
        if response is not None:
            row['response'] = response
        row.update(kw)
        return row

    def flow(self, status=200, stored=None, **write_args):
        return [self.row(response={'id': 7, 'title': 'old', 'owner_id': 1}),
                self.row('PATCH', status, input={'title': 'new', 'owner_id': 2}, **write_args),
                self.row(response=stored if stored is not None else {'id': 7, 'title': 'new', 'owner_id': 2})]

    def semantic(self, rows, prop, name='out'):
        self.prepare()
        self.rows(rows)
        r, out = self.invoke(name)
        self.assertEqual(r['exit_code'], 0, loads(read(out / 'diagnostics.json')))
        return [v for v in self.verdicts(out) if v['property'] == prop], out

    def test_structural_binding_uses_contract_route_not_id_name_guess(self):
        ctx = loads(read(self.knowledge))
        b = ctx['write_read_bindings']['PATCH /items/{id}']
        self.assertEqual(b['identity_basis'], 'same_concrete_item_uri_not_inferred_id_field')
        self.assertEqual(sorted(b['fields']), ['owner_id', 'title'])
        self.assertEqual(b['excluded_fields']['id'], 'SERVER_MANAGED_OR_WRITE_ONLY')

    def test_readback_correct_control(self):
        verdicts, _ = self.semantic(self.flow(), 'S1')
        self.assertEqual([v['value'] for v in verdicts], ['consistent'])

    def test_readback_silent_change_found_independently(self):
        verdicts, _ = self.semantic(self.flow(stored={'title': 'changed', 'owner_id': 2}), 'S1')
        self.assertEqual(verdicts[0]['value'], 'violation')
        self.assertEqual(verdicts[0]['details']['changes'], {'title': 'changed'})
        self.assertEqual(len(verdicts[0]['evidence']), 3)

    def test_required_read_field_dropped_is_candidate(self):
        verdicts, _ = self.semantic(self.flow(stored={'owner_id': 2}), 'S1')
        self.assertEqual(verdicts[0]['details']['changes']['title'], 'dropped_required_field')

    def test_optional_read_field_missing_is_policy_not_bug(self):
        verdicts, _ = self.semantic(self.flow(stored={'title': 'new'}), 'S1')
        self.assertEqual(verdicts[0]['value'], 'policy_observation')
        self.assertEqual(verdicts[0]['reason'], 'OPTIONAL_READ_FIELD_NOT_RETURNED')

    def test_server_managed_field_ignored(self):
        rows = self.flow()
        rows[1]['input']['id'] = 999
        verdicts, _ = self.semantic(rows, 'S1')
        self.assertEqual(verdicts[0]['value'], 'consistent')
        self.assertNotIn('id', verdicts[0]['fields'])

    def test_writeonly_field_not_compared(self):
        self.doc['components']['schemas']['Item']['properties']['title']['writeOnly'] = True
        self.refreeze()
        verdicts, _ = self.semantic(self.flow(stored={'title': 'hidden', 'owner_id': 2}), 'S1')
        self.assertEqual(verdicts[0]['value'], 'consistent')
        self.assertNotIn('title', verdicts[0]['fields'])

    def test_numeric_equivalence(self):
        verdicts, _ = self.semantic(self.flow(stored={'title': 'new', 'owner_id': 2.0}), 'S1')
        self.assertEqual(verdicts[0]['value'], 'consistent')

    def test_boolean_is_not_number(self):
        verdicts, _ = self.semantic(self.flow(stored={'title': 'new', 'owner_id': True}), 'S1')
        self.assertEqual(verdicts[0]['value'], 'violation')

    def test_datetime_equivalence(self):
        self.doc['components']['schemas']['Item']['properties']['title']['format'] = 'date-time'
        self.refreeze()
        rows = self.flow(stored={'title': '2026-10-31T12:00:00Z', 'owner_id': 2})
        rows[1]['input']['title'] = '2026-10-31T14:00:00+02:00'
        verdicts, _ = self.semantic(rows, 'S1')
        self.assertEqual(verdicts[0]['value'], 'consistent')

    def test_missing_capture_actor_epoch_and_isolation_abstain(self):
        for i, missing in enumerate(('capture', 'actor', 'epoch', 'exclusive')):
            self.prepare()
            rows = self.flow()
            if missing == 'capture':
                self.req['evidence'].pop('capture')
            elif missing == 'exclusive':
                self.req['evidence']['capture']['exclusive'] = False
            else:
                for row in rows:
                    row.pop(missing)
            self.rows(rows)
            _, out = self.invoke(str(i))
            v = [v for v in self.verdicts(out) if v['property'] == 'S1']
            self.assertTrue(v)
            self.assertTrue(all(x['value'] == 'not_evaluable' for x in v))

    def test_different_actor_case_origin_or_id_cannot_supply_readback(self):
        for i, extra in enumerate(({'actor': 'B'}, {'case_id': 'other'}, {'path': '/api/v1/items/8'},
                                   {'path': 'https://other.invalid/api/v1/items/7'})):
            rows = self.flow(stored={'title': 'wrong', 'owner_id': 99})
            rows[-1].update(extra)
            verdicts, _ = self.semantic(rows, 'S1', str(i))
            self.assertEqual(verdicts[0]['value'], 'not_evaluable')

    def test_reset_epoch_change_invalidates_prefix(self):
        rows = self.flow(stored={'title': 'wrong', 'owner_id': 99})
        rows[-1]['epoch'] = 1
        verdicts, _ = self.semantic(rows, 'S1')
        self.assertEqual(verdicts[0]['reason'], 'RESET_EPOCH_CHANGED')

    def test_intervening_mutation_invalidates_even_other_resource(self):
        rows = self.flow(stored={'title': 'wrong', 'owner_id': 99})
        rows.insert(2, self.row('POST', 201, path='/api/v1/items', input={'title': 'another'}))
        verdicts, _ = self.semantic(rows, 'S1')
        self.assertEqual(verdicts[0]['reason'], 'INTERVENING_MUTATION')

    def test_readback_failure_and_missing_body_abstain(self):
        for i, changes in enumerate(({'status': 404}, {'response': None}, {'path': '/api/v1/items/7?fields=id'})):
            rows = self.flow()
            rows[-1].update(changes)
            verdicts, _ = self.semantic(rows, 'S1', str(i))
            self.assertEqual(verdicts[0]['value'], 'not_evaluable')

    def test_async_success_not_treated_as_synchronous(self):
        verdicts, _ = self.semantic(self.flow(status=202), 'S1')
        self.assertEqual(verdicts[0]['reason'], 'ASYNCHRONOUS_WRITE_NOT_INTERPRETED')

    def test_intervals_override_false_serial_declaration(self):
        self.prepare()
        rows = self.flow()
        for i, row in enumerate(rows):
            row.update(started_utc='2026-10-31T12:00:00Z', ended_utc='2026-10-31T12:00:01Z')
        self.rows(rows)
        _, out = self.invoke()
        v = next(v for v in self.verdicts(out) if v['property'] == 'S1')
        self.assertEqual(v['value'], 'not_evaluable')
        self.assertEqual(v['reason'], 'CAPTURE_INTERVALS_OVERLAP_OR_ARE_OUT_OF_ORDER')

    def test_failure_rollback_control(self):
        verdicts, _ = self.semantic(self.flow(500, {'title': 'old', 'owner_id': 1}), 'S5')
        self.assertEqual(verdicts[0]['value'], 'consistent')
        self.assertEqual(verdicts[0]['details']['outcome'], 'unchanged')

    def test_partial_commit_is_observation_without_atomicity_promise(self):
        verdicts, _ = self.semantic(self.flow(500, {'title': 'new', 'owner_id': 1}), 'S5')
        self.assertEqual(verdicts[0]['value'], 'policy_observation')
        self.assertEqual(verdicts[0]['details']['outcome'], 'partial')
        self.assertEqual(verdicts[0]['details']['field_states'], {'title': 'applied', 'owner_id': 'kept'})
        self.assertFalse(verdicts[0]['details']['full_resource_atomicity_proven'])

    def test_commit_despite_422_and_500_is_observed(self):
        for status in (422, 500):
            verdicts, _ = self.semantic(self.flow(status), 'S5', str(status))
            self.assertEqual(verdicts[0]['details']['outcome'], 'committed_despite_error')
            self.assertEqual(verdicts[0]['value'], 'policy_observation')

    def test_failure_missing_preimage_not_guessed(self):
        verdicts, _ = self.semantic(self.flow(500)[1:], 'S5')
        self.assertEqual(verdicts[0]['reason'], 'PREIMAGE_NOT_RETAINED')

    def test_failed_read_invalidates_old_preimage(self):
        rows = self.flow(500)
        rows.insert(1, self.row(status=404))
        verdicts, _ = self.semantic(rows, 'S5')
        self.assertEqual(verdicts[0]['reason'], 'PREIMAGE_NOT_RETAINED')

    def test_only_observable_requested_changes_count_for_atomicity(self):
        rows = self.flow(500)
        rows[1]['input'] = {'title': 'old', 'owner_id': 1}
        verdicts, _ = self.semantic(rows, 'S5')
        self.assertEqual(verdicts[0]['reason'], 'NO_OBSERVABLE_REQUESTED_CHANGE')

    def test_large_body_abstains_without_discarding_status_checks(self):
        with patch('state_semantics.MAX_STATE_BODY_BYTES', 5):
            verdicts, out = self.semantic(self.flow(), 'S1')
        self.assertEqual(verdicts[0]['value'], 'not_evaluable')
        self.assertEqual(loads(read(out / 'coverage.json'))['classes']['S7']['opportunities'], 3)

    def test_schema_max_length_rejection_and_invalid_storage(self):
        rows = self.flow(stored={'title': 'x' * 41, 'owner_id': 2})
        rows[1]['input']['title'] = 'x' * 41
        verdicts, _ = self.semantic(rows, 'S3')
        self.assertEqual(verdicts[0]['value'], 'violation')
        self.assertEqual(verdicts[0]['details']['stored_invalid']['title'], ['maxLength'])
        rows = self.flow(422, {'title': 'old', 'owner_id': 1})
        rows[1]['input']['title'] = 'x' * 41
        verdicts, _ = self.semantic(rows, 'S3', 'reject')
        self.assertEqual(verdicts[0]['reason'], 'INVALID_INPUT_REJECTED')

    def test_invalid_input_accepted_without_readback_is_not_stored_claim(self):
        rows = self.flow()[:2]
        rows[1]['input']['title'] = 'x' * 41
        verdicts, _ = self.semantic(rows, 'S3')
        self.assertEqual(verdicts[0]['value'], 'policy_observation')
        self.assertEqual(verdicts[0]['reason'], 'INVALID_INPUT_ACCEPTED_STORAGE_UNVERIFIED')

    def test_invalid_input_normalized_into_valid_storage_not_violation(self):
        rows = self.flow(stored={'title': 'short', 'owner_id': 2})
        rows[1]['input']['title'] = 'x' * 41
        verdicts, _ = self.semantic(rows, 'S3')
        self.assertEqual(verdicts[0]['value'], 'policy_observation')

    def test_error_body_not_treated_as_stored_resource(self):
        rows = self.flow(stored={'title': 'x' * 41, 'owner_id': 2})
        rows[1]['input']['title'] = 'x' * 41
        rows[-1]['status'] = 500
        verdicts, _ = self.semantic(rows, 'S3')
        self.assertEqual(verdicts[0]['value'], 'policy_observation')

    def test_state_rules_are_invariant_under_four_tool_labels(self):
        self.prepare()
        self.rows(self.flow(500, {'title': 'new', 'owner_id': 1}))
        answers = []
        for tool in ('provengo', 'restler', 'evomaster', 'schemathesis'):
            self.req['run']['tool'] = tool
            _, out = self.invoke(tool)
            answers.append((out / 'verdicts.jsonl').read_bytes())
        self.assertTrue(all(a == answers[0] for a in answers))

    def test_false_producer_pass_does_not_hide_partial_commit(self):
        rows = self.flow(500, {'title': 'new', 'owner_id': 1})
        for row in rows:
            row.update(verdict='pass', logical_id='known-bug', facts={'rolled_back': True})
        verdicts, _ = self.semantic(rows, 'S5')
        self.assertEqual(verdicts[0]['details']['outcome'], 'partial')

    def test_state_outputs_do_not_emit_raw_values_or_actor(self):
        rows = self.flow(stored={'title': 'PRIVATE_AFTER', 'owner_id': 2})
        rows[1]['input']['title'] = 'PRIVATE_BEFORE'
        _, out = self.semantic(rows, 'S1')
        text = '\n'.join(p.read_text() for p in out.iterdir())
        for raw in ('PRIVATE_BEFORE', 'PRIVATE_AFTER', 'capture-principal-A'):
            self.assertNotIn(raw, text)

    def test_observer_transport_excludes_oracle_and_verdict_rows(self):
        self.prepare()
        self.req['evidence']['format'] = 'observer-tool-jsonl'
        self.rows([{'role': 'startup', 'bugs': [1, 2]},
                   {'role': 'tool', 'method': 'GET', 'path': '/api/v1/items/7', 'status': 200, 'request': None, 'response': {'title': 'ok'}},
                   {'role': 'oracle', 'method': 'GET', 'path': '/api/v1/items/7', 'status': 500},
                   {'role': 'verdict', 'method': 'PATCH', 'path': '/api/v1/items/7', 'status': 500, 'facts': {'bug': True}}])
        r, out = self.invoke()
        self.assertEqual(r['exchanges'], 1)
        self.assertEqual(loads(read(out / 'coverage.json'))['server_5xx'], 0)
        self.assertEqual(loads(read(out / 'coverage.json'))['ingestion']['ignored_non_http'], 3)

    def test_constraint_type_enum_numeric_and_required_cases(self):
        from state_semantics import scalar_valid
        def schema(**constraints):
            return {'status': 'declared', 'constraints': constraints}
        for value, spec, expected in ((True, schema(type='integer'), ['type']),
                                      (1.0, schema(type='integer'), []),
                                      (2, schema(type='integer', enum=[1]), ['enum']),
                                      (0, schema(type='number', minimum=1), ['minimum']),
                                      (3, schema(type='number', maximum=2), ['maximum']),
                                      (2, schema(type='number', exclusiveMinimum=2), ['exclusiveMinimum']),
                                      ('', schema(type='string', minLength=1), ['minLength'])):
            with self.subTest(value=value, spec=spec):
                self.assertEqual(scalar_valid(value, spec), expected)
        rows = self.flow(422, {'title': 'old', 'owner_id': 1})
        rows[1]['input'].pop('title')
        verdicts, _ = self.semantic(rows, 'S3')
        self.assertEqual(verdicts[0]['details']['invalid']['title'], ['required'])
        self.assertIn('#/components/schemas/Item/properties/title', [k['pointer'] for k in verdicts[0]['knowledge']])

    def test_reset_epoch_reuse_does_not_reuse_old_preimage(self):
        rows = self.flow(500)
        rows.insert(1, self.row(epoch=1, response={'title': 'other_epoch', 'owner_id': 99}))
        verdicts, _ = self.semantic(rows, 'S5')
        self.assertEqual(verdicts[0]['reason'], 'PREIMAGE_NOT_RETAINED')

    def test_bounded_snapshot_cache_eviction_is_explicit(self):
        rows = self.flow(500)
        rows.insert(1, self.row(path='/api/v1/items/8', response={'title': 'another', 'owner_id': 1}))
        with patch('state_semantics.MAX_SNAPSHOTS', 1):
            verdicts, out = self.semantic(rows, 'S5')
        self.assertEqual(verdicts[0]['reason'], 'PREIMAGE_NOT_RETAINED')
        self.assertEqual(loads(read(out / 'coverage.json'))['state_audit']['snapshot_evictions'], 1)

    def test_har_bodies_and_identity_feed_same_state_judge(self):
        self.prepare()
        self.req['evidence']['format'] = 'har'
        entries = []
        for row in self.flow(500, {'title': 'new', 'owner_id': 1}):
            req = {'method': row['method'], 'url': row['path'], 'headers': []}
            if 'input' in row:
                req['postData'] = {'mimeType': 'application/json', 'text': json.dumps(row['input'])}
            entries.append({'request': req, 'response': {'status': row['status'],
                            'content': {'mimeType': 'application/json', 'text': json.dumps(row.get('response'))}},
                            '_actor': row['actor'], '_epoch': row['epoch']})
        write(self.traffic, {'log': {'version': '1.2', 'entries': entries}})
        r, out = self.invoke()
        self.assertEqual(r['exit_code'], 0)
        verdict = next(v for v in self.verdicts(out) if v['property'] == 'S5')
        self.assertEqual(verdict['details']['outcome'], 'partial')
        self.assertTrue(all('locator' in s for s in verdict['evidence']))

    def test_31_type_unions_abstain_instead_of_engine_error(self):
        self.doc['openapi'] = '3.1.0'
        self.doc['components']['schemas']['Item']['properties']['title']['type'] = ['string', 'null']
        self.refreeze()
        verdicts, _ = self.semantic(self.flow(), 'S3')
        self.assertEqual(verdicts[0]['value'], 'consistent')
        self.assertIn('title', verdicts[0]['details']['unsupported_fields'])
        self.assertNotIn('title', verdicts[0]['details']['checked_fields'])

    def test_nullable_does_not_override_enum(self):
        from state_semantics import scalar_valid
        schema = {'status': 'declared', 'constraints': {'type': 'string', 'nullable': True, 'enum': ['a']}}
        self.assertEqual(scalar_valid(None, schema), ['enum'])
        schema['constraints']['enum'].append(None)
        self.assertEqual(scalar_valid(None, schema), [])


if __name__ == '__main__':
    unittest.main()
