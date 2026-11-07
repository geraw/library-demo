import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
s=importlib.util.spec_from_file_location('report_audit',Path(__file__).parents[1]/'audit_report.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
@pytest.fixture(scope='module')
def audit():
 g=ROOT/'natchan-history/family-coverage/results/gitea-g005-home-20261020'
 v=ROOT/'natchan-history/family-coverage/results/check-v164-work-20261018/evidence/v164-triggers-20261018-153232-redacted.zip'
 b=ROOT/'natchan-history/report-corrections/results/compare-v153-20261017'
 if not all(p.exists() for p in (g,v,b)):pytest.skip('Private original evidence required')
 return dict(g005=m.g005(g),adj=m.adjacency(v),baselines=m.baselines(b))
def test_noop_version_has_concrete_versions(audit):
 rows=audit['g005']['noop_version_observations'];assert len(rows)==12
 assert all(r['version_before']==6 and r['version_after']==7 and r['statuses']==[201,409] for r in rows)
def test_length_is_not_claimed_exact_boundary(audit):
 rows=audit['g005']['undeclared_length_observations'];assert len(rows)==12
 assert all(not r['maxLength_declared'] and not r['exact_limit_verified'] for r in rows)
def test_adj_sources_and_distinct_matching_levels(audit):
 rows=audit['adj'];assert len(rows)==6 and {r['product'] for r in rows}=={'vikunja'}
 assert sum(r['unique_log_match'] for r in rows)==5
 assert all(r['grouped_lock_evidence'] for r in rows)
def test_evomaster_triggered_vs_reported(audit):
 rows=[r for r in audit['baselines'] if r['tool']=='EvoMaster'];assert len(rows)==3
 assert all(r['lock_log_count']==1 and r['replay_500_became_401'] and not r['has_native_500_fault_code_100'] for r in rows)
 assert all(r['native_fault_entries']>r['native_fault_total_field']>0 for r in rows)
def test_schemathesis_native_label_witness(audit):
 rows=[r for r in audit['baselines'] if r['tool']=='Schemathesis'];assert len(rows)==3
 assert all(r['known_signature']=='VIK-F02' and r['label_title_empty_201'] and r['declared_minLength_1'] and r['missing_body_reported'] for r in rows)
