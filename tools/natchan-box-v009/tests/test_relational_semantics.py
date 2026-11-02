"""Neutral resources, raw HTTP only; synthetic controls are not SUT runs."""
import copy,io,json,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contract_context import derive
from traffic import normalize
from judge import analyze


def operation(summary='',kind='object',description=''):
    return {'summary':summary,'description':description,'responses':{'200':{'description':'ok','content':{'application/json':{'schema':{'type':kind}}}},'404':{'description':'absent'}}}


def context():
    paths={
        '/containers/{id}':{'get':operation()},
        '/containers/{id}/add/{source}':{'post':operation()},
        '/objects/{id}':{'get':operation(),'patch':operation()},
        '/objects/{id}/copy':{'post':operation('Copy object')},
        '/objects/{id}/metrics':{'get':operation()},
        '/parents/{id}/metrics':{'get':operation()},
        '/views/{id}':{'get':operation()},
        '/foods/{id}':{'get':operation()},
        '/entries/{id}':{'get':operation()},
    }
    return derive({'openapi':'3.0.0','info':{'title':'Neutral fixture','version':'1'},'paths':paths},'fixture')


def row(method,path,response,status=200,body=None):
    r={'method':method,'path':path,'status':status,'response':response,'actor':'A','epoch':1}
    if body is not None:r['input']=body
    return r


def run(rows):
    out=io.StringIO()
    normalized=[normalize(dict(r,t_utc=r.get('t_utc',f'2026-11-02T00:{i//60:02d}:{i%60:02d}Z')),{'line_1based':i+1,'sha256':'fixture'}) for i,r in enumerate(rows)]
    a=analyze(normalized,context(),out,capture={})
    v=[json.loads(l) for l in out.getvalue().splitlines()]
    return [x for x in v if x['property'] in ('S4','S6') and x['value'] in ('violation','policy_observation')],a


class RelationalTests(unittest.TestCase):
    def test_scaling_and_linear_control(self):
        for final,expected in [(20,1),(19,0)]:
            rows=[row('GET','/containers/1',{'id':1,'items':[{'quantity':13}]}),
                  row('POST','/containers/1/add/7',{'id':1,'items':[{'quantity':17}]},body={'factor':1}),
                  row('GET','/containers/1',{'id':1,'items':[{'quantity':17}]}),
                  row('POST','/containers/1/add/7',{'id':1,'items':[{'quantity':final}]},body={'factor':0.5})]
            findings,_=run(rows);self.assertEqual(len(findings),expected)
            if findings:self.assertEqual(findings[0]['reason'],'SCALED_ACTION_NONLINEAR_DELTA')
            rows[2]['actor']='B';self.assertEqual(run(rows)[0],[])

    def test_scaling_intervening_write(self):
        rows=[row('GET','/containers/1',{'id':1,'quantity':0}),row('POST','/containers/1/add/7',{'id':1,'quantity':4},body={'factor':1}),
              row('PATCH','/objects/2',{'id':2},body={'title':'new'}),row('GET','/containers/1',{'id':1,'quantity':4}),
              row('POST','/containers/1/add/7',{'id':1,'quantity':7},body={'factor':0.5})]
        self.assertEqual(run(rows)[0],[])

    def test_copy_references_and_repaired_control(self):
        source={'id':1,'parts':[{'referenceId':'old','title':'a'}],'steps':[{'refs':[{'referenceId':'old'}]}]}
        for ref,expected in [('old',1),('new',0)]:
            target={'id':2,'parts':[{'referenceId':'new','title':'a'}],'steps':[{'refs':[{'referenceId':ref}]}]}
            f,_=run([row('GET','/objects/1',source),row('POST','/objects/1/copy',target)])
            self.assertEqual(len(f),expected)
            if f:self.assertEqual(f[0]['reason'],'COPY_INTERNAL_REFERENCE_NOT_IN_COPIED_TARGETS')

    def test_copy_ambiguous_source_relation_abstains(self):
        source={'id':1,'a':[{'refId':'x'}],'b':[{'refId':'x'}],'c':[{'refId':'x'}]}
        target={'id':2,'a':[{'refId':'x'}],'b':[{'refId':'y'}],'c':[{'refId':'z'}]}
        self.assertEqual(run([row('GET','/objects/1',source),row('POST','/objects/1/copy',target)])[0],[])

    def test_reference_absence_and_present_control(self):
        for status,expected in [(404,1),(200,0)]:
            f,_=run([row('GET','/foods/7',{'id':7},status),row('GET','/entries/2',{'id':2,'foodId':7})])
            self.assertEqual(len(f),expected)
            if f:self.assertEqual(f[0]['reason'],'REFERENCE_TO_OBSERVED_ABSENT_RESOURCE')

    def test_reference_recreation_invalidates_absence(self):
        self.assertEqual(run([row('GET','/foods/7',{},404),row('POST','/unknown',{'id':7}),row('GET','/entries/2',{'foodId':7})])[0],[])

    def test_aggregate_transfer_and_conserved_control(self):
        for old,expected in [(30,1),(20,0)]:
            rows=[row('GET','/objects/7',{'id':7,'parentId':1}),row('GET','/objects/7/metrics',{'weight':10}),
                  row('GET','/parents/1/metrics',{'weight':30}),row('GET','/parents/2/metrics',{'weight':0}),
                  row('PATCH','/objects/7',{'id':7,'parentId':2},body={'parentId':2}),
                  row('GET','/parents/1/metrics',{'weight':old}),row('GET','/parents/2/metrics',{'weight':10})]
            f,_=run(rows);self.assertEqual(len(f),expected)
            if f:self.assertEqual(f[0]['reason'],'MOVE_AGGREGATE_TRANSFER_MISMATCH')

    def test_nested_view_and_moved_control(self):
        item={'id':7,'title':'example','done':False,'parentId':1}
        for parent,expected in [(1,1),(2,0)]:
            rows=[row('GET','/objects/7',item),row('GET','/views/9',[{'id':1,'children':[item]}]),
                  row('PATCH','/objects/7',dict(item,parentId=2),body={'parentId':2}),
                  row('GET','/views/9',[{'id':parent,'children':[dict(item,parentId=parent)]}])]
            f,_=run(rows);self.assertEqual(len(f),expected)
            if f:self.assertEqual(f[0]['reason'],'MOVED_ENTITY_REMAINS_UNDER_OTHER_PARENT')

    def test_flat_view_is_not_parent_membership(self):
        item={'id':7,'title':'example','done':False,'parentId':1}
        self.assertEqual(run([row('GET','/objects/7',item),row('GET','/views/9',[item]),row('PATCH','/objects/7',dict(item,parentId=2),body={'parentId':2}),row('GET','/views/9',[item])])[0],[])

    def test_epoch_and_actor_and_time_boundaries(self):
        rows=[row('GET','/foods/7',{},404),row('GET','/entries/2',{'id':2,'foodId':7})]
        for field,value in [('epoch',2),('actor','B'),('t_utc','2026-11-01T00:00:00Z')]:
            control=copy.deepcopy(rows);control[-1][field]=value
            self.assertEqual(run(control)[0],[])

    def test_observations_never_promoted_to_violation(self):
        f,_=run([row('GET','/foods/7',{},404),row('GET','/entries/2',{'id':2,'foodId':7,'known_bug':'B5'})])
        self.assertEqual(f[0]['value'],'policy_observation');self.assertFalse(f[0]['details']['background_concurrency_excluded'])

if __name__=='__main__':unittest.main()
