"""Mechanism-level tests, including former shortcut counterexamples."""
import importlib.util,logging,random,unittest
from pathlib import Path
from verify import Scenario,witness
logging.disable(logging.CRITICAL)

class Regressions(unittest.TestCase):
    def test_directed_witness_matrix(self):
        for bug in ['B1','B2','B3','B4','B5','B6']:
            for mode in ['original','baseline','B1','B2','B3','B4','B5','B6']:
                with self.subTest(bug=bug,mode=mode):
                    random.seed(42)
                    if mode==bug:
                        with self.assertRaises(AssertionError):witness(bug,mode)
                    else:witness(bug,mode)
    def test_v002_shortcuts_are_closed(self):
        for mode in ['B2','B3','B4','B5','B6']:
            with self.subTest(mode=mode):
                s=Scenario(mode)
                if mode=='B2':
                    s.loan(0,0);s.ret(0,0);s.loan(1,0);s.loan(0,1);s.ret(1,0);s.delete(0)
                    self.assertEqual(len(s.call('GET',f'/loans?userId={s.u[0]}&bookId={s.b[1]}')),1)
                elif mode=='B3':
                    h=s.hold(0,0);k=s.hold(1,1);s.hold(2,2);s.cancel(h);s.hold(0,2);s.cancel(k)
                    self.assertFalse(any(x['id']==k for x in s.call('GET','/holds')))
                elif mode=='B4':
                    s.loan(0,0);q=f'/loans?userId={s.u[0]}&bookId={s.b[0]}'
                    s.call('GET',q);s.ret(0,0);self.assertEqual(s.call('GET',q),[])
                elif mode=='B5':
                    s.loan(0,0);s.ret(0,0);s.loan(0,1);s.loan(1,0);s.ret(0,1);s.ret(1,0);s.loan(0,0);s.ret(0,0)
                    self.assertEqual(s.call('GET','/loans'),[])
                elif mode=='B6':
                    s.loan(0,0);h=s.hold(1,0);s.ret(0,0);s.cancel(h);s.delete(0)
                    self.assertFalse(any(x['id']==s.b[0] for x in s.call('GET','/books')))
    def test_b1_no_handoff_is_safe(self):
        s=Scenario('B1');s.loan(0,0);h=s.hold(1,0);k=s.hold(2,0)
        s.ret(0,0);s.loan(0,1);s.cancel(h);s.cancel(k);s.loan(2,0)
    def test_b2_acyclic_retirement_is_safe(self):
        s=Scenario('B2');s.loan(0,0);h=s.hold(1,0);s.ret(0,0);s.loan(0,1);s.loan(1,0);k=s.hold(2,1)
        s.ret(0,1);s.loan(0,2);s.loan(2,1);s.ret(1,0);s.cancel(h);s.ret(2,1);s.cancel(k);s.delete(0)
        self.assertEqual(len(s.call('GET',f'/loans?userId={s.u[0]}&bookId={s.b[2]}')),1)
    def test_b3_release_without_repin_is_safe(self):
        s=Scenario('B3');s.loan(0,2);s.loan(1,0);h=s.hold(2,0);s.hold(0,0);k=s.hold(0,1);s.hold(1,1);s.hold(1,2)
        s.cancel(h);s.ret(0,2);s.ret(1,0);s.cancel(k)
        self.assertFalse(any(x['id']==k for x in s.call('GET','/holds')))
    def test_b4_release_without_positive_refresh_is_safe(self):
        for refresh in [False,True]:
            s=Scenario('B4');s.loan(0,0);s.loan(1,1);h=s.hold(0,1);k=s.hold(1,0)
            q=f'/loans?userId={s.u[0]}&bookId={s.b[0]}'
            s.call('GET',q);s.ret(0,0);s.ret(1,1);s.loan(0,1);s.loan(1,0)
            if refresh:self.assertEqual(s.call('GET',q),[])
            s.cancel(h);s.cancel(k);self.assertEqual(s.call('GET',q),[])
    def test_b5_single_rebound_side_is_safe(self):
        s=Scenario('B5');s.loan(0,0);s.loan(1,1);s.hold(0,1);s.hold(1,0)
        s.ret(0,0);s.ret(1,1);s.loan(0,1);s.ret(0,1);s.loan(0,0);s.ret(0,0)
        self.assertEqual(s.call('GET','/loans'),[])
    def test_reset_clears_fault_metadata(self):
        for mode in ['baseline','B1','B2','B3','B4','B5','B6']:
            s=Scenario(mode);s.loan(0,0);s.hold(1,0)
            s.call('POST','/reset',{})
            for kind in ['users','books','loans','holds']:self.assertEqual(s.call('GET','/'+kind),[])
            u=s.call('POST','/users',{'name':'A'},201)['id'];b=s.call('POST','/books',{'title':'X'},201)['id']
            s.call('POST','/loans',{'userId':u,'bookId':b},201)
    def test_baseline_validation_and_seeded_reset(self):
        s=Scenario('baseline');s.call('POST','/loans',{'userId':True,'bookId':s.b[0]},400)
        s.call('GET','/loans?userId=-1',expected=400)
        s.call('POST','/reset',{'users':[{'id':111111,'name':'A'}],'books':[{'id':222222,'title':'X'}],
            'loans':[{'id':333333,'userId':111111,'bookId':222222}],'holds':[{'id':444444,'userId':111111,'bookId':222222}]})
        self.assertEqual(len(s.call('GET','/books')),1)
        s.call('DELETE','/loans/111111/222222');s.call('DELETE','/holds/444444');s.call('DELETE','/books/222222')
        self.assertEqual(s.call('GET','/books'),[])

if __name__=='__main__':unittest.main()
