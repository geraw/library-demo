import io
import json
from pathlib import Path
import sys
import zipfile
import unittest
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence import ingest, Limits
from gateways import RecordedToolGateway, OpaqueProductGateway, TOOLS, PRODUCTS


def archive(tmp_path, members):
    path=tmp_path/'evidence.zip'
    with zipfile.ZipFile(path,'w') as z:
        for name,data in members:
            z.writestr(name,data)
    return path


def manifest(**kw):
    return {'schema_version':1,'runs':[dict(id='r',tool='future',system='future',artifacts={'trace':'trace.jsonl'},**kw)]}


def test_independent_gateways_and_exact_source(tmp_path):
    p=archive(tmp_path,[('trace.jsonl',json.dumps({'method':'GET','path':'/books/7','status':404})+'\n')])
    r=ingest(p,manifest(product_gateway='library-issta-v006'))
    e=r['events'][0]
    assert e['gateway']=='recorded-json-v1'
    assert e['product']['entities']==[{'resource':'books','path_id':'7'}]
    assert e['scope']['basis']=='unknown'
    assert e['source']['line']==1 and r['findings']==[] and r['summary']['finding_count'] is None
    assert r['artifacts'][0]['sha256']


def test_custom_tool_and_custom_product_independent(tmp_path):
    class ExtraTool(RecordedToolGateway):
        def normalize(self,label,record):
            return dict(super().normalize(label,record),extra_tool=True)
    class ExtraProduct(OpaqueProductGateway):
        def describe(self,record):
            return dict(super().describe(record),extra_product=True)
    tools_patch=patch.dict(TOOLS,{'extra':ExtraTool()}); tools_patch.start()
    products_patch=patch.dict(PRODUCTS,{'extra':ExtraProduct()}); products_patch.start()
    p=archive(tmp_path,[('trace.jsonl','{"method":"GET","path":"/a"}')])
    r=ingest(p,manifest(tool_gateway='extra',product_gateway='extra'))
    assert r['events'][0]['extra_tool'] and r['events'][0]['product']['extra_product']
    tools_patch.stop(); products_patch.stop()


def test_invalid_record_breaks_scope_and_claim_is_not_finding(tmp_path):
    p=archive(tmp_path,[('trace.jsonl','{"role":"boundary","case":1}\nBROKEN\n{"method":"GET","path":"/books/1"}\n{"role":"verdict","bug":4}')])
    r=ingest(p,manifest())
    assert r['status']=='incomplete'
    assert r['events'][1]['scope']['basis']=='unknown'
    assert r['events'][2]['kind']=='imported_claim'
    assert not r['findings']


def test_conflicting_case(tmp_path):
    p=archive(tmp_path,[('trace.jsonl','{"role":"boundary","case":1}\n{"role":"tool","case":2}')])
    assert ingest(p,manifest())['events'][1]['scope']['basis']=='conflicting'


def test_missing_and_unsupported_gateway(tmp_path):
    p=archive(tmp_path,[])
    assert ingest(p,manifest())['runs'][0]['status']=='incomplete'
    with unittest.TestCase().assertRaisesRegex(ValueError,'Unsupported gateway'):
        ingest(p,manifest(tool_gateway='does-not-exist'))


def test_utf16_and_bomless(tmp_path):
    text='{"method":"GET","path":"/a"}\n'
    for encoding in ('utf-16','utf-16-le','utf-8-sig'):
        p=archive(tmp_path,[('trace.jsonl',text.encode(encoding))])
        assert len(ingest(p,manifest())['events'])==1


def test_duplicate_and_traversal_not_consumed(tmp_path):
    p=archive(tmp_path,[('trace.jsonl','{}'),('trace.jsonl','{}'),('../escape','secret')])
    r=ingest(p,manifest())
    assert not r['events']
    assert {'duplicate_member','unsafe_member_name'}<={i['code'] for i in r['issues']}
    assert not (tmp_path.parent/'escape').exists()


def test_nested_zip_budget_and_member_limit(tmp_path):
    inner=io.BytesIO()
    with zipfile.ZipFile(inner,'w') as z:z.writestr('trace.jsonl','{}')
    p=archive(tmp_path,[('inner.zip',inner.getvalue())])
    m=manifest();m['runs'][0]['artifacts']['trace']='inner.zip!/trace.jsonl'
    assert len(ingest(p,m)['events'])==1
    assert ingest(p,m,Limits(max_depth=0))['status']=='incomplete'
    assert ingest(p,m,Limits(max_member_bytes=1))['status']=='incomplete'
    assert ingest(p,m,Limits(max_total_bytes=1))['status']=='incomplete'
    assert ingest(p,m,Limits(max_members=0))['status']=='incomplete'


def test_empty_inventory_is_not_analysis(tmp_path):
    p=archive(tmp_path,[])
    assert ingest(p)['status']=='incomplete'


def test_partial_library_not_complete(tmp_path):
    p=archive(tmp_path,[('completed.json','{"complete":true,"scenario_count":542}')])
    r=ingest(p,library=True)
    assert len(r['runs'])==3 and all(x['status']=='incomplete' for x in r['runs'])


def test_event_limit(tmp_path):
    p=archive(tmp_path,[('trace.jsonl','{}\n{}')])
    r=ingest(p,manifest(),Limits(max_events=1))
    assert len(r['events'])==1 and r['status']=='incomplete'


class EvidenceTests(unittest.TestCase):
    pass


def wrap(function):
    def test(self):
        with tempfile.TemporaryDirectory() as directory:
            function(Path(directory))
    return test


for name,function in list(globals().items()):
    if name.startswith("test_") and callable(function):
        setattr(EvidenceTests,name,wrap(function))


if __name__ == "__main__":
    unittest.main()
