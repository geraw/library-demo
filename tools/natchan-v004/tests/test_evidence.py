import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from analyze import gitea_observations, vikunja_observations, log_links, summarize_oracles, compare_fields
from classifier import classify


def run(product='vikunja'):
    return dict(id='test',product=product,version='2.7.0' if product=='vikunja' else '28.1.0',tool='test',source={'file':'fixture','sha256':'fixture'})


def contract():
    schema={'properties':{'hex_color':{'type':'string','maxLength':7},'title':{'type':'string'}}}
    op={'parameters':[{'in':'body','schema':schema}]}
    return {'paths':{'/labels':{'put':op},'/labels/{id}':{'put':op,'get':{}},'/projects/{id}/shares':{'put':op}}}


class EvidenceTests(unittest.TestCase):
    def test_truncation_with_unicode_ellipsis(self):
        obs={'facts':{},'witnesses':[]}
        compare_fields(obs,{'title':'L'*10000},{'title':'L'*252+'\u2026'},['title'],{'record':1})
        self.assertTrue(obs['facts']['field_changes']['title']['truncated'])

    def test_imported_verdict_cannot_manufacture_silent_change(self):
        rows=[{'method':'PUT','path':'/labels','body':{'hex_color':'ABCDEF1'},'status':201,'response':{'id':4,'hex_color':'ABCDEF'},'verdict':'silently_changed'}]
        obs,_=vikunja_observations(run(),{'records':rows},contract())
        self.assertNotIn('silent_change',obs[0]['facts'])

    def test_real_readback_finds_truncation(self):
        rows=[{'method':'PUT','path':'/labels','body':{'hex_color':'ABCDEF1'},'status':201,'response':{'id':4}},
              {'method':'GET','path':'/labels/4','status':200,'response':{'hex_color':'ABCDEF'}}]
        obs,_=vikunja_observations(run(),{'records':rows},contract())
        report=classify(obs,ROOT/'catalogs')
        self.assertIn('VIK-F05',report['summary']['known_bug_ids'])

    def test_other_resource_not_a_readback(self):
        rows=[{'method':'PUT','path':'/labels','body':{'hex_color':'ABCDEF1'},'status':201,'response':{'id':4}},
              {'method':'GET','path':'/labels/5','status':200,'response':{'hex_color':'ABCDEF'}}]
        obs,_=vikunja_observations(run(),{'records':rows},contract())
        self.assertNotIn('silent_change',obs[0]['facts'])

    def test_intervening_write_blocks_readback(self):
        rows=[{'method':'PUT','path':'/labels','body':{'hex_color':'ABCDEF1'},'status':201,'response':{'id':4}},
              {'method':'POST','path':'/labels/4','body':{'hex_color':'ABCDEF'},'status':200},
              {'method':'GET','path':'/labels/4','status':200,'response':{'hex_color':'ABCDEF'}}]
        obs,_=vikunja_observations(run(),{'records':rows},contract())
        self.assertNotIn('silent_change',obs[0]['facts'])

    def test_unicode_password_counts_bytes(self):
        row={'method':'PUT','path':'/projects/1/shares','body':{'password':'ש'*40},'status':500}
        obs,_=vikunja_observations(run(),{'records':[row]},contract())
        self.assertEqual(obs[0]['facts']['password_byte_lower_bound'],80)
        self.assertIn('VIK-F06',classify(obs,ROOT/'catalogs')['summary']['known_bug_ids'])

    def test_redacted_password_is_lower_bound_not_reconstructed(self):
        row={'method':'PUT','path':'/projects/1/shares','body':{'password':'<40 chars>'},'status':500}
        obs,_=vikunja_observations(run(),{'records':[row]},contract())
        self.assertNotIn('VIK-F06',classify(obs,ROOT/'catalogs')['summary']['known_bug_ids'])

    def test_wrong_version_does_not_match_known_bug(self):
        row={'method':'PUT','path':'/projects/1/shares','body':{'password':'x'*73},'status':500}
        r=run();r['version']='unverified'
        obs,_=vikunja_observations(r,{'records':[row]},contract())
        self.assertNotIn('VIK-F06',classify(obs,ROOT/'catalogs')['summary']['known_bug_ids'])

    def test_original_atom_verdict_recomputed_from_states_but_kept_separate(self):
        record={'source':{'file':'archive.zip'},'category':'atomicity-check','payload':{'kind':'update','fields':{'body':'applied','assignee':'kept'},'verdict':'rolled_back'}}
        summary=summarize_oracles([record]);group=next(iter(summary.values()))
        self.assertEqual(group['atomicity_from_recorded_field_states'],{'partial':1})
        self.assertEqual(group['atomicity_verdict_disagreements'],1)

    def test_unique_log_join(self):
        row={'category':'research','method':'PATCH','path':'/x/1','status':500,'t_utc':'2026-10-21T10:00:00+00:00'}
        log='2026/10/21 10:00:00 x [E] user does not exist\n2026/10/21 10:00:00 HTTPRequest completed PATCH /api/v1/x/1 for host, 500 Internal Server Error'
        self.assertIn(0,log_links([row],log))
        self.assertEqual(log_links([row,row],log),{})

    def test_generic_500_cannot_identify_root_cause(self):
        row={'category':'research','method':'PATCH','path':'/issues/1','status':500,'input':{},'response':'{}'}
        data={'records':[row],'ir':{'entities':[]},'sut_log':''}
        obs,_=gitea_observations(run('gitea'),data)
        self.assertEqual(classify(obs,ROOT/'catalogs')['summary']['known_bug_ids'],[])

    def test_deleted_share_success_requires_prior_absence(self):
        row={'method':'DELETE','path':'/projects/1/shares/999','status':200}
        obs,_=vikunja_observations(run(),{'records':[row]},contract())
        self.assertNotIn('delete_absent_share_success',obs[0]['facts'])


if __name__=='__main__':unittest.main()
