import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from replay_library import run

class ReplayLibraryTests(unittest.TestCase):
    def test_four_configuration_raw_replay_and_no_source_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runs=root/'runs';contract=root/'contract.json'
            fixture=Path(__file__).parent/'fixtures/step2';contract.write_bytes((fixture/'contract.json').read_bytes())
            raw=json.dumps({'role':'tool','method':'GET','path':'/books','status':200,'response':[],'actor':'A','epoch':1})+'\n'
            for name in ('evomaster','restler','provengo-sample10','provengo-java'):
                folder=runs/'existing'/name/'none';folder.mkdir(parents=True);(folder/'http.jsonl').write_text(raw)
            report=run(runs,contract,root/'output')
            self.assertEqual(len(report['cells']),4);self.assertEqual(report['missing_raw_configurations'],[])
            self.assertTrue(all(c['result']['exit_code']==0 for c in report['cells']))
            self.assertTrue(all(p.read_text()==raw for p in runs.rglob('http.jsonl')))
            self.assertEqual(report['new_SUT_requests'],0)
            with self.assertRaises(ValueError):run(runs,contract,root/'output')

    def test_missing_traces_are_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runs=root/'runs';runs.mkdir();contract=Path(__file__).parent/'fixtures/step2/contract.json'
            report=run(runs,contract,root/'output')
            self.assertEqual(report['status'],'PARTIAL');self.assertEqual(len(report['missing_raw_configurations']),4)

if __name__=='__main__':unittest.main()
