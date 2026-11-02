import copy
import json
import unittest
from unittest.mock import patch

import test_state_semantics as s
from common import loads, read, write


class PathTests(unittest.TestCase):
    setUp = s.StateTests.setUp
    refreeze = s.StateTests.refreeze
    rows = s.StateTests.rows
    invoke = s.StateTests.invoke
    verdicts = s.StateTests.verdicts
    prepare = s.StateTests.prepare
    row = s.StateTests.row

    def configured(self):
        self.doc['paths']['/items']['post']['requestBody'] = {
            'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Item'}}}}
        self.refreeze()
        self.prepare()

    def flow(self, create_status=201, update_status=200, created='probe', updated='probe', location=True):
        create = self.row('POST', create_status, input={'title': 'probe', 'owner_id': 1},
                          path='/api/v1/items', response={'id': 7, 'title': created})
        if location:
            create['response_headers'] = {'Location': '/api/v1/items/7'}
        return [create, self.row(response={'id': 7, 'title': created, 'owner_id': 1}),
                self.row('PATCH', update_status, input={'title': 'probe'}),
                self.row(response={'id': 7, 'title': updated, 'owner_id': 1})]

    def check(self, rows, name='out'):
        self.rows(rows)
        result, out = self.invoke(name)
        self.assertEqual(result['exit_code'], 0, loads(read(out / 'diagnostics.json')))
        vs = [v for v in self.verdicts(out) if v['property'] == 'S2' and v['field'] == 'title']
        return vs, out

    def test_contract_pair_and_exact_scalar_assertions(self):
        self.configured()
        pair = loads(read(self.knowledge))['create_update_bindings']['PATCH /items/{id}']['pairs'][0]
        self.assertEqual(pair['create_operation'], 'POST /items')
        self.assertEqual(sorted(pair['fields']), ['owner_id', 'title'])
        self.assertEqual(pair['excluded_fields']['id'], 'SERVER_MANAGED_OR_WRITE_ONLY')

    def test_control_same_value_same_storage(self):
        self.configured()
        vs, _ = self.check(self.flow())
        self.assertEqual(vs[0]['value'], 'consistent')
        self.assertEqual(vs[0]['reason'], 'S2_CREATE_UPDATE_READBACK_MATCH')

    def test_independent_controlled_storage_divergence_candidate(self):
        self.configured()
        vs, _ = self.check(self.flow(created='create-normalized', updated='update-normalized'))
        self.assertEqual(vs[0]['value'], 'violation')
        self.assertTrue(vs[0]['details']['controlled_scalar_comparison'])
        self.assertEqual(len(vs[0]['evidence']), 4)
        self.assertEqual(vs[0]['details']['identity_basis'], 'recorded_201_location')
        self.assertFalse(vs[0]['details']['field_causality_proven'])

    def test_create_accepts_update_rejects_is_policy_observation(self):
        self.configured()
        vs, _ = self.check(self.flow(update_status=422))
        self.assertEqual(vs[0]['value'], 'policy_observation')
        self.assertEqual(vs[0]['details']['create_class'], 'accepted')
        self.assertEqual(vs[0]['details']['update_class'], 'validation_rejected')

    def test_create_rejects_update_accepts_is_policy_observation(self):
        self.configured()
        vs, _ = self.check(self.flow(create_status=422, location=False))
        self.assertEqual(vs[0]['value'], 'policy_observation')
        self.assertEqual(vs[0]['details']['create_status'], 422)
        self.assertEqual(vs[0]['details']['update_status'], 200)

    def test_update_5xx_is_path_observation_plus_separate_s7(self):
        self.configured()
        vs, out = self.check(self.flow(update_status=500))
        self.assertEqual(vs[0]['value'], 'policy_observation')
        self.assertEqual(vs[0]['details']['update_class'], 'server_error')
        self.assertEqual(loads(read(out / 'coverage.json'))['server_5xx'], 1)

    def test_equal_rejection_classes_not_claimed_success(self):
        self.configured()
        vs, _ = self.check(self.flow(create_status=400, update_status=422))
        self.assertEqual(vs[0]['value'], 'consistent')
        self.assertEqual(vs[0]['reason'], 'S2_SAME_RESPONSE_CLASS_ONLY')

    def test_401_403_404_409_429_and_202_not_equivalent_validation(self):
        self.configured()
        for code in (401, 403, 404, 409, 429, 202):
            vs, _ = self.check(self.flow(create_status=code), str(code))
            self.assertEqual(vs[0]['value'], 'not_evaluable')
            self.assertEqual(vs[0]['reason'], 'S2_RESPONSE_CLASS_NOT_COMPARABLE')

    def test_no_identifier_name_guess_without_location_or_link(self):
        self.configured()
        vs, _ = self.check(self.flow(created='a', updated='b', location=False))
        self.assertEqual(vs[0]['value'], 'not_evaluable')
        self.assertEqual(vs[0]['reason'], 'S2_CREATE_OR_UPDATE_READBACK_NOT_COMPARABLE')

    def test_public_operation_link_uses_arbitrary_response_field(self):
        self.configured()
        self.doc['paths']['/items']['post']['responses']['201']['links'] = {
            'created': {'operationId': 'getItem', 'parameters': {'id': '$response.body#/publicKey'}}}
        self.refreeze()
        rows = self.flow(created='a', updated='b', location=False)
        rows[0]['response'] = {'publicKey': 7}
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['value'], 'violation')
        self.assertEqual(vs[0]['details']['identity_basis'], 'explicit_public_operation_link')

    def test_conflicting_location_and_link_cannot_identify_create(self):
        self.configured()
        self.doc['paths']['/items']['post']['responses']['201']['links'] = {
            'created': {'operationId': 'getItem', 'parameters': {'id': '$response.body#/other'}}}
        self.refreeze()
        rows = self.flow(created='a', updated='b')
        rows[0]['response']['other'] = 8
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['value'], 'not_evaluable')

    def test_no_update_preimage_abstains(self):
        self.configured()
        rows = self.flow(create_status=422)
        del rows[1]
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['reason'], 'S2_UPDATE_RESOURCE_PREIMAGE_NOT_ESTABLISHED')

    def test_missing_update_readback_abstains(self):
        self.configured()
        vs, _ = self.check(self.flow()[:-1])
        self.assertEqual(vs[0]['reason'], 'S2_READBACK_NOT_RETAINED_IN_SAME_SCOPE')

    def test_duplicate_matching_creations_are_ambiguous(self):
        self.configured()
        rows = self.flow(create_status=422)
        rows.insert(1, copy.deepcopy(rows[0]))
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['reason'], 'S2_AMBIGUOUS_CREATE_MATCH')

    def test_confirmed_same_resource_disambiguates_without_ignoring_intervening_mutation(self):
        self.configured()
        rows = self.flow(created='a', updated='b')
        another = copy.deepcopy(rows[0])
        another['response_headers']['Location'] = '/api/v1/items/8'
        rows.insert(2, another)
        rows.insert(3, self.row(response={'id': 7, 'title': 'a', 'owner_id': 1}))
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['value'], 'policy_observation')
        self.assertFalse(vs[0]['details']['controlled_scalar_comparison'])

    def test_declared_constraint_difference_prevents_pairing(self):
        self.configured()
        schema = copy.deepcopy(self.doc['components']['schemas']['Item'])
        schema['properties']['title']['maxLength'] = 10
        self.doc['paths']['/items']['post']['requestBody']['content']['application/json']['schema'] = schema
        self.refreeze()
        rows = self.flow()
        vs, out = self.check(rows)
        self.assertEqual(vs, [])
        pair = loads(read(self.knowledge))['create_update_bindings']['PATCH /items/{id}']['pairs'][0]
        self.assertEqual(pair['excluded_fields']['title'], 'DECLARED_FIELD_ASSERTIONS_DIFFER')
        self.assertTrue(any(v['property'] == 'S2' and v['value'] == 'not_evaluable' for v in self.verdicts(out)))

    def test_unimplemented_assertion_difference_is_not_discarded(self):
        self.configured()
        create_schema = copy.deepcopy(self.doc['components']['schemas']['Item'])
        create_schema['properties']['owner_id']['multipleOf'] = 2
        self.doc['paths']['/items']['post']['requestBody']['content']['application/json']['schema'] = create_schema
        self.refreeze()
        pair = loads(read(self.knowledge))['create_update_bindings']['PATCH /items/{id}']['pairs'][0]
        self.assertNotIn('owner_id', pair['fields'])

    def test_annotations_do_not_create_false_constraint_difference(self):
        self.configured()
        schema = copy.deepcopy(self.doc['components']['schemas']['Item'])
        schema['properties']['title'].update(description='A different description', default='other')
        self.doc['paths']['/items']['post']['requestBody']['content']['application/json']['schema'] = schema
        self.refreeze()
        vs, _ = self.check(self.flow())
        self.assertEqual(vs[0]['value'], 'consistent')

    def test_other_changed_input_downgrades_storage_candidate(self):
        self.configured()
        rows = self.flow(created='a', updated='b')
        rows[2]['input']['owner_id'] = 2
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['value'], 'policy_observation')

    def test_capture_actor_epoch_case_origin_guards(self):
        self.configured()
        for i, extra in enumerate(({'actor': 'other'}, {'epoch': 1}, {'case_id': 'other'},
                                   {'path': 'https://other.invalid/api/v1/items/7'})):
            rows = self.flow(create_status=422)
            rows[1].update(extra)
            rows[2].update(extra)
            rows[3].update(extra)
            vs, _ = self.check(rows, str(i))
            self.assertTrue(vs)
            self.assertTrue(all(v['value'] == 'not_evaluable' for v in vs))

    def test_missing_capture_facts_do_not_evaluate_status_pairs(self):
        self.configured()
        self.req['evidence'].pop('capture')
        _, out = self.check(self.flow(create_status=422))
        all_s2 = [v for v in self.verdicts(out) if v['property'] == 'S2']
        self.assertEqual(len(all_s2), 1)
        self.assertEqual(all_s2[0]['reason'], 'COMPLETE_ISOLATED_SERIAL_CAPTURE_NOT_DECLARED')

    def test_number_comparison_preserves_arbitrary_integer_precision(self):
        from create_update import fingerprint
        self.assertNotEqual(fingerprint(10 ** 40, {}), fingerprint(10 ** 40 + 1, {}))
        self.assertEqual(fingerprint(1, {}), fingerprint(1.0, {}))
        self.assertNotEqual(fingerprint(True, {}), fingerprint(1, {}))

    def test_public_pointer_does_not_guess_negative_or_padded_array_index(self):
        from create_update import pointer
        value = {'items': [{'key': 7}]}
        self.assertEqual(pointer(value, '$response.body#/items/0/key'), 7)
        self.assertIsNone(pointer(value, '$response.body#/items/-1/key'))
        self.assertIsNone(pointer(value, '$response.body#/items/00/key'))

    def test_link_server_override_does_not_prove_local_resource_identity(self):
        self.configured()
        self.doc['paths']['/items']['post']['responses']['201']['links'] = {
            'created': {'operationId': 'getItem', 'parameters': {'id': '$response.body#/id'},
                        'server': {'url': 'https://another.invalid'}}}
        self.refreeze()
        vs, _ = self.check(self.flow(created='a', updated='b', location=False))
        self.assertEqual(vs[0]['value'], 'not_evaluable')

    def test_different_parent_collection_cannot_supply_match(self):
        self.configured()
        self.doc['paths']['/groups/{group}/items'] = self.doc['paths'].pop('/items')
        self.doc['paths']['/groups/{group}/items/{id}'] = self.doc['paths'].pop('/items/{id}')
        self.refreeze()
        rows = self.flow(create_status=422)
        rows[0]['path'] = '/api/v1/groups/1/items'
        for row in rows[1:]:
            row['path'] = '/api/v1/groups/2/items/7'
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['reason'], 'S2_MATCHING_CREATE_NOT_RETAINED')

    def test_empty_get_body_does_not_establish_update_resource(self):
        self.configured()
        rows = self.flow(create_status=422)
        rows[1]['response'] = {}
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['reason'], 'S2_UPDATE_RESOURCE_PREIMAGE_NOT_ESTABLISHED')

    def test_absolute_same_origin_location_is_accepted(self):
        self.configured()
        rows = self.flow()
        for row in rows:
            row['path'] = 'http://fixture.invalid' + row['path']
        rows[0]['response_headers']['Location'] = 'http://fixture.invalid/api/v1/items/7'
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['value'], 'consistent')

    def test_budget_truncation_is_cleared_only_by_new_epoch(self):
        self.configured()
        old = self.flow(create_status=422)
        old.insert(1, copy.deepcopy(old[0]))
        new = self.flow()
        for row in new:
            row['epoch'] = 1
        with patch('create_update.MAX_ARMS', 1):
            vs, out = self.check(old + new)
        all_s2 = [v for v in self.verdicts(out) if v['property'] == 'S2']
        self.assertEqual(all_s2[0]['reason'], 'S2_HISTORY_BUDGET_EXCEEDED')
        self.assertEqual(vs[-1]['value'], 'consistent')

    def test_har_headers_and_bodies_preserve_s2_identity(self):
        self.configured()
        self.req['evidence']['format'] = 'har'
        entries = []
        for row in self.flow(created='a', updated='b'):
            request = {'method': row['method'], 'url': row['path'], 'headers': []}
            if 'input' in row:
                request['postData'] = {'text': json.dumps(row['input']), 'mimeType': 'application/json'}
            response = {'status': row['status'], 'headers': [{'name': k, 'value': v} for k, v in row.get('response_headers', {}).items()],
                        'content': {'mimeType': 'application/json', 'text': json.dumps(row.get('response'))}}
            entries.append({'request': request, 'response': response, '_actor': row['actor'], '_epoch': row['epoch']})
        write(self.traffic, {'log': {'version': '1.2', 'entries': entries}})
        _, out = self.invoke()
        v = next(v for v in self.verdicts(out) if v['property'] == 'S2')
        self.assertEqual(v['value'], 'violation')
        self.assertTrue(all('locator' in src for src in v['evidence']))

    def test_malformed_location_abstains_instead_of_engine_error(self):
        self.configured()
        for i, value in enumerate(('http://[broken', '/api/v1/items/7\n', 'javascript:/api/v1/items/7')):
            rows = self.flow(created='a', updated='b')
            rows[0]['response_headers']['Location'] = value
            vs, _ = self.check(rows, str(i))
            self.assertEqual(vs[0]['value'], 'not_evaluable')

    def test_qualified_public_link_path_parameter(self):
        self.configured()
        self.doc['paths']['/items']['post']['responses']['201']['links'] = {
            'created': {'operationId': 'getItem', 'parameters': {'path.id': '$response.body#/id'}}}
        self.refreeze()
        vs, _ = self.check(self.flow(created='a', updated='b', location=False))
        self.assertEqual(vs[0]['value'], 'violation')

    def test_history_budget_never_silently_reuses_evicted_match(self):
        self.configured()
        rows = self.flow(create_status=422)
        second = copy.deepcopy(rows[0])
        second['input']['title'] = 'different'
        rows.insert(1, second)
        with patch('create_update.MAX_ARMS', 1):
            _, out = self.check(rows)
        vs = [v for v in self.verdicts(out) if v['property'] == 'S2']
        self.assertEqual(vs[0]['reason'], 'S2_HISTORY_BUDGET_EXCEEDED')

    def test_null_value_is_not_assumed_to_mean_same_patch_action(self):
        self.configured()
        rows = self.flow()
        rows[0]['input']['title'] = None
        rows[2]['input']['title'] = None
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['reason'], 'S2_NULL_OR_COMPLEX_VALUE_NOT_INTERPRETED')

    def test_same_judge_four_tool_names_and_no_producer_verdicts(self):
        self.configured()
        rows = self.flow(created='a', updated='b')
        for row in rows:
            row.update(logical_id='bug-trap', verdict='pass', facts={'path_consistency': True})
        self.rows(rows)
        outputs = []
        for tool in ('provengo', 'restler', 'evomaster', 'schemathesis'):
            self.req['run']['tool'] = tool
            _, out = self.invoke(tool)
            outputs.append((out / 'verdicts.jsonl').read_bytes())
        self.assertTrue(all(o == outputs[0] for o in outputs))

    def test_private_payloads_are_not_copied_into_output(self):
        self.configured()
        rows = self.flow(created='PRIVATE_FIRST_VALUE', updated='PRIVATE_SECOND_VALUE')
        rows[0]['input']['title'] = 'PRIVATE_INPUT'
        rows[2]['input']['title'] = 'PRIVATE_INPUT'
        _, out = self.check(rows)
        text = '\n'.join(p.read_text() for p in out.iterdir())
        for value in ('PRIVATE_FIRST_VALUE', 'PRIVATE_SECOND_VALUE', 'PRIVATE_INPUT'):
            self.assertNotIn(value, text)

    def test_public_roles_support_put_create_post_update_without_name_profiles(self):
        self.configured()
        create = self.doc['paths'].pop('/items')['post']
        create['summary'] = 'Create an item'
        self.doc['paths']['/projects/{project}/items'] = {'put': create}
        update = self.doc['paths']['/items/{id}'].pop('patch')
        update['summary'] = 'Update an item'
        self.doc['paths']['/items/{id}']['post'] = update
        self.refreeze()
        rows = self.flow(created='a', updated='b')
        rows[0].update(method='PUT', path='/api/v1/projects/4/items')
        rows[2]['method'] = 'POST'
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['value'], 'violation')
        self.assertEqual(vs[0]['operations'], ['PUT /projects/{project}/items', 'POST /items/{id}'])

    def test_cross_route_parent_without_identity_abstains(self):
        self.configured()
        create = self.doc['paths'].pop('/items')['post']
        create['summary'] = 'Create an item'
        self.doc['paths']['/projects/{project}/items'] = {'put': create}
        update = self.doc['paths']['/items/{id}'].pop('patch')
        update['summary'] = 'Update an item'
        self.doc['paths']['/items/{id}']['post'] = update
        self.refreeze()
        rows = self.flow(create_status=422, location=False)
        rows[0].update(method='PUT', path='/api/v1/projects/4/items')
        rows[2]['method'] = 'POST'
        vs, _ = self.check(rows)
        self.assertEqual(vs[0]['reason'], 'S2_CROSS_ROUTE_PARENT_CONTEXT_UNPROVEN')


if __name__ == '__main__':
    unittest.main()
