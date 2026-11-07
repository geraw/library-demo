from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_mealie import unresolved_writes


class MealieTests(unittest.TestCase):
    def test_other_target_failed_write_does_not_confound(self):
        saved={'before':{},'other_list_add_a':{'operation':'POST /lists','code':500},'after':{},'list_b':{'body':{'id':'B'}}}
        self.assertEqual([],unresolved_writes(saved,['before','other_list_add_a','after'],'before','after','A'))
        self.assertEqual(['other_list_add_a'],unresolved_writes(saved,['before','other_list_add_a','after'],'before','after','B'))

    def test_missing_target_is_unknown(self):
        saved={'before':{},'other_list_add_a':{'operation':'POST /lists','code':500},'after':{}}
        self.assertEqual(['other_list_add_a'],unresolved_writes(saved,['before','other_list_add_a','after'],'before','after','A'))
