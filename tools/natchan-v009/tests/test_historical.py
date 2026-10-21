import importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('natchan_v009_history',Path(__file__).parents[1]/'historical.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_raw_projection_classified_without_policy_or_known_bug(tmp_path):
 import json
 path=tmp_path/'gateway-journal.jsonl'
 path.write_text(json.dumps(dict(category='reference-check',sent=[1],stored=[],readback_status=200,status=201,verdict='ok'))+'\n')
 r=m.analyze([path]);assert r['pattern_occurrences']=={'GEN-REFERENCE-PROJECTION-DIFFERENCE':1}
 assert all(not a.get('known_bugs') for a in r['assessments'])
 assert r['historical_coverage'][0]['semantic_status']=='not_evaluable'
def test_duplicate_archives_not_double_counted(tmp_path):
 import json
 body=json.dumps(dict(category='known-failure',status=500,attempt=1,known_failure='Anything'))+'\n'
 a=tmp_path/'a.jsonl';b=tmp_path/'b.jsonl';a.write_text(body);b.write_text(body)
 r=m.analyze([a,b]);assert r['distinct_journals']==1
 assert r['pattern_occurrences']=={'GEN-SERVER_ERROR':1}
