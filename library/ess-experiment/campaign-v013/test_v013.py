"""Checks for the v013 campaign pieces that need no Provengo run.

    .venv/bin/python -m unittest discover -s library/ess-experiment/campaign-v013 -p test_v013.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
from patch_runtime_v013 import patch, CATALOG_BOUNDARY, normalized  # noqa: E402
from prepare_model_v013 import prepare  # noqa: E402
import sample_coverage_v013 as coverage  # noqa: E402


def rest(method, path, codes, parameters):
    return {'name': method, 'data': {'lib': 'REST', 'method': method, 'url': 'http://127.0.0.1:23243' + path,
                                     'expectedResponseCodes': codes, 'parameters': parameters}}


class PatchTest(unittest.TestCase):
    def test_patch_keeps_catalog_and_adds_matching(self):
        source = (HERE.parent / 'src/StrictGuidedRun.java').read_text(encoding='utf-8')
        patched = patch(source)
        self.assertEqual(patched.split(CATALOG_BOUNDARY)[0], normalized(source).split(CATALOG_BOUNDARY)[0])
        self.assertIn('V013Match.actionName(event)', patched)
        self.assertNotIn('return event.getName();', patched)
        self.assertIn('V011Actuation.evaluate(event)', patched)
        self.assertEqual(patched.count('runScenario('), normalized(source).count('runScenario('))

    def test_patch_rejects_modified_source(self):
        source = (HERE.parent / 'src/StrictGuidedRun.java').read_text(encoding='utf-8')
        with self.assertRaises(RuntimeError):
            patch(source.replace('private static List<Scenario> scenarios1()', 'private static List<Scenario> scenarios1x()'))


class PrepareTest(unittest.TestCase):
    def check(self, profile, stories):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            root.mkdir()
            description = prepare(REPO, root, profile=profile, stories=stories, users=3, books=2, port=23242)
            model = root / 'model'
            stories_text = (model / 'spec/js/lib_stories.js').read_text(encoding='utf-8')
            dal = (model / 'spec/js/dal.js').read_text(encoding='utf-8')
            self.assertIn('const NUMBER_OF_USERS = 3;', stories_text)
            self.assertIn('const NUMBER_OF_BOOKS = 2;', stories_text)
            self.assertEqual('v013PairLoans' in dal, profile == 'contract')
            self.assertEqual("return e.type === 'user-book' && !hasLoanForUser(e.userid) && !hasLoanForBook(e.bookid);" in dal, profile == 'original')
            self.assertEqual('business.borrow' in stories_text, stories == 'business')
            self.assertIn('var port = 23242;', (model / 'data/v013_endpoint.js').read_text(encoding='utf-8'))
            self.assertIn('scenario.max-length: 500', (model / 'config/provengo.yml').read_text(encoding='utf-8'))
            self.assertTrue((root / 'sut_buggy_issta.py').is_file())
            self.assertEqual(json.loads((root / 'model_profile.json').read_text())['profile'], profile)
            self.assertEqual(description['stories'], stories)
            for name in ('lib_stories.js', 'interfaces.library.js', 'dal.js'):
                check = subprocess.run(['node', '--check', str(model / 'spec/js' / name)], capture_output=True, text=True)
                self.assertEqual(check.returncode, 0, check.stderr)

    def test_contract_full(self): self.check('contract', 'full')
    def test_original_business(self): self.check('original', 'business')


class ClassifyTest(unittest.TestCase):
    def test_create_and_reads(self):
        self.assertEqual(coverage.classify(rest('POST', '/books', [201], {'id': 3, 'description': 'Create: Book 3'}))['action'], 'createBook')
        self.assertEqual(coverage.classify(rest('GET', '/books/@{BOOK3}', [200], {'id': 3}))['action'], 'readBookDetail')
        self.assertEqual(coverage.classify(rest('GET', '/loans', [200], {'userId': '@{USER1}', 'bookId': '@{BOOK3}'}))['action'], 'readLoans')
        self.assertEqual(coverage.classify(rest('DELETE', '/loans/@{USER1}/@{BOOK2}', [200], {'userId': 1, 'bookId': 2}))['ids'], {'userId': 1, 'bookId': 2})

    def test_rejection_ids_from_description(self):
        event = coverage.classify(rest('DELETE', '/users/@{USER4}', [400], {'description': 'Verify: delete User 4 is rejected because the operation is not allowed in this state'}))
        self.assertEqual((event['outcome'], event['ids']), ('rejected-400', {'id': 4}))
        event = coverage.classify(rest('DELETE', '/loans/@{USER1}/@{BOOK2}', [404], {'description': 'Verify: delete Loan 1/2 is rejected because the operation is not allowed in this state'}))
        self.assertEqual(event['ids'], {'userId': 1, 'bookId': 2})


class AnalyzeTest(unittest.TestCase):
    def test_triggers(self):
        def ev(method, path, codes, parameters): return coverage.classify(rest(method, path, codes, parameters))
        sample = [ev('POST', '/users', [201], {'id': 1}), ev('POST', '/books', [201], {'id': 1}), ev('POST', '/books', [201], {'id': 2}),
                  ev('POST', '/books', [201], {'id': 3}), ev('POST', '/books', [201], {'id': 4}),
                  ev('GET', '/books/@{BOOK1}', [200], {'id': 1}),
                  ev('POST', '/loans', [201], {'userId': 1, 'bookId': 1}), ev('POST', '/loans', [201], {'userId': 1, 'bookId': 2}),
                  ev('POST', '/loans', [201], {'userId': 1, 'bookId': 3}), ev('POST', '/loans', [201], {'userId': 1, 'bookId': 4}),
                  ev('DELETE', '/users/@{USER1}', [400], {'description': 'Verify: delete User 1 is rejected because x'}),
                  ev('DELETE', '/loans/@{USER1}/@{BOOK1}', [200], {'userId': 1, 'bookId': 1}),
                  ev('POST', '/holds', [201], {'id': 1, 'userId': 1, 'bookId': 1}), ev('POST', '/holds', [201], {'id': 2, 'userId': 1, 'bookId': 2}),
                  ev('DELETE', '/holds/@{HOLD1}', [200], {'id': 1})]
        result = coverage.analyze([sample], 'contract')
        hit = {name for name, v in result['triggers'].items() if v['samples_hit']}
        self.assertTrue(any(n.startswith('ISSTA-1 ') for n in hit), hit)
        self.assertTrue(any(n.startswith('ISSTA-3 ') for n in hit), hit)
        self.assertTrue(any(n.startswith('ISSTA-4 ') for n in hit), hit)
        self.assertTrue(any(n.startswith('ISSTA-5 ') for n in hit), hit)
        self.assertTrue(any(n.startswith('2.4.3 ') for n in hit), hit)
        self.assertFalse(any(n.startswith('ISSTA-2 ') for n in hit), hit)
        self.assertEqual(result['maxima']['loans_per_reader'], 4)
        self.assertEqual(result['degeneracy']['samples_without_loan'], 0)


@unittest.skipUnless(os.environ.get('V013_JAR'), 'set V013_JAR to a Provengo uber JAR to compile the Java adapter')
class JavaCompileTest(unittest.TestCase):
    def test_compiles_and_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'src'; src.mkdir(); classes = Path(tmp) / 'classes'; classes.mkdir()
            (src / 'StrictGuidedRun.java').write_text(patch((HERE.parent / 'src/StrictGuidedRun.java').read_text(encoding='utf-8')), encoding='utf-8')
            for name in ('V013Match.java', 'V013Scenarios.java', 'V013GuidedSuiteHarness.java'):
                shutil.copy2(HERE / name, src / name)
            shutil.copy2(HERE.parent / 'campaign-v011/V011Actuation.java', src / 'V011Actuation.java')
            jar = os.environ['V013_JAR']
            compile_result = subprocess.run(['java', '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-cp', jar, '-d', str(classes), *map(str, src.glob('*.java'))], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            listing = subprocess.run(['java', '-cp', str(classes) + os.pathsep + jar, 'V013GuidedSuiteHarness', 'x', 'y', '1', '--list'], capture_output=True, text=True)
            count = int(next(l for l in listing.stdout.splitlines() if l.startswith('SCENARIO_COUNT=')).split('=')[1])
            self.assertGreaterEqual(count, 542 + 16 + 10 + 20)
            self.assertIn('v013-N-2.4.2', listing.stdout)


if __name__ == '__main__':
    unittest.main()
