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
    def test_b2_campaign_accepts_complete_events_without_log_marker(self):
        from argparse import Namespace
        from unittest.mock import patch
        import shutil
        from sample_campaign import main
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);jar=root/'fake.jar';jar.write_bytes(b'fake')
            def fake_launch(command,folder,name,timeout):
                (folder/(name+'.log')).write_text('--max-length --seed' if name=='help' else '')
                if name=='sample':shutil.copyfile(HERE/'b2-witness-events.json',command[command.index('-o')+1])
            args=Namespace(jar=jar,java='fake',count=1,max_length=2000,seed=10001,timeout=30,
                model='full',b2_witness=True,resume=None,work_base=root/'work',output_base=root/'out')
            with patch('sample_campaign.launch',side_effect=fake_launch):main(args)
            run=next((root/'out').iterdir())
            summary=json.loads((run/'summary.json').read_text())['case-001']
            self.assertFalse(summary['b2_guide_log_marker'])
            self.assertEqual(summary['arms']['B2']['status'],'DIFFERENT')
            self.assertEqual(summary['arms']['original']['status'],'PASS')
            self.assertEqual(summary['arms']['baseline']['status'],'PASS')
            self.assertTrue((run/'completed.json').exists())
if __name__=='__main__':unittest.main()
