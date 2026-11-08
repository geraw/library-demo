import copy,json,tempfile,unittest
from pathlib import Path
from sample_campaign import events_from,materialize,archive_case
from replay import replay
HERE=Path(__file__).resolve().parent
class CompactTests(unittest.TestCase):
    def test_symbolic_sample_materializes_and_replays_on_controls(self):
        events=events_from(HERE/'compact_smoke_events.json')
        rows=materialize(events,123)
        self.assertEqual(len(rows),13)
        self.assertEqual(rows[-1]['status'],404)
        with tempfile.TemporaryDirectory() as d:
            for arm in ['original','baseline']:
                self.assertEqual(replay(rows,arm,Path(d)/'trace.jsonl',456)['status'],'PASS')
    def test_negative_fields_and_callbacks_rejected(self):
        good=json.loads((HERE/'compact_smoke_events.json').read_text())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.json'
            for change in ['negative','callback']:
                bad=copy.deepcopy(good)
                if change=='negative':bad[0][0]['data']['expectedResponseCodes']=[400]
                else:bad[0][0]['data']['callback']={'object':'serialized'}
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):events_from(p)
    def test_unbound_symbol_rejected(self):
        e=events_from(HERE/'compact_smoke_events.json')
        e[0]['data']['url']='http://127.0.0.1/books/@{BOOK999}'
        with self.assertRaises(ValueError):materialize(e,123)
    def test_archive_matches_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);work=root/'work';work.mkdir();(work/'x.json').write_text('{}')
            archive_case(work,root/'archive')
            self.assertEqual((root/'archive/x.json').read_text(),'{}')
            self.assertTrue((root/'archive/archive-verified.json').exists())
if __name__=='__main__':unittest.main()
