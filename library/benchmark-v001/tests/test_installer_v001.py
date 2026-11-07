"""Installer regression checks using real subprocesses, without downloads."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('benchmark_installer', Path(__file__).resolve().parents[1] / 'vendor/bootstrap_native_v001.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class InstallerTest(unittest.TestCase):
    def test_uses_running_python_despite_broken_legacy_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            broken = home / 'restler-python/Scripts/python.exe'
            broken.parent.mkdir(parents=True)
            broken.write_bytes(b'broken')
            selected = installer.restler_python(home)
            self.assertEqual(selected, Path(sys.executable))
            self.assertIn(str(selected), (home / 'restler-python-check.log').read_text())
            self.assertEqual(broken.read_bytes(), b'broken')
            self.assertFalse(list(home.glob('restler-python-repaired-*')))

if __name__ == '__main__':
    unittest.main()
