import importlib.util
import io
import json
from pathlib import Path
import zipfile
s=importlib.util.spec_from_file_location('family_audit',Path(__file__).parents[1]/'family_audit.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_projected_ids_ignore_verdict():
 r=m.analyze_rows([dict(category='reference-check',sent=[1],stored=[2],readback_status=200,status=201,verdict='ok')],[])
 assert r['observations'][0]['facts']['ids_equal'] is False
 assert r['observations'][0]['evidence_level']=='recomputed-from-projected-ids'
def test_missing_readback_not_negative():
 r=m.analyze_rows([dict(category='link2-check',sent=[1],listed=[],status=200,verdict='ok')],[])
 assert r['counts']=={'LINK-2:incomplete-projection':1}
def test_idem_different_payload_rejected():
 rows=[dict(action='idem_write',case_id='x',logical_id='a',method='PATCH',path='/a',input={'x':v},status=200) for v in [1,2]]
 assert m.analyze_rows(rows,[])['counts']=={'IDEM:unqualified-pair':1}
def test_ambiguous_idem_not_stitched():
 r=dict(action='idem_write',case_id='x',logical_id='a',method='PATCH',path='/a',input={},status=200)
 assert m.analyze_rows([r,r,r],[])['counts']=={'IDEM:ambiguous-pair':1}
def test_cascade_different_path_unknown():
 rows=[dict(action='cascade_delete',method='DELETE',path='/parent/1',session='A',status=204),dict(action='cascade_verify',method='GET',path='/child/2',session='A',status=200)]
 assert m.analyze_rows(rows,[])['counts']=={'CASCADE-1:unresolved-relationship':1}
def test_edge_same_value_status_only():
 rows=[dict(action='edge_create',logical_id='Issue_EDGE_title_long',input={'title':'x'},status=201),dict(action='edge_update',logical_id='Issue_EDGEU_title_long',input={'title':'x'},status=500)]
 r=m.analyze_rows(rows,[])['observations'][0]
 assert r['facts']['response_class_differs'] is True
 assert r['evidence_level']=='same-field-value-status-comparison'
def test_nested_zip_scoped_and_bounded():
 def archive(name,body):
  f=io.BytesIO()
  with zipfile.ZipFile(f,'w') as z:z.writestr(name,body)
  return f.getvalue()
 raw=archive('inner.zip',archive('gateway-journal.jsonl',b'{"category":"research"}\n'))
 assert len(list(m.journals(raw,[],[10000])))==1
 try:list(m.journals(raw,[],[1]))
 except ValueError:pass
 else:raise AssertionError('Missing expansion limit')
