import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import native_analysis as gateway

class EvidenceTests(unittest.TestCase):
    def folder(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def test_failed_exit_overrides_report_presence_and_wrapper_complete(self):
        p=self.folder();(p/'report.json').write_text('{}')
        (p/'tool-console.log').write_text('G018_COMPLETE\n### exit 1\n')
        self.assertEqual(gateway.lifecycle(p)['process_status'],'failed')

    def test_missing_report_and_missing_exit_are_unknown(self):
        p=self.folder();(p/'tool-console.log').write_text('Phase SEARCH lasted: 0h 20m 0s\n')
        result=gateway.lifecycle(p)
        self.assertIsNone(result['native_fault_count'])
        self.assertEqual(result['process_status'],'unknown_or_incomplete')

    def test_c1_signature_is_not_exact_match_or_partial_persistence(self):
        p=self.folder()/'sut.log'
        p.write_text('2026/10/22 12:01:25 EditIssue() [E] InternalServerError: user does not exist [uid: 0]\n'
            '2026/10/22 12:01:25 router: completed PATCH /api/v1/repos/a/b/issues/1 for 172.1.0.4:52, 500 Internal Server Error\n')
        f=gateway.signatures(p)['findings'][0]
        self.assertEqual(f['known_bug_candidate'],'GIT-C1')
        self.assertFalse(f['exact_known_bug_confirmed']);self.assertFalse(f['causal_join'])
        self.assertEqual(f['partial_persistence'],'not_evaluable')
        self.assertEqual(f['adjacent_response_candidate']['status'],500)

    def test_incompatible_adjacent_request_is_not_attached(self):
        p=self.folder()/'sut.log'
        p.write_text('2026/10/22 12:01:25 EditIssue() [E] InternalServerError: user does not exist\n'
            '2026/10/22 12:01:25 router: completed GET /api/v1/repos/a/b/issues/1 for 172.1.0.4:52, 500 Internal Server Error\n')
        self.assertNotIn('adjacent_response_candidate',gateway.signatures(p)['findings'][0])

    def test_owner_message_not_promoted_and_unknown_signature_preserved(self):
        p=self.folder()/'sut.log';p.write_text('[E] Organization does not have owner team: 2\n[E] completely new error\n')
        r=gateway.signatures(p)
        self.assertEqual(r['findings'][0]['kind'],'log_only_candidate')
        self.assertEqual(len(r['unmatched_error_lines']),1)
        self.assertNotIn('adjacent_response_candidate',r['findings'][0])

    def test_host_fixture_success_excluded_but_tool_success_counted(self):
        p=self.folder()/'sut.log'
        p.write_text('router: completed POST /api/v1/repos/a/b/issues for 172.1.0.1:5, 201 Created\n'
            'router: completed POST /api/v1/repos/a/b/issues for 172.1.0.4:5, 201 Created\n')
        self.assertEqual(gateway.tool_reach(p)['nested_status_classes']['2xx'],1)

if __name__=='__main__':unittest.main()
