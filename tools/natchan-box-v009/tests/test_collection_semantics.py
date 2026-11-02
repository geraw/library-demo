import io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contract_context import derive
from traffic import normalize
from judge import analyze

class CollectionTests(unittest.TestCase):
    def analyze(self,rows,doc=None):
        doc=doc or json.loads((Path(__file__).parent/'fixtures/step2/contract.json').read_text())
        normalized=[normalize(dict(r,actor='A',epoch=1),{'line_1based':i+1}) for i,r in enumerate(rows)]
        out=io.StringIO();result=analyze(normalized,derive(doc,'fixture'),out,capture={'complete':True,'exclusive':True,'ordering':'serial'})
        return [json.loads(l) for l in out.getvalue().splitlines()],result

    def test_filter_compound_violation_and_valid_control(self):
        for book,value in [(2,'consistent'),(3,'violation')]:
            v,_=self.analyze([{'method':'GET','path':'/loans?userId=1&bookId=2','status':200,'response':[{'id':1,'userId':1,'bookId':book}]}])
            self.assertEqual([x['value'] for x in v if x['property']=='S6'],[value])

    def test_duplicate_or_unknown_filter_abstains(self):
        for query in ['userId=1&userId=2','page=1','bookId=bad']:
            v,_=self.analyze([{'method':'GET','path':'/loans?'+query,'status':200,'response':[{'id':1,'userId':3,'bookId':3}]}])
            self.assertEqual([x['value'] for x in v if x['property']=='S6'],['not_evaluable'])

    def test_collateral_delete_requires_complete_collection_for_violation(self):
        rows=[{'method':'GET','path':'/holds','status':200,'response':[{'id':1},{'id':2}]},
              {'method':'DELETE','path':'/holds/1','status':204},
              {'method':'GET','path':'/holds','status':200,'response':[]}]
        doc=json.loads((Path(__file__).parent/'fixtures/step2/contract.json').read_text())
        for complete,value in [(False,'policy_observation'),(True,'violation')]:
            if complete:doc['paths']['/holds']['get']['description']='Return all holds.'
            v,_=self.analyze(rows,doc)
            self.assertEqual([x['value'] for x in v if x['reason']=='DELETE_REMOVED_NON_TARGET_RESOURCES'],[value])

    def test_missing_delete_readback_included_in_coverage(self):
        v,a=self.analyze([{'method':'GET','path':'/holds','status':200,'response':[{'id':1},{'id':2}]},
                          {'method':'DELETE','path':'/holds/1','status':204}])
        self.assertEqual(a['classes']['S4']['counts']['not_evaluable'],1)
        self.assertIn('DELETE_COLLECTION_READBACK_NOT_RETAINED',[x['reason'] for x in v])

if __name__=='__main__':unittest.main()
