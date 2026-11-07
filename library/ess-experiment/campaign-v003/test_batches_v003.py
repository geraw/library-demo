import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from campaign_v003 import batched_sample


class Batches(unittest.TestCase):
    def test_hundred_cases_keep_native_file_ids(self):
        calls = []
        def fake(args, log, timeout=None):
            calls.append(args)
            count = int(args[args.index('--size') + 1])
            output = Path(args[args.index('-o') + 1])
            output.write_text(json.dumps({'scenarios': [
                {'events': [len(calls), n]} for n in range(count)]}))
            return {'exit_code': 0, 'wall_seconds': 2.0}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('campaign_v003.command', side_effect=fake):
                sources, outcome = batched_sample('java', 'jar', root, root, 100, '--max-length', 5)
            self.assertEqual(len(calls), 20)
            self.assertEqual(len(sources), 100)
            self.assertEqual([i for _, i in sources[:7]], [1, 2, 3, 4, 5, 1, 2])
            self.assertEqual(outcome['wall_seconds'], 40.0)
            self.assertTrue(all('-Xmx2g' in args for args in calls))
            self.assertTrue(json.loads((root / 'sampling.json').read_text())['complete'])

    def test_failed_batch_does_not_publish_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('campaign_v003.command', return_value={'exit_code': 1, 'wall_seconds': 3.0}):
                with self.assertRaises(RuntimeError):
                    batched_sample('java', 'jar', root, root, 100, '--max-length', 5)
            self.assertFalse((root / 'budget.json').exists())
            self.assertFalse(json.loads((root / 'sampling.json').read_text())['complete'])
