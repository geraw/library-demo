import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from classifier import load_catalogs
ROOT=Path(__file__).resolve().parents[1]


class HandoffTests(unittest.TestCase):
    def test_taxonomy_complete_and_drafts_never_activated(self):
        entries,_=load_catalogs(ROOT/'catalogs');rules={e['id']:e for e in entries}
        families=json.loads((ROOT/'TAXONOMY.json').read_text())['families']
        self.assertEqual({'RESPONSE','EDGE-1','RT-1','ATOM-1-2','EDGE-U','KNOWN','CASCADE-1','ADJ','IDEM','VIEW','LINK'},{f['id'] for f in families})
        for family in families:
            for id in family['catalog_ids']:self.assertIn(id,rules)
        self.assertEqual('draft',rules['GEN-TRIGGER-ADJACENCY']['status'])
        self.assertEqual('draft',rules['GEN-CREATE-DUPLICATE']['status'])
        self.assertTrue((ROOT/'HANDOFF_PROMPT_HE.md').is_file())
