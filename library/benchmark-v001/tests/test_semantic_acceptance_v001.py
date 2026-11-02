"""Live in-process acceptance: frozen SUT code, actual exchanges, independent judge.
No expected mutation label is passed to the analyzer. Each trigger also runs on
baseline; an extra collection read supplies the B3 preimage explicitly.
"""
import io,json,sys,unittest
from pathlib import Path
import test_benchmark_v001 as benchmark
Exchange=benchmark.Exchange
ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT.parents[1]/'tools/natchan-box-v009'
sys.path.insert(0,str(ENGINE))
from contract_context import derive
from common import digest
from traffic import normalize
from judge import analyze as semantic_analyze


class SemanticAcceptance(unittest.TestCase):
    capture = benchmark.BenchmarkTest.capture
    # Inherit only the capture fixture, not the parent's whole test matrix.
    def check_flow(self, mutation, kind):
        def scenario(c):
            x=Exchange(c)
            if kind in ('B1','B2'):
                b=x.book('acceptance')
                if kind=='B2':x.req('DELETE','/books/'+str(b))
                x.req('GET','/books/'+str(b))
            else:
                u=x.user('a');v=x.user('b');b=x.book('acceptance')
                x.create('/loans',{'userId':u,'bookId':b})
                x.req('GET','/loans')
                x.req('POST','/loans',{'userId':v,'bookId':b})
                x.req('GET','/loans')
        _,rows=self.capture(mutation,scenario)
        cb=(ROOT/'openapi.json').read_bytes();context=derive(json.loads(cb),digest(cb));out=io.StringIO()
        normalized=[normalize(r,{'line_1based':i+1,'sha256':'in-process-capture'}) for i,r in enumerate(rows) if r.get('role')=='tool']
        result=semantic_analyze(normalized,context,out,capture={'complete':True,'exclusive':True,'ordering':'serial'})
        return result,[json.loads(l) for l in out.getvalue().splitlines()]
    def test_b1_b2_b3_and_baseline_controls(self):
        expected={'B1':'CREATED_RESOURCE_NOT_READABLE','B2':'DELETED_RESOURCE_STILL_READABLE','B3':'REJECTED_CREATE_STATE_APPEARED'}
        for kind,reason in expected.items():
            for mutation in ('none',kind):
                with self.subTest(kind=kind,mutation=mutation):
                    result,verdicts=self.check_flow(mutation,kind)
                    found=[v for v in verdicts if v['reason']==reason and v['value']=='violation']
                    self.assertEqual(bool(found),mutation==kind,verdicts)
                    if mutation=='none':self.assertEqual(result['finding_partitions']['semantic_candidate']['occurrences'],0)
                    else:
                        self.assertTrue(found[0]['details']['semantic_guarantee'])
                        self.assertGreaterEqual(len(found[0]['evidence']),2)

if __name__=='__main__':unittest.main()
