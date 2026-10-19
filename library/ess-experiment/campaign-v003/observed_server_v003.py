"""Managed localhost fixture and observing proxy. Never modifies the imported SUT.

Tool traffic is recorded separately from independent GET readbacks. The proxy is
serial: this experiment explores logical sequences, not overlapping backend calls.
"""
import argparse
import http.client
import importlib.util
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from werkzeug.serving import make_server


class Ledger:
    def __init__(self, forward, emit):
        self.forward, self.emit = forward, emit
        self.case = None
        self.reset()

    def reset(self):
        self.expected = {x: [] for x in ('users', 'books', 'loans', 'holds')}
        self.history = {}
        self.tainted = False

    def check(self, method, path, payload, status, response):
        p = urlsplit(path).path.strip('/').split('/')
        entity = p[0]
        if entity == 'reset':
            self.reset()
            return
        if self.case is None or entity not in self.expected:
            return
        violations = []
        before = json.loads(json.dumps(self.expected))
        if method == 'POST' and len(p) == 1 and isinstance(payload, dict):
            if entity == 'loans':
                u, b = payload.get('userId'), payload.get('bookId')
                legal = (type(u) is int and type(b) is int and
                         any(x['id'] == u for x in before['users']) and
                         any(x['id'] == b for x in before['books']) and
                         not any(x['bookId'] == b for x in before['loans']))
                if legal and status != 201:
                    violations.append({'rule': 'VALID_LOAN_REJECTED',
                                       'active_for_user': sum(x['userId'] == u for x in before['loans']),
                                       'prior_pair_loans': self.history.get((u, b), 0)})
                if legal and status == 201:
                    self.history[(u, b)] = self.history.get((u, b), 0) + 1
            if status == 201 and isinstance(response, dict) and 'id' in response:
                self.expected[entity].append(response)
        elif method == 'DELETE' and status == 200:
            try:
                ids = [int(x) for x in p[1:]]
                if entity == 'loans' and len(ids) == 2:
                    self.expected[entity] = [x for x in before[entity]
                                             if (x['userId'], x['bookId']) != tuple(ids)]
                elif len(ids) == 1:
                    self.expected[entity] = [x for x in before[entity] if x['id'] != ids[0]]
            except ValueError:
                pass
        elif method == 'GET' and entity == 'books' and len(p) == 2:
            try:
                book = next((x for x in before['books'] if x['id'] == int(p[1])), None)
                if book and (status != 200 or response != book):
                    violations.append({'rule': 'EXISTING_BOOK_READ', 'expected_book': book})
            except ValueError:
                pass
        # Readback is observational only: it never supplies identifiers to a tool.
        # Run after writes; failed writes must also preserve state.
        if method in ('POST', 'DELETE'):
            for name in self.expected:
                code, actual = self.forward('GET', '/' + name, None)
                self.emit({'role': 'oracle', 'case': self.case, 'method': 'GET',
                           'path': '/' + name, 'status': code, 'response': actual})
                if code != 200 or not isinstance(actual, list):
                    violations.append({'rule': 'READBACK_UNAVAILABLE', 'entity': name})
                elif sorted(actual, key=lambda x: x.get('id', 0)) != sorted(self.expected[name], key=lambda x: x.get('id', 0)):
                    violations.append({'rule': 'STATE_MISMATCH', 'entity': name,
                                       'expected': self.expected[name], 'actual': actual})
        if violations:
            self.emit({'role': 'verdict', 'case': self.case, 'method': method, 'path': path,
                       'status': status, 'response': response, 'violations': violations,
                       'prefix_tainted': self.tainted})
            self.tainted = True


def serve(sut_path, bugs, port, backend_port, logfile):
    service_token = os.environ['ISSTA_SERVICE_TOKEN']
    os.environ['ISSTA_BUGS'] = bugs
    spec = importlib.util.spec_from_file_location('campaign_sut', sut_path)
    sut = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sut)
    if not hasattr(sut, 'BUGS'):
        raise RuntimeError('Expected the versioned experiment fixture, not the original SUT')
    backend = make_server('127.0.0.1', backend_port, sut.app, threaded=False)
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    output = open(logfile, 'a', encoding='utf-8', buffering=1)

    def emit(record):
        record['time_ns'] = time.time_ns()
        output.write(json.dumps(record, ensure_ascii=True) + '\n')

    def forward(method, path, raw):
        conn = http.client.HTTPConnection('127.0.0.1', backend_port, timeout=15)
        conn.request(method, path, body=raw, headers={'Content-Type': 'application/json'})
        reply = conn.getresponse()
        data = reply.read().decode('utf-8', errors='replace')
        try:
            data = json.loads(data)
        except ValueError:
            pass
        code = reply.status
        conn.close()
        return code, data

    ledger = Ledger(forward, emit)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            try:
                payload = json.loads(raw) if raw else None
            except ValueError:
                payload = None
            if self.path == '/__campaign__/health':
                status, result = 200, {'bugs': sorted(sut.BUGS), 'pid': os.getpid(),
                                      'sut': str(sut_path), 'service_token': service_token}
            elif self.path == '/__campaign__/shutdown' and self.command == 'POST':
                if not isinstance(payload, dict) or payload.get('token') != service_token:
                    status, result = 403, {'error': 'Incorrect service token'}
                else:
                    status, result = 200, {'shutdown': True}
                    threading.Thread(target=proxy.shutdown, daemon=True).start()
            elif self.path == '/__campaign__/case' and self.command == 'POST':
                ledger.case = payload['case']
                status, result = forward('POST', '/reset', b'{}')
                if status != 200:
                    raise RuntimeError('Reset failed')
                ledger.reset()
                emit({'role': 'boundary', 'case': ledger.case, 'bugs': sorted(sut.BUGS)})
            else:
                status, result = forward(self.command, self.path, raw or None)
                emit({'role': 'tool', 'case': ledger.case, 'method': self.command,
                      'path': self.path, 'request': payload, 'status': status, 'response': result})
                ledger.check(self.command, self.path, payload, status, result)
            data = json.dumps(result).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_DELETE = do_PUT = do_PATCH = do_OPTIONS = dispatch

    emit({'role': 'startup', 'bugs': sorted(sut.BUGS), 'sut': str(sut_path),
          'pid': os.getpid(), 'port': port, 'backend_port': backend_port})
    proxy = HTTPServer(('127.0.0.1', port), Handler)
    try:
        proxy.serve_forever()
    finally:
        proxy.server_close()
        backend.shutdown()
        backend.server_close()
        output.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sut', type=Path, required=True)
    parser.add_argument('--bugs', default='none')
    parser.add_argument('--port', type=int, default=23243)
    parser.add_argument('--backend-port', type=int, default=23244)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    serve(args.sut, args.bugs, args.port, args.backend_port, args.log)
