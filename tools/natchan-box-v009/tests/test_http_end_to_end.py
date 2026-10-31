"""Real loopback HTTP capture -> independent analyzer. Synthetic SUT, never a research result."""
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread
import unittest

import test_state_semantics as s
from common import read, loads


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, value):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.answer(200, self.server.state)

    def do_PATCH(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        mode = self.server.mode
        if mode != 'rollback':
            self.server.state['title'] = 'silently_changed' if mode == 'silent' else data['title']
            if mode != 'partial':
                self.server.state['owner_id'] = data['owner_id']
        self.answer(500 if mode in ('partial', 'rollback', 'committed') else 200, {'accepted': mode not in ('partial', 'rollback', 'committed')})


class RealCaptureTests(unittest.TestCase):
    setUp = s.StateTests.setUp
    refreeze = s.StateTests.refreeze
    rows = s.StateTests.rows
    invoke = s.StateTests.invoke
    verdicts = s.StateTests.verdicts
    prepare = s.StateTests.prepare
    row = s.StateTests.row
    def check_mode(self, mode, expected_prop, expected_value, outcome=None, long_title=False):
        # setUp derived/froze before any of the following requests exist.
        self.prepare()
        server = HTTPServer(('127.0.0.1', 0), Handler)
        server.state = {'id': 7, 'title': 'old', 'owner_id': 1}
        server.mode = mode
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        captured = []
        try:
            for method, payload in [('GET', None), ('PATCH', {'title': 'x' * 41 if long_title else 'new', 'owner_id': 2}), ('GET', None)]:
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                start = datetime.now(timezone.utc).isoformat()
                conn.request(method, '/api/v1/items/7', body=json.dumps(payload) if payload else None,
                             headers={'Content-Type': 'application/json'})
                response = conn.getresponse()
                body = json.loads(response.read())
                end = datetime.now(timezone.utc).isoformat()
                captured.append(self.row(method, response.status, input=payload, response=body,
                                         started_utc=start, ended_utc=end))
                conn.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()
        self.rows(captured)
        result, out = self.invoke()
        self.assertEqual(result['exit_code'], 0)
        v = next(v for v in self.verdicts(out) if v['property'] == expected_prop)
        self.assertEqual(v['value'], expected_value)
        if outcome:
            self.assertEqual(v['details']['outcome'], outcome)
        self.assertFalse(loads(read(out / 'provenance.json'))['producer_verdicts_used'])

    def test_real_correct_roundtrip(self):
        self.check_mode('correct', 'S1', 'consistent')

    def test_real_silent_change_candidate(self):
        self.check_mode('silent', 'S1', 'violation')

    def test_real_partial_commit_observed(self):
        self.check_mode('partial', 'S5', 'policy_observation', 'partial')

    def test_real_full_commit_despite_error_observed(self):
        self.check_mode('committed', 'S5', 'policy_observation', 'committed_despite_error')

    def test_real_rollback_control(self):
        self.check_mode('rollback', 'S5', 'consistent', 'unchanged')

    def test_real_declared_length_violation_stored(self):
        self.check_mode('correct', 'S3', 'violation', long_title=True)


if __name__ == '__main__':
    unittest.main()
