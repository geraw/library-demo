import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('g015_gateway', ROOT / 'g015_gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class GatewayTests(unittest.TestCase):
    def test_repository_coverage_ignores_query_and_excludes_non_nested_routes(self):
        self.assertEqual(gateway.repository_route('/api/v1/repos/a/b/issues/7?x=1'),
                         ('/repos/{owner}/{repo}/issues', True))
        self.assertEqual(gateway.repository_route('/api/v1/repos/a/b/issues/7/comments'),
                         ('/repos/{owner}/{repo}/issues', False))
        self.assertIsNone(gateway.repository_route('/api/v1/user/repos'))
        self.assertIsNone(gateway.repository_route('/api/v1/repos/a/b'))

    def test_coverage_no_success_is_not_rejection_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'sut.log'
            p.write_text('x router: completed PATCH /api/v1/repos/a/b/issues/3 for x:1, 404 Not Found\n'
                         'x router: completed POST /api/v1/repos/a/b/issues for x:1, 500 Internal Server Error\n')
            stats, _ = gateway.scan_logs(p)
            reach = stats['repository_reach']
            self.assertEqual(reach['successful_nested_responses'], 0)
            self.assertEqual(reach['issue_patch_status_classes'], {'4xx': 1})
            self.assertEqual(reach['rejection_cause'], 'not_inferred_from_access_status_only')

    def test_successful_nested_response_is_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'sut.log'
            p.write_text('x router: completed POST /api/v1/repos/a/b/issues for x:1, 201 Created\n')
            stats, _ = gateway.scan_logs(p)
            self.assertEqual(stats['repository_reach']['successful_nested_responses'], 1)

    def test_multipart_context_requires_header_and_500_not_operation_name(self):
        self.assertTrue(gateway.multipart_context({'headers': {'Content-Type': ['multipart/form-data']}}, 500)['malformed_multipart_500'])
        for header in ['application/json', 'multipart/form-data; boundary=x', 'multipart/form-data; boundary="x"']:
            self.assertFalse(gateway.multipart_context({'headers': {'content-type': header}}, 500)['malformed_multipart_500'])
        self.assertFalse(gateway.multipart_context({'headers': {'Content-Type': 'multipart/form-data'}}, 404)['malformed_multipart_500'])

    def test_decode_preserves_json_and_non_json(self):
        raw = base64.b64encode(b'{"x":0}').decode()
        self.assertEqual(gateway.decoded({'$base64': raw}), {'x': 0})
        self.assertEqual(gateway.decoded('not json'), 'not json')

    def test_log_error_is_not_automatically_a_500(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'sut.log'
            p.write_text('x [E] Organization does not have owner team: 3\n'
                         'x router: completed GET /api/v1/a for x:1, 200 OK in 1ms\n'
                         'x router: completed PATCH /api/v1/b?x=y for x:1, 500 Internal Server Error\n')
            stats, errors = gateway.scan_logs(p)
            self.assertEqual(stats['completed_requests'], 2)
            self.assertEqual(stats['http_5xx'], 1)
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]['path'], '/api/v1/b')
            self.assertNotIn('request', errors[0])

    def test_native_fault_is_a_claim_not_an_observed_http_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'report.json').write_text(json.dumps({'faults': {
                'totalNumber': 0, 'foundFaults': [{'operationId': 'POST:/x',
                    'faultCategories': [{'code': 100}]}]}}))
            observations, summary = gateway.evomaster(folder, '28.1.0')
            self.assertTrue(summary['counter_mismatch'])
            self.assertNotIn('status', observations[0])
            self.assertEqual(observations[0]['evidence_tier'], 'native_tool_claim')

    def test_ndjson_repeated_snapshot_deduplicated_actual_retry_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            part = folder / 'report-round1'
            part.mkdir()
            def event(timestamp):
                return {'ScenarioFinished': {'recorder': {'label': 'POST /x',
                    'checks': {'case1': [{'name': 'not_a_server_error', 'status': 'failure'}]},
                    'interactions': {'case1': {'timestamp': timestamp,
                        'request': {'method': 'POST', 'uri': 'http://local/x'},
                        'response': {'status_code': 500}}}}}}
            (part / 'events.ndjson').write_text('\n'.join(json.dumps(event(t)) for t in [1, 1, 2]))
            observations, summary = gateway.schemathesis(folder, '28.1.0')
            self.assertEqual(summary['recorded_interactions'], 2)
            self.assertEqual(summary['recorded_http_5xx'], 2)
            self.assertEqual(len(observations), 2)

    def test_unknown_error_not_forced_into_known_family(self):
        self.assertEqual(gateway.error_family('unexpected xyz'), 'other_server_error_log')
        self.assertEqual(gateway.error_family('Organization does not have owner team: 9'),
                         'organization_owner_team_missing')


if __name__ == '__main__':
    unittest.main()
