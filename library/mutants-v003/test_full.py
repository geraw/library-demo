"""Projection correctness and semantic B2 witness, not native scheduling tests."""
import copy,json,random,tempfile,unittest
from pathlib import Path
from sample_campaign import events_from,materialize
from check_b2_reachability import check_rows
from verify import witness
from replay import replay
HERE=Path(__file__).resolve().parent
class FullTests(unittest.TestCase):
    def test_full_keeps_negative_events_but_projects_them_out(self):
        events=json.loads((HERE/'compact_smoke_events.json').read_text())[0]
        negative={'name':'POST','data':{'url':'http://127.0.0.1/users','body':'{}','expectedResponseCodes':[400],'parameters':{},'model':{'valid':False}}}
        events.insert(0,negative)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.json';p.write_text(json.dumps([events]))
            with self.assertRaises(ValueError):events_from(p)
            full=materialize(events_from(p,allow_negative=True),123,allow_negative=True)
            self.assertEqual(full[0]['status'],400)
            clean=[r for r in full if 200<=r['status']<300 or (r['method']=='GET' and r['status']==404)]
            self.assertEqual(len(clean),13);self.assertEqual(clean[-1]['status'],404)
            for arm in ['original','baseline']:self.assertEqual(replay(clean,arm,Path(d)/'trace.jsonl',456)['status'],'PASS')
    def test_unexpected_original_acceptance_is_not_silently_removed(self):
        e={'name':'POST','data':{'url':'http://127.0.0.1/users','body':'{"name":"A"}','parameters':{'id':1},'expectedResponseCodes':[400]}}
        with self.assertRaises(ValueError):materialize([e],123,allow_negative=True)
    def test_b2_semantic_witness(self):
        random.seed(42);rows=witness('B2','original')
        for i,r in enumerate(rows,1):r.update(url='http://127.0.0.1'+r['path'],order=i,role='tool')
        self.assertEqual(check_rows(rows)['requests'],24)
if __name__=='__main__':unittest.main()
