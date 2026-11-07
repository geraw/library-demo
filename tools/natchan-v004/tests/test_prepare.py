import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_evidence import prepare


class ExportTests(unittest.TestCase):
    def test_pinned_git_export_preserves_exact_bytes_and_checks_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';repo.mkdir()
            subprocess.run(['git','init','-q',str(repo)],check=True)
            raw=b'{"transcript":[]}\r\n'
            (repo/'raw.json').write_bytes(raw)
            subprocess.run(['git','-C',str(repo),'add','raw.json'],check=True)
            subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
            commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
            manifest=root/'manifest.json'
            document={'commit':commit,'runs':[{'path':'raw.json','sha256':hashlib.sha256(raw).hexdigest()}]}
            manifest.write_text(json.dumps(document))
            prepare(repo,manifest,root/'export')
            self.assertEqual((root/'export/raw.json').read_bytes(),raw)
            with self.assertRaises(ValueError):prepare(repo,manifest,root/'export')
            document['runs'][0]['sha256']='0'*64;manifest.write_text(json.dumps(document))
            with self.assertRaises(ValueError):prepare(repo,manifest,root/'wrong')
