import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence import ingest
from analyze import analyze_envelope


def trace(status=404,readback=True):
    book={'id':7,'title':'B'}
    events=[dict(role='boundary',case=1,empty_verified=True),
            dict(role='tool',case=1,method='POST',path='/books',request={'title':'B'},status=201,response=book)]
    if readback: events.append(dict(role='oracle',case=1,method='GET',path='/books',status=200,response=[book]))
    events.append(dict(role='tool',case=1,method='GET',path='/books/7',status=status,response=book if status==200 else {'error':'missing'}))
    return events


class AnalysisTests(unittest.TestCase):
    def analyze(self,records):
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'evidence.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('trace.jsonl','\n'.join(json.dumps(r) for r in records))
            envelope=ingest(archive,{'schema_version':1,'runs':[dict(id='r',tool='future',system='library',product_gateway='library-issta-v006',artifacts={'trace':'trace.jsonl'})]})
            return analyze_envelope(envelope)

    def test_bug4_is_external_observation_with_real_source(self):
        r=self.analyze(trace())
        self.assertEqual('complete',r['status'])
        self.assertEqual(['bug-4'],r['runs'][0]['semantic']['external_evaluator']['candidate_classes_in_evaluable_cases'])
        self.assertEqual(1,len(r['findings']))
        f=r['findings'][0]
        self.assertEqual('EXISTING_BOOK_READ',f['rule'])
        self.assertEqual(4,f['source']['line'])
        self.assertEqual('unknown',r['runs'][0]['native']['status'])
        self.assertIsNone(r['summary']['confirmed_unique_bug_count'])

    def test_healthy_and_forged_claim_ignored(self):
        rows=trace(200)+[dict(role='verdict',case=1,violations=[dict(rule='EXISTING_BOOK_READ')])]
        self.assertEqual([],self.analyze(rows)['findings'])

    def test_missing_readback_is_not_a_finding(self):
        r=self.analyze(trace(readback=False))
        self.assertEqual('incomplete',r['status'])
        self.assertEqual([],r['findings'])
        self.assertEqual(0,r['runs'][0]['semantic']['evaluable_case_count'])

    def test_case_reset_prevents_stitching(self):
        rows=trace(200)+[dict(role='boundary',case=2,empty_verified=True),dict(role='tool',case=2,method='GET',path='/books/7',status=404,response={})]
        self.assertEqual([],self.analyze(rows)['findings'])

    def test_tainted_later_violation_not_counted(self):
        rows=trace()+[dict(role='tool',case=1,method='GET',path='/books/7',status=404,response={})]
        r=self.analyze(rows)
        self.assertEqual(1,len(r['findings']))
        self.assertEqual(2,len(r['runs'][0]['semantic']['cases'][0]['result']['verdicts']))

    def test_repeated_case_id_context_uses_boundary_not_id(self):
        r=self.analyze(trace()+trace())
        self.assertEqual(2,len(r['findings']))
        self.assertTrue(set(r['findings'][0]['context_event_ids']).isdisjoint(r['findings'][1]['context_event_ids']))

    def test_bad_trace_cannot_be_clean_after_import(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'evidence.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('trace.jsonl','\n'.join(json.dumps(r) for r in trace())+'\nBROKEN')
            envelope=ingest(archive,{'schema_version':1,'runs':[dict(id='r',tool='x',system='library',product_gateway='library-issta-v006',artifacts={'trace':'trace.jsonl'})]})
            r=analyze_envelope(envelope)
            self.assertEqual('NOT_EVALUATED',r['runs'][0]['semantic']['status'])
            self.assertEqual([],r['findings'])

    def test_opaque_product_is_not_silently_evaluated(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'evidence.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('trace.jsonl','{}')
            envelope=ingest(archive,{'schema_version':1,'runs':[dict(id='r',tool='x',system='new',artifacts={'trace':'trace.jsonl'})]})
            r=analyze_envelope(envelope)
            self.assertEqual('incomplete',r['status'])
            self.assertEqual('NOT_EVALUATED',r['runs'][0]['semantic']['status'])
