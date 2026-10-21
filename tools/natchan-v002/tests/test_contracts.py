import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts import GatewayContract, describe_contract, evidence_availability
from gateways import TOOLS, PRODUCTS, select, RecordedToolGateway, OpaqueProductGateway
from evidence import ingest


class ContractsTests(unittest.TestCase):
    def test_registry_has_versioned_independent_contracts(self):
        for dimension, registry in [('tool', TOOLS), ('product', PRODUCTS)]:
            for name, gateway in registry.items():
                value=describe_contract(gateway,dimension)
                self.assertEqual(name,value['id'])
                self.assertEqual('natchan-gateway/1',value['api_version'])
                self.assertIsInstance(value['limitations'],list)

    def test_all_current_combinations(self):
        for tool in TOOLS:
            for product in PRODUCTS:
                a,b=select({'tool_gateway':tool,'product_gateway':product})
                self.assertEqual(tool,a.id)
                self.assertEqual(product,b.id)

    def test_undeclared_or_wrong_dimension_rejected(self):
        class Undeclared:
            id='bad'
            def normalize(self,label,record): return {}
        with patch.dict(TOOLS,{'bad':Undeclared()}):
            with self.assertRaisesRegex(ValueError,'declare'): select({'tool_gateway':'bad'})
        class Wrong(RecordedToolGateway):
            contract=GatewayContract('product',())
        with patch.dict(TOOLS,{'bad':Wrong()}):
            with self.assertRaisesRegex(ValueError,'dimension'): select({'tool_gateway':'bad'})

    def test_missing_required_artifact_is_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'a.zip'
            with zipfile.ZipFile(path,'w'): pass
            result=ingest(path,{'schema_version':1,'runs':[dict(id='r',tool='provengo',system='other',tool_gateway='provengo-fixed-java-v011',artifacts={})]})
            self.assertEqual('incomplete',result['runs'][0]['status'])
            self.assertEqual('native_jsonl',result['issues'][0]['detail']['label'])

    def test_invalid_plugin_output_preserves_source_payload(self):
        class Invalid(RecordedToolGateway):
            def normalize(self,label,record): return {'id':'overwrite-core'}
        with tempfile.TemporaryDirectory() as folder,patch.dict(TOOLS,{'bad':Invalid()}):
            path=Path(folder)/'a.zip'
            with zipfile.ZipFile(path,'w') as z: z.writestr('trace.jsonl','{"status":500}')
            r=ingest(path,{'schema_version':1,'runs':[dict(id='r',tool='x',system='x',tool_gateway='bad',artifacts={'trace':'trace.jsonl'})]})
            self.assertEqual('e1',r['events'][0]['id'])
            self.assertEqual(500,r['events'][0]['payload']['status'])
            self.assertEqual('gateway_record_error',r['issues'][0]['code'])
            self.assertEqual('incomplete',r['status'])

    def test_evidence_presence_is_not_correctness(self):
        value=evidence_availability({'method':'GET','path':'/books/1','status':404},'http')
        self.assertEqual(['response'],value['missing'])
        self.assertEqual('partial',value['status'])
        value=evidence_availability({'method':'GET','path':'/books/1','status':404,'response':None},'http')
        self.assertEqual('recorded',value['status'])
        self.assertNotIn('verdict',value)

    def test_native_boolean_without_case_is_not_interpreted(self):
        e=TOOLS['provengo-fixed-java-v011'].normalize('native_jsonl',{'native_pass':False})
        self.assertEqual('not_evaluated',e['native_interpretation'])
