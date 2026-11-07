"""Meaningful integration checks: public HTTP requests, recorded state and control."""
import json
import shutil
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from campaign_v002 import Service, call, evaluate


class Observation(unittest.TestCase):
    def test_redirecting_launcher_and_closed_logs(self):
        fixture = Path(__file__).resolve().parents[2] / 'sut/sut_buggy_issta.py'
        if not fixture.exists():
            fixture = Path(__file__).resolve().parents[1] / 'sut_buggy_issta.py'
        real_popen = subprocess.Popen
        def redirected(args, **kwargs):
            return real_popen([sys.executable, '-c',
                'import subprocess,sys; sys.exit(subprocess.call(sys.argv[1:]))'] + args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy2(fixture, root / 'sut_buggy_issta.py')
            with patch('campaign_v002.subprocess.Popen', side_effect=redirected):
                with Service(root, root, 'none'):
                    health = call('http://127.0.0.1:23243/__campaign__/health')
                    identity = json.loads((root / 'server_identity.json').read_text())
                    self.assertNotEqual(health['pid'], identity['launcher_pid'])
            # A gracefully stopped worker must release both files (Windows requirement).
            (root / 'http.jsonl').unlink()
            (root / 'server.log').unlink()

    def test_control_and_five_isolated_faults(self):
        # In the repository, the fixture is at library/sut, two directories up.
        fixture = Path(__file__).resolve().parents[2] / 'sut/sut_buggy_issta.py'
        if not fixture.exists():
            fixture = Path(__file__).resolve().parents[1] / 'sut_buggy_issta.py'
        for fault in range(1, 6):
            for enabled in ('none', str(fault)):
                with self.subTest(fault=fault, enabled=enabled), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    shutil.copy2(fixture, root / 'sut_buggy_issta.py')
                    with Service(root, root, enabled):
                        call('http://127.0.0.1:23243/__campaign__/case', {'case': 'verification'})
                        def request(method, path, payload=None):
                            data = None if payload is None else json.dumps(payload).encode()
                            req = Request('http://127.0.0.1:23243' + path, data=data,
                                          headers={'Content-Type': 'application/json'}, method=method)
                            try:
                                response = urlopen(req, timeout=10)
                            except HTTPError as ex:
                                response = ex
                            with response:
                                return response.status, json.load(response)
                        user = request('POST', '/users', {'name': 'Reader'})[1]['id']
                        books = [request('POST', '/books', {'title': str(i)})[1]['id'] for i in range(4)]
                        def loan(book):
                            return request('POST', '/loans', {'userId': user, 'bookId': book})
                        if fault == 1:
                            for book in books:
                                loan(book)
                        elif fault == 2:
                            for _ in range(2):
                                loan(books[0])
                                request('DELETE', f'/loans/{user}/{books[0]}')
                            loan(books[0])
                        elif fault == 3:
                            loan(books[0]); loan(books[1])
                            request('DELETE', f'/loans/{user}/{books[0]}')
                        elif fault == 4:
                            request('GET', f'/books/{books[0]}')
                        else:
                            holds = [request('POST', '/holds', {'userId': user, 'bookId': b})[1]['id'] for b in books[:2]]
                            request('DELETE', '/holds/' + str(holds[0]))
                    result = evaluate(root)
                    self.assertGreater(result['tool_http_requests'], 0)
                    findings = result['semantic_candidates']
                    self.assertEqual(bool(findings), enabled != 'none')
                    if findings:
                        self.assertFalse(findings[0]['prefix_tainted'])


if __name__ == '__main__':
    unittest.main()
