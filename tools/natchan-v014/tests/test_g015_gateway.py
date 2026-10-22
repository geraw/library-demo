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
