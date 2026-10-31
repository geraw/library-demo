"""Real HTTP create/read/update/read sequences; the judge only receives captured exchanges."""
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread
import unittest

import test_create_update as p


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, body, location=False):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        if location:
            self.send_header('Location', '/api/v1/items/7')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.answer(200, self.server.value)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.server.mode == 'create_reject':
            self.answer(422, {'message': 'rejected'})
        else:
            self.server.value.update(body)
            if self.server.mode == 'diverge':
                self.server.value['title'] = 'create_normalization'
            self.answer(201, self.server.value, True)

    def do_PATCH(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.server.mode == 'update_reject':
            self.answer(422, {'message': 'rejected'})
        else:
            self.server.value.update(body)
            if self.server.mode == 'diverge':
                self.server.value['title'] = 'update_normalization'
            self.answer(200, self.server.value)


class LivePathTests(unittest.TestCase):
    setUp = p.PathTests.setUp
    refreeze = p.PathTests.refreeze
    rows = p.PathTests.rows
    invoke = p.PathTests.invoke
    verdicts = p.PathTests.verdicts
    prepare = p.PathTests.prepare
    row = p.PathTests.row
    configured = p.PathTests.configured
    check = p.PathTests.check

    def exercise(self, mode, expected):
        self.configured()  # knowledge/freeze precede capture generation
        server = HTTPServer(('127.0.0.1', 0), Handler)
        server.mode, server.value = mode, {'id': 7, 'title': 'old', 'owner_id': 1}
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        rows = []
        try:
            for method, path, body in [('POST', '/api/v1/items', {'title': 'probe', 'owner_id': 1}),
                                       ('GET', '/api/v1/items/7', None),
                                       ('PATCH', '/api/v1/items/7', {'title': 'probe'}),
                                       ('GET', '/api/v1/items/7', None)]:
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                started = datetime.now(timezone.utc).isoformat()
                conn.request(method, path, json.dumps(body) if body else None, {'Content-Type': 'application/json'})
                response = conn.getresponse()
                payload = json.loads(response.read())
                headers = dict(response.getheaders())
                ended = datetime.now(timezone.utc).isoformat()
                rows.append(self.row(method, response.status, input=body, response=payload, path=path,
                                     response_headers=headers, started_utc=started, ended_utc=ended))
                conn.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()
        verdicts, _ = self.check(rows)
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0]['value'], expected)

    def test_live_equal_paths_control(self):
        self.exercise('control', 'consistent')

    def test_live_stored_value_divergence(self):
        self.exercise('diverge', 'violation')

    def test_live_create_accepts_update_rejects(self):
        self.exercise('update_reject', 'policy_observation')

    def test_live_create_rejects_update_accepts(self):
        self.exercise('create_reject', 'policy_observation')


if __name__ == '__main__':
    unittest.main()
