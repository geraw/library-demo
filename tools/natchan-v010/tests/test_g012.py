import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
s=importlib.util.spec_from_file_location('g012_analysis',Path(__file__).parents[1]/'analyze_g012.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
ARCHIVE=ROOT/'upload/g012-gitea-variants-20261021-203735.zip'
@pytest.fixture(scope='module')
def report():
 if not ARCHIVE.exists():pytest.skip('Private original archive required')
 return m.analyze(ARCHIVE)
def test_complete_raw_count_parity(report):
 assert len(report['runs'])==16
 assert sum(r['http_requests'] for r in report['runs'])==7501
 assert sum(r['http_5xx'] for r in report['runs'])==83
 assert sum(r['correlated_5xx'] for r in report['runs'])==83
def test_native_failures_not_wrapper_success(report):
 rr=[r for r in report['runs'] if r['model']=='g009']
 assert len(rr)==8 and all(r['native_exit']==1 and r['status']=='STOPPED_AT_FIRST_FAILURE' for r in rr)
 assert all(r['native_exit']==0 and r['native_success_marker'] for r in report['runs'] if r['model']=='g003')
def test_nightly_never_silently_becomes_supported_version(report):
 assert all(not r['strict_catalog_known_occurrences'] for r in report['runs'] if r['variant']=='nightly')
 assert report['nightly_behavioral_analogs_outside_catalog_versions']['GIT-C8']==4
def test_postgres_new_failure_payloads_and_logs(report):
 errors=report['error_evidence']
 nul=[e for e in errors if e['cause']=='postgres_nul'];length=[e for e in errors if e['cause']=='postgres_varchar_limit']
 assert len(nul)==27 and all(e['nul_fields'] for e in nul)
 assert len(length)==8 and all(10000 in e['long_fields'].values() for e in length)
def test_c7_now_has_native_provengo_run_evidence(report):
 rr=[r for r in report['runs'] if r['variant']=='postgres' and r['model']=='g003']
 assert sum(r['strict_catalog_known_occurrences'].get('GIT-C7',0) for r in rr)==4
def test_atom_field_measurements_are_not_full_snapshots(report):
 records=report['atomicity_field_measurements']
 assert len(records)==31 and all(not a['full_state_independently_verified'] for a in records)
 assert sum(a['recomputed_from_field_measurements']=='partial' for a in records)==23
 assert sum(a['recomputed_from_field_measurements']=='rolled_back' for a in records)==8
def test_sqlite_matching_uses_original_payload(report):
 folder=ROOT/'natchan-history/coverage/results/gitea-g003-work-20261021'
 if not folder.exists():pytest.skip('Private SQLite baseline required')
 pairs=m.compare_sqlite(report,ARCHIVE,folder)
 assert len(pairs)==35 and all(len(p['sqlite_matches'])==1 for p in pairs)
 assert sum(p['sqlite_matches'][0]['status'] in (200,201) for p in pairs)==33
