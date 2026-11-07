import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('split', Path(__file__).with_name('split_v005.py'))
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)

class Routing(unittest.TestCase):
    def test_two_arms_budgets_and_completed_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            root.mkdir()
            (root / 'sampling.json').write_text(json.dumps({'wall_seconds': 10.2}))
            calls = []
            def replay(java, jar, target, sample, size, name, bugs):
                calls.append((name, bugs, size))
                (target / name).mkdir()
                return {'wall_seconds': 20.1}
            with patch.object(split, 'inputs', return_value=(Path('jar'), [('sample', 1)])), patch.object(split.core, 'replay', side_effect=replay):
                args = SimpleNamespace(campaign=root, java='java')
                split.replay(args)
                split.replay(args)
            self.assertEqual(calls, [('split-v005-business-four', '1,2,3,5', 1), ('split-v005-book-read-one', '4', 1)])
            for arm in split.ARMS:
                budget = json.loads((root / ('split-v005-' + arm) / 'budget.json').read_text())
                self.assertEqual(budget['baseline_search_budget_seconds'], 31)

if __name__ == '__main__':
    unittest.main()
