from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from library_adapter import observations_from_analysis
from classifier import classify


class LibraryAdapterTests(unittest.TestCase):
    def test_future_append_in_legacy_expected_is_not_state_evidence(self):
        left=dict(id=10,userId=1,bookId=1);right=dict(id=20,userId=1,bookId=2)
        def event(id,line,role,payload):return dict(id=id,role=role,source=dict(line=line,artifact_id='a'),payload=payload)
        events=[event('before',1,'oracle',dict(path='/holds',status=200,response=[left,right])),
                event('delete',2,'tool',dict(method='DELETE',path='/holds/10',status=200)),
                event('after',3,'oracle',dict(path='/holds',status=200,response=[]))]
        finding=dict(id='f1',run_id='r',source_event_id='delete',case='1',case_ordinal=1,context_event_ids=['before','delete','after'],
                     evidence=dict(violation=dict(rule='STATE_MISMATCH',entity='holds',expected=[right,dict(id=99,userId=2)],actual=[])))
        document=dict(evidence=dict(source={'sha256':'fixture'},artifacts=[dict(id='a',locator='http.jsonl')],
            events=events,runs=[dict(id='r',tool='provengo',product_gateway='library-issta-v006')]),findings=[finding])
        fake=types.ModuleType('analyze');fake.analyze_envelope=lambda evidence:document
        with patch.dict(sys.modules,{'analyze':fake}):observations=observations_from_analysis(document)
        self.assertEqual([right],observations[0]['state_witnesses']['non_targets_removed'])
        self.assertEqual(['LIB-ISSTA-BUG-5'],classify(observations)['summary']['known_bug_ids'])
