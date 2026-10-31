"""Generic regressions prompted by the 2026-11-01 producer handoff."""
import copy
import unittest

import test_contract_track as f
import test_state_semantics as s
from common import InputError, loads, read
from contract_context import derive


class ReviewTests(unittest.TestCase):
    setUp = f.ContractTrackTests.setUp
    refreeze = f.ContractTrackTests.refreeze
    rows = f.ContractTrackTests.rows
    invoke = f.ContractTrackTests.invoke
    verdicts = f.ContractTrackTests.verdicts
    prepare = s.StateTests.prepare
    row = s.StateTests.row
    flow = s.StateTests.flow

    def test_swagger_parameter_required_boolean_is_not_schema_required(self):
        self.doc = {'swagger': '2.0', 'paths': {'/items/{id}': {
            'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'type': 'integer'}],
            'get': {'parameters': [{'name': 'q', 'in': 'query', 'required': False, 'type': 'string'}],
                    'responses': {'200': {'description': 'ok'}}}}}}
        self.refreeze()
        op = loads(read(self.knowledge))['operations'][0]
        self.assertEqual(op['parameters'][0]['required'], True)
        self.assertEqual(op['parameters'][0]['schema']['constraints']['type'], 'integer')
        self.assertNotIn('required', op['parameters'][0]['schema'])

    def test_boolean_required_on_actual_object_schema_still_invalid(self):
        self.doc['components']['schemas']['Item']['required'] = True
        with self.assertRaises(InputError):
            self.refreeze()

    def test_trailing_slash_binding_and_real_matching_preserve_slash(self):
        item = self.doc['paths'].pop('/items/{id}')
        self.doc['paths']['/items/{id}/'] = item
        self.refreeze()
        b = loads(read(self.knowledge))['write_read_bindings']['PATCH /items/{id}/']
        self.assertEqual(b['status'], 'structural_candidate')
        self.prepare()
        rows = self.flow()
        for row in rows:
            row['path'] += '/'
        self.rows(rows)
        _, out = self.invoke()
        self.assertEqual(next(v for v in self.verdicts(out) if v['property'] == 'S1')['value'], 'consistent')

    def test_binding_diagnostics_explain_missing_get_and_composition(self):
        del self.doc['paths']['/items/{id}']['get']
        self.refreeze()
        b = loads(read(self.knowledge))['write_read_bindings']['PATCH /items/{id}']
        self.assertIn('SAME_ROUTE_GET_MISSING', b['diagnostics']['unavailable_reasons'])
        self.doc = f.fixture()
        self.doc['components']['schemas']['Item']['allOf'] = [{'type': 'object'}]
        self.refreeze()
        b = loads(read(self.knowledge))['write_read_bindings']['PATCH /items/{id}']
        self.assertIn('REQUEST_SCHEMA_UNKNOWN_OR_COMPOSED', b['diagnostics']['unavailable_reasons'])

    def test_differently_named_patched_request_schema_can_bind(self):
        self.doc['components']['schemas']['PatchedItem'] = copy.deepcopy(self.doc['components']['schemas']['Item'])
        self.doc['paths']['/items/{id}']['patch']['requestBody']['content']['application/json']['schema']['$ref'] = '#/components/schemas/PatchedItem'
        self.refreeze()
        self.assertEqual(loads(read(self.knowledge))['write_read_bindings']['PATCH /items/{id}']['usable_scalar_fields'], 2)

    def test_no_shared_scalar_fields_has_an_explicit_reason(self):
        self.doc['paths']['/items/{id}']['patch']['requestBody']['content']['application/json']['schema'] = {
            'type': 'object', 'properties': {'different': {'type': 'string'}}}
        self.refreeze()
        b = loads(read(self.knowledge))['write_read_bindings']['PATCH /items/{id}']
        self.assertEqual(b['usable_scalar_fields'], 0)
        self.assertIn('NO_SUPPORTED_COMMON_SCALAR_FIELDS', b['diagnostics']['unavailable_reasons'])

    def test_null_response_schema_is_explicit_unknown(self):
        self.doc['paths']['/items/{id}']['get']['responses']['200']['content']['application/json']['schema'] = None
        self.refreeze()
        c = loads(read(self.knowledge))
        self.assertTrue(any(g['code'] == 'NULL_SCHEMA_UNINTERPRETABLE' for g in c['gaps']))
        self.assertEqual(c['write_read_bindings']['PATCH /items/{id}']['status'], 'unknown')

    def test_empty_schema_array_is_unknown_not_an_invented_array_type(self):
        self.doc['paths']['/items/{id}']['get']['responses']['200']['content']['application/json']['schema'] = []
        self.refreeze()
        c = loads(read(self.knowledge))
        self.assertTrue(any(g['code'] == 'EMPTY_ARRAY_SCHEMA_UNINTERPRETABLE' for g in c['gaps']))
        self.assertEqual(c['write_read_bindings']['PATCH /items/{id}']['status'], 'unknown')

    def test_nested_fanout_is_bounded_without_losing_top_level_scalar(self):
        node = {'type': 'object', 'properties': {'leaf': {'type': 'string'}}}
        for depth in range(7):
            node = {'type': 'object', 'properties': {'a': node, 'b': copy.deepcopy(node)}}
        self.doc['components']['schemas']['Item']['properties']['nested'] = node
        self.refreeze()
        c = loads(read(self.knowledge))
        self.assertLess(len(read(self.knowledge)), 50_000)
        self.assertTrue(any(g['code'] == 'NESTED_SCHEMA_SCOPE_LIMIT' for g in c['gaps']))
        self.assertIn('title', c['write_read_bindings']['PATCH /items/{id}']['fields'])

    def test_server_errors_and_undeclared_statuses_are_separate_no_duplicate_groups(self):
        self.rows([f.record(500), f.record(500), f.record(401), f.record(404)])
        _, out = self.invoke()
        data = loads(read(out / 'findings.json'))
        ids = [g['id'] for g in data['groups']]
        partitions = data['group_partitions']
        self.assertEqual(len(data['groups']), 2)
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(len(partitions['server_5xx']), 1)
        self.assertEqual(len(partitions['undeclared_status']), 1)
        flat = [g for values in partitions.values() for g in values]
        self.assertEqual(sorted(flat), sorted(ids))
        self.assertIn('Separate finding streams', (out / 'report.md').read_text())

    def test_start_only_history_is_accepted_as_declared_not_verified_serial(self):
        self.prepare()
        rows = self.flow()
        for i, row in enumerate(rows):
            row['started_utc'] = '2026-11-01T12:00:0' + str(i) + 'Z'
        self.rows(rows)
        _, out = self.invoke()
        self.assertEqual(next(v for v in self.verdicts(out) if v['property'] == 'S1')['value'], 'consistent')
        p = loads(read(out / 'provenance.json'))
        self.assertEqual(p['http_intervals_retained'], 0)
        self.assertEqual(p['timing_evidence']['start_only'], 3)

    def test_observation_only_journal_time_is_not_a_request_interval(self):
        self.prepare()
        rows = self.flow()
        for i, row in enumerate(rows):
            row['observed_utc'] = '2026-11-01T12:00:0' + str(i) + 'Z'
        self.rows(rows)
        _, out = self.invoke()
        self.assertEqual(next(v for v in self.verdicts(out) if v['property'] == 'S1')['value'], 'consistent')
        self.assertEqual(loads(read(out / 'provenance.json'))['timing_evidence']['observation_only'], 3)

    def test_start_only_reversed_order_cannot_prove_serial_prefix(self):
        self.prepare()
        rows = self.flow()
        for i, row in enumerate(rows):
            row['started_utc'] = '2026-11-01T12:00:0' + str(2 - i) + 'Z'
        self.rows(rows)
        _, out = self.invoke()
        self.assertEqual(next(v for v in self.verdicts(out) if v['property'] == 'S1')['value'], 'not_evaluable')


if __name__ == '__main__':
    unittest.main()
