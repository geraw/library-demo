import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('box009', ROOT / 'natchan.py')
box = importlib.util.module_from_spec(spec)
spec.loader.exec_module(box)
from common import InputError, Unsupported, canonical, digest, loads, read, write
from contract_context import derive
from traffic import exchanges, MAX_HAR_BYTES
from judge import analyze


def fixture():
    return {'openapi': '3.0.3', 'info': {'title': 'Synthetic control', 'version': '1'},
            'servers': [{'url': 'https://example.invalid/api/v1'}],
            'paths': {
                '/items/{id}': {
                    'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                    'get': {'operationId': 'getItem', 'responses': {
                        '200': {'description': 'ok', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Item'}}}},
                        '404': {'description': 'missing'}}},
                    'patch': {'requestBody': {'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Item'}}}},
                              'responses': {'200': {'description': 'ok'}, '422': {'description': 'invalid'}}}},
                '/items': {'post': {'responses': {'201': {'description': 'created'}}}}},
            'components': {'schemas': {'Item': {'type': 'object', 'required': ['title'],
                                               'properties': {'id': {'type': 'integer', 'readOnly': True},
                                                              'title': {'type': 'string', 'maxLength': 40},
                                                              'owner_id': {'type': 'integer'}}}},
                           'securitySchemes': {'token': {'type': 'http', 'scheme': 'bearer'}}}}


def record(status=200, **kwargs):
    return dict(method='GET', path='/api/v1/items/7', status=status, **kwargs)


class ContractTrackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.contract = self.home / 'contract.json'
        self.knowledge = self.home / 'knowledge.json'
        self.freeze = self.home / 'freeze.json'
        self.traffic = self.home / 'traffic.jsonl'
        self.request = self.home / 'request.json'
        self.doc = fixture()
        self.refreeze()
        self.req = {'schema_version': 'natchan-semantic-request/1',
                    'run': {'id': 'fixture', 'product': 'example', 'tool': 'provengo', 'start_state': 'fresh_snapshot'},
                    'contract': 'contract.json', 'knowledge': 'knowledge.json', 'freeze': 'freeze.json',
                    'evidence': {'format': 'http-jsonl', 'traffic': 'traffic.jsonl'}}
        self.rows([record()])

    def refreeze(self):
        write(self.contract, self.doc)
        write(self.knowledge, box.contract(self.contract))
        write(self.freeze, box.make_freeze(self.contract, self.knowledge))

    def rows(self, rows):
        self.traffic.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')

    def invoke(self, name='out'):
        write(self.request, self.req)
        out = self.home / name
        result = box.run(self.request, out)
        return result, out

    def verdicts(self, out):
        return [json.loads(l) for l in (out / 'verdicts.jsonl').read_text().splitlines()]

    def test_derivation_has_exact_contract_hash(self):
        self.assertEqual(loads(read(self.knowledge))['contract_sha256'], digest(read(self.contract)))

    def test_fields_and_sources_are_from_contract(self):
        ctx = loads(read(self.knowledge))
        op = next(o for o in ctx['operations'] if o['key'] == 'GET /items/{id}')
        title = op['responses']['200']['fields']['title']
        self.assertEqual(title['constraints']['maxLength'], 40)
        self.assertEqual(title['provenance'], '#/components/schemas/Item/properties/title')

    def test_schema_ref_does_not_prove_reference_integrity(self):
        ctx = loads(read(self.knowledge))
        self.assertEqual(ctx['references']['status'], 'unknown')
        self.assertEqual(ctx['entity_candidates'][0]['identifier_fields']['status'], 'unknown')
        self.assertIn('owner_id', ctx['entity_candidates'][0]['identifier_fields']['candidates'])

    def test_methods_do_not_silently_prove_business_roles(self):
        self.assertTrue(all(o['role']['status'] == 'ambiguous' for o in loads(read(self.knowledge))['operations']))

    def test_security_schemes_but_not_guessed_logout(self):
        ctx = loads(read(self.knowledge))
        self.assertEqual(ctx['security_schemes']['token']['status'], 'declared')
        self.assertEqual(ctx['session_ending_operations']['status'], 'unknown')

    def test_explicit_operation_link_is_retained_without_foreign_key_claim(self):
        self.doc['paths']['/items']['post']['responses']['201']['links'] = {
            'item': {'operationId': 'getItem', 'parameters': {'id': '$response.body#/id'}}}
        self.refreeze()
        op = next(o for o in loads(read(self.knowledge))['operations'] if o['method'] == 'POST')
        self.assertEqual(op['links'][0]['parameters']['id'], '$response.body#/id')
        self.assertEqual(op['links'][0]['interpretation'], 'operation_link_not_foreign_key_proof')

    def test_external_ref_and_recursive_schema_are_explicit(self):
        self.doc['components']['schemas']['Item']['properties']['external'] = {'$ref': 'other.json#/X'}
        self.doc['components']['schemas']['Item']['properties']['self'] = {'$ref': '#/components/schemas/Item'}
        self.refreeze()
        gaps = loads(read(self.knowledge))['gaps']
        self.assertTrue(any(g['code'] == 'UNRESOLVED_REFERENCE' for g in gaps))
        self.assertTrue(any(g['code'] == 'RECURSIVE_SCHEMA' for g in gaps))

    def test_recursive_fanout_does_not_expand_exponentially(self):
        item = self.doc['components']['schemas']['Item']
        item['properties']['left'] = {'$ref': '#/components/schemas/Item'}
        item['properties']['right'] = {'$ref': '#/components/schemas/Item'}
        self.refreeze()
        self.assertLess(self.knowledge.stat().st_size, 20_000)

    def test_composition_not_silently_flattened(self):
        self.doc['components']['schemas']['Item']['allOf'] = [{'required': ['id']}]
        self.refreeze()
        op = next(o for o in loads(read(self.knowledge))['operations'] if o['method'] == 'GET')
        self.assertEqual(op['responses']['200']['status'], 'ambiguous')

    def test_swagger_2_and_response_references(self):
        self.doc = {'swagger': '2.0', 'basePath': '/v1', 'paths': {'/items': {'get': {'responses': {'200': {'$ref': '#/responses/Items'}}}}},
                    'responses': {'Items': {'description': 'ok', 'schema': {'type': 'array', 'items': {'type': 'string'}}}}}
        self.refreeze()
        ctx = loads(read(self.knowledge))
        self.assertEqual(ctx['api_base_paths'], ['/v1'])
        self.assertEqual(ctx['operations'][0]['responses']['200']['constraints']['type'], 'array')

    def test_bad_contracts_refused_as_input_errors(self):
        for mutate in (
            lambda d: d.update(paths=[]),
            lambda d: d.update(components=[]),
            lambda d: d['paths']['/items/{id}'].update(parameters='bad'),
            lambda d: d['components']['schemas'].update(Item={'$ref': '#/missing'}),
            lambda d: d['paths']['/items']['post'].update(responses=[]),
        ):
            doc = fixture()
            mutate(doc)
            write(self.contract, doc)
            with self.subTest(doc=doc), self.assertRaises(InputError):
                box.contract(self.contract)

    def test_ref_siblings_and_boolean_schema_do_not_crash(self):
        self.doc['components']['schemas']['Item']['properties']['x'] = True
        self.doc['components']['schemas']['Item']['properties']['y'] = {'$ref': '#/components/schemas/Item', 'maxLength': 3}
        self.refreeze()
        self.assertTrue(loads(read(self.knowledge))['gaps'])

    def test_declared_control_and_failure_are_distinguished(self):
        self.rows([record(), record(404), record(500), record(418)])
        result, out = self.invoke()
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual([v['value'] for v in self.verdicts(out)], ['consistent', 'consistent', 'violation', 'violation'])
        coverage = loads(read(out / 'coverage.json'))
        self.assertEqual(coverage['classes']['S7']['counts']['violation'], 2)
        self.assertTrue(coverage['classes']['S5']['implemented'])
        self.assertEqual(coverage['classes']['S5']['opportunities'], 0)
        self.assertIsNone(coverage['classes']['S4']['counts']['violation'])

    def test_same_traffic_same_verdicts_across_four_tools(self):
        self.rows([record(500), record(200), record(None)])
        answers = []
        for tool in ('provengo', 'restler', 'evomaster', 'schemathesis'):
            self.req['run']['tool'] = tool
            _, out = self.invoke(tool)
            answers.append((out / 'verdicts.jsonl').read_bytes())
        self.assertTrue(all(a == answers[0] for a in answers))

    def test_producer_labels_and_bug_ids_have_no_effect(self):
        self.rows([record(200)])
        _, a = self.invoke('a')
        self.rows([record(200, verdict='crash', known_bugs=['GIT-C2'], facts={'server_error': True}, action='edge_update', logical_id='bug')])
        _, b = self.invoke('b')
        va, vb = self.verdicts(a)[0], self.verdicts(b)[0]
        # Raw input bytes changed, so exact source hash and evidence-derived ID must change.
        for value in (va, vb):
            value.pop('id')
            value.pop('evidence')
        self.assertEqual(va, vb)

    def test_journal_ignores_all_producer_check_categories(self):
        self.req['evidence']['format'] = 'journal-jsonl'
        self.rows([{'category': 'research', **record(200)}, {'category': 'atomicity-check', 'verdict': 'partial'},
                   {'category': 'STORY_CHECK', 'verdict': 'failure'}, {'category': 'known-failure', 'status': 500}])
        r, out = self.invoke()
        self.assertEqual(r['exchanges'], 1)
        self.assertEqual(loads(read(out / 'coverage.json'))['ingestion']['ignored_non_http'], 3)

    def test_5xx_declared_by_contract_still_candidate(self):
        self.doc['paths']['/items/{id}']['get']['responses']['500'] = {'description': 'error'}
        self.refreeze()
        self.rows([record(500)])
        _, out = self.invoke()
        self.assertEqual(self.verdicts(out)[0]['reason'], 'SERVER_5XX_CANDIDATE')

    def test_declared_wildcard_and_default(self):
        for code in ('2XX', 'default'):
            self.doc['paths']['/items/{id}']['get']['responses'] = {code: {'description': 'ok'}}
            self.refreeze()
            _, out = self.invoke(code)
            self.assertEqual(self.verdicts(out)[0]['value'], 'consistent')

    def test_missing_answer_unknown_route_and_ambiguous_route_abstain(self):
        self.rows([record(None), dict(method='GET', path='/unknown', status=200)])
        _, out = self.invoke()
        self.assertTrue(all(v['value'] == 'not_evaluable' for v in self.verdicts(out)))
        self.doc['paths']['/items/{other}'] = copy.deepcopy(self.doc['paths']['/items/{id}'])
        self.refreeze()
        self.rows([record()])
        _, out = self.invoke('ambiguous')
        self.assertEqual(self.verdicts(out)[0]['reason'], 'OPERATION_MATCH_AMBIGUOUS')

    def test_no_traffic_is_null_not_zero(self):
        self.req['evidence'] = {'format': 'none'}
        r, out = self.invoke()
        self.assertIsNone(r['exchanges'])
        self.assertIsNone(loads(read(out / 'coverage.json'))['classes']['S7']['counts']['violation'])

    def test_occurrences_are_not_distinct_bugs(self):
        self.rows([record(500), record(500)])
        _, out = self.invoke()
        findings = loads(read(out / 'findings.json'))
        self.assertEqual(len(findings['groups']), 1)
        self.assertEqual(findings['groups'][0]['occurrences'], 2)
        self.assertIsNone(findings['distinct_bugs'])

    def test_exact_evidence_locator_and_contract_pointer(self):
        _, out = self.invoke()
        v = self.verdicts(out)[0]
        self.assertEqual(v['evidence'], [{'sha256': digest(read(self.traffic)), 'line_1based': 1}])
        self.assertEqual(v['knowledge'][0]['pointer'], '#/paths/~1items~1{id}/get/responses')

    def test_unique_server_log_id_correlation_and_no_root_cause_claim(self):
        self.rows([record(500, request_id='r1')])
        log = self.home / 'sut.jsonl'
        log.write_text(json.dumps({'request_id': 'r1', 'method': 'GET', 'path': '/api/v1/items/7', 'status': 500, 'message': 'constraint 123 failed'}))
        self.req['evidence']['server_log'] = log.name
        _, out = self.invoke()
        v = self.verdicts(out)[0]
        self.assertEqual(len(v['evidence']), 2)
        self.assertFalse(v['root_cause_proven'])
        self.assertIn('server_signature_sha256', v)

    def test_duplicate_http_or_log_ids_never_correlate(self):
        log = self.home / 'sut.jsonl'
        line = json.dumps({'request_id': 'r1', 'message': 'failed'}) + '\n'
        self.req['evidence']['server_log'] = log.name
        self.rows([record(500, request_id='r1'), record(500, request_id='r1')])
        log.write_text(line)
        _, out = self.invoke('httpdup')
        self.assertTrue(all('server_signature_sha256' not in v for v in self.verdicts(out)))
        self.rows([record(500, request_id='r1')])
        log.write_text(line * 2)
        _, out = self.invoke('logdup')
        self.assertNotIn('server_signature_sha256', self.verdicts(out)[0])

    def test_log_adjacency_without_id_never_correlates(self):
        log = self.home / 'sut.jsonl'
        log.write_text(json.dumps({'message': 'server failed'}))
        self.req['evidence']['server_log'] = log.name
        self.rows([record(500)])
        _, out = self.invoke()
        self.assertNotIn('server_signature_sha256', self.verdicts(out)[0])

    def test_ambiguous_or_conflicting_id_headers_are_not_joined(self):
        for i, extra in enumerate((
            {'request_headers': {'X-Request-ID': 'a', 'x-request-id': 'b'}},
            {'request_id': 'a', 'request_headers': {'x-request-id': 'b'}},
        )):
            self.rows([record(500, **extra)])
            self.assertEqual(self.invoke(str(i))[0]['exit_code'], 2)

    def test_redacted_request_id_is_not_correlation_evidence(self):
        self.rows([record(500, request_id='<TOKEN>')])
        log = self.home / 'sut.jsonl'
        log.write_text(json.dumps({'request_id': '<TOKEN>', 'message': 'failed'}))
        self.req['evidence']['server_log'] = log.name
        _, out = self.invoke()
        self.assertNotIn('server_signature_sha256', self.verdicts(out)[0])

    def test_unrecognized_extra_configuration_cannot_inject_sbt_knowledge(self):
        self.req['configuration'] = {'story_semantics': 'sbt.json'}
        with self.assertRaises(InputError):
            self.invoke()

    def test_invalid_cli_request_returns_2_not_engine_error(self):
        self.request.write_text('{broken')
        p = subprocess.run([sys.executable, str(ROOT / 'natchan.py'), 'analyze', '--request', str(self.request),
                            '--output', str(self.home / 'invalid')], capture_output=True)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn(b'Traceback', p.stderr)

    def test_native_log_and_zip_have_explicit_unsupported_format(self):
        for fmt in ('restler-network', 'toolkit-v1', 'zip'):
            self.req['evidence']['format'] = fmt
            with self.subTest(fmt=fmt), self.assertRaises(Unsupported):
                self.invoke(fmt)

    def test_contract_knowledge_and_code_freeze_drift_refused(self):
        self.doc['info']['version'] = '2'
        write(self.contract, self.doc)
        r, _ = self.invoke('contractdrift')
        self.assertEqual(r['exit_code'], 2)
        self.refreeze()
        ctx = loads(read(self.knowledge))
        ctx['references']['status'] = 'confirmed'
        write(self.knowledge, ctx)
        r, _ = self.invoke('knowledgedrift')
        self.assertEqual(r['exit_code'], 2)
        self.refreeze()
        manifest = loads(read(self.freeze))
        manifest['engine']['judge.py'] = '0' * 64
        write(self.freeze, manifest)
        r, _ = self.invoke('codedrift')
        self.assertEqual(r['exit_code'], 2)

    def test_byte_identical_outputs_with_same_inputs(self):
        _, a = self.invoke('a')
        _, b = self.invoke('b')
        self.assertEqual({p.name: p.read_bytes() for p in a.iterdir()}, {p.name: p.read_bytes() for p in b.iterdir()})

    def test_output_hashes_and_commit_marker(self):
        r, out = self.invoke()
        for name, h in r['artifacts'].items():
            self.assertEqual(digest((out / name).read_bytes()), h)
        self.assertNotIn('result.json', r['artifacts'])

    def test_malformed_partial_evidence_no_partial_success_files(self):
        self.traffic.write_text(json.dumps(record()) + '\n{broken')
        r, out = self.invoke()
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual({p.name for p in out.iterdir()}, {'result.json', 'diagnostics.json'})

    def test_invalid_status_and_duplicate_keys(self):
        for i, row in enumerate([record(True), record(600), record(200.0)]):
            self.rows([row])
            r, _ = self.invoke(str(i))
            self.assertEqual(r['exit_code'], 2)
        self.traffic.write_text('{"method":"GET","method":"POST"}\n')
        self.assertEqual(self.invoke('duplicate')[0]['exit_code'], 2)

    def test_nan_overflow_and_deep_json_refused(self):
        for raw in ('{"x":NaN}', '{"x":1e9999}', '[' * 2000 + '0' + ']' * 2000):
            with self.subTest(raw=raw[:40]), self.assertRaises(InputError):
                loads(raw)

    def test_oversized_line_is_explicit_unsupported(self):
        self.traffic.write_text(json.dumps(record(input='x' * 200)))
        with patch('traffic.MAX_LINE_BYTES', 100):
            self.assertEqual(self.invoke()[0]['exit_code'], 3)

    def test_large_har_refused_as_unsupported_without_parsing(self):
        self.req['evidence']['format'] = 'har'
        self.traffic.write_text('x' * 100)
        with patch('traffic.MAX_HAR_BYTES', 50):
            self.assertEqual(self.invoke()[0]['exit_code'], 3)

    def test_unsupported_format_never_engine_error(self):
        self.req['evidence']['format'] = 'toolkit-v1'
        with self.assertRaises(Unsupported):
            self.invoke()

    def test_har_and_jsonl_same_semantic_decision(self):
        self.rows([record(500)])
        _, a = self.invoke('jsonl')
        self.req['evidence']['format'] = 'har'
        write(self.traffic, {'log': {'version': '1.2', 'entries': [{'request': {'method': 'GET', 'url': '/api/v1/items/7'}, 'response': {'status': 500}}]}})
        _, b = self.invoke('har')
        for field in ('property', 'value', 'reason', 'operation', 'input_class'):
            self.assertEqual(self.verdicts(a)[0][field], self.verdicts(b)[0][field])
        self.assertEqual(self.verdicts(b)[0]['evidence'][0]['locator'], '/log/entries/0')

    def test_fresh_output_required(self):
        self.invoke()
        with self.assertRaises(InputError):
            self.invoke()

    def test_unexpected_fault_exit_4(self):
        with patch.object(box, 'execute', side_effect=RuntimeError('internal secret')):
            r, out = self.invoke()
        self.assertEqual(r['exit_code'], 4)
        self.assertNotIn('internal secret', (out / 'diagnostics.json').read_text())

    def test_input_mutation_rejected(self):
        original = box.analyze
        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            self.traffic.write_text('')
            return result
        with patch.object(box, 'analyze', side_effect=mutate):
            self.assertEqual(self.invoke()[0]['exit_code'], 2)

    def test_share_outputs_do_not_copy_raw_personal_values(self):
        self.rows([record(500, request_id='my-secret-id', response='C:\\Users\\PrivateName',
                          input={'password': 'SECRET_PASSWORD'}, actor='PrivateName')])
        _, out = self.invoke()
        text = '\n'.join(p.read_text() for p in out.iterdir())
        self.assertNotIn('PrivateName', text)
        self.assertNotIn('SECRET_PASSWORD', text)
        self.assertNotIn('my-secret-id', text)
        self.assertNotIn(str(self.home), text)

    def test_cli_isolated_mode_end_to_end(self):
        write(self.request, self.req)
        p = subprocess.run([sys.executable, '-I', str(ROOT / 'natchan.py'), 'analyze', '--request', str(self.request),
                            '--output', str(self.home / 'isolated')], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_90000_exchanges_processed_without_retaining_traffic(self):
        line = json.dumps(record()) + '\n'
        self.traffic.write_text(line * 90_000)
        r, out = self.invoke()
        self.assertEqual(r['exit_code'], 0)
        self.assertEqual(r['exchanges'], 90_000)
        coverage = loads(read(out / 'coverage.json'))
        self.assertEqual(coverage['classes']['S7']['counts']['consistent'], 90_000)
        self.assertEqual(loads(read(out / 'findings.json'))['groups'], [])


if __name__ == '__main__':
    unittest.main()
