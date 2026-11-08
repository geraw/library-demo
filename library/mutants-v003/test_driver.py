"""Campaign orchestration tests use a fake CLI, not a native Provengo run."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
@unittest.skipIf(os.name=='nt','Local Unix fake-CLI harness; native Windows checked by first-sample gate')
class DriverTests(unittest.TestCase):
    def test_campaign_and_resume_preserve_partial_case(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);jar=p/'dummy.jar';jar.write_bytes(b'fake')
            fake=p/'fake-java'
            fake.write_text('#!'+sys.executable+'\nimport sys,shutil\n'
                "if '-h' in sys.argv: print('--max-length --seed'); raise SystemExit(0)\n"
                'shutil.copyfile('+repr(str(HERE/'compact_smoke_events.json'))+",sys.argv[sys.argv.index('-o')+1])\n")
            fake.chmod(0o755)
            command=[sys.executable,str(HERE/'sample_campaign.py'),'--jar',str(jar),'--java',str(fake),'--count','2','--work-base',str(p/'work'),'--output-base',str(p/'out')]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            root=next((p/'out').iterdir());config=json.loads((root/'campaign.json').read_text());work=Path(config['work_root'])
            self.assertEqual(json.loads((root/'completed.json').read_text())['cases'],2)
            self.assertIn('FIRST_SAMPLE_CONTROL_GATE_PASSED',result.stdout)
            (root/'case-002/completed.json').unlink()
            partial=work/'case-002';partial.mkdir();(partial/'keep.txt').write_text('preserve me')
            result=subprocess.run(command+['--resume',str(root)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue(list((root/'incomplete').glob('case-002-*')))
            self.assertEqual(next((work/'incomplete').glob('case-002-*/keep.txt')).read_text(),'preserve me')
            self.assertEqual(json.loads((root/'completed.json').read_text())['cases'],2)
if __name__=='__main__':unittest.main()
