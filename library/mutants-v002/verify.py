"""Directed positive controls; no malformed inputs or unsupported state transitions."""
import json
from mutants import create

class Scenario:
    def __init__(self, mode):
        self.client=create(mode).test_client();self.steps=[]
        self.client.post('/reset',json={})
        self.u=[self.call('POST','/users',{'name':f'U{i}'},201)['id'] for i in range(3)]
        self.b=[self.call('POST','/books',{'title':f'B{i}'},201)['id'] for i in range(3)]
    def call(self, method, path, body=None, expected=200):
        r=self.client.open(path,method=method,json=body)
        self.steps.append({'method':method,'path':path,'input':body,'status':r.status_code,'response':r.get_json(silent=True)})
        assert r.status_code==expected,(path,r.status_code,r.get_json())
        return r.get_json()
    def loan(self,u,b):return self.call('POST','/loans',{'userId':self.u[u],'bookId':self.b[b]},201)
    def ret(self,u,b):return self.call('DELETE',f'/loans/{self.u[u]}/{self.b[b]}')
    def hold(self,u,b):return self.call('POST','/holds',{'userId':self.u[u],'bookId':self.b[b]},201)['id']
    def cancel(self,h):return self.call('DELETE',f'/holds/{h}')
    def delete(self,b):return self.call('DELETE',f'/books/{self.b[b]}')

def witness(bug, mode):
    s=Scenario(mode)
    if bug=='B1':
        s.loan(0,0);h=s.hold(1,0);k=s.hold(2,0);s.ret(0,0);s.cancel(h);s.loan(1,0);s.loan(0,1);s.ret(1,0);s.cancel(k);s.loan(2,0)
    elif bug=='B2':
        s.loan(0,0);s.ret(0,0);s.loan(1,0);s.loan(0,1);s.ret(1,0);s.delete(0)
        assert len(s.call('GET',f'/loans?userId={s.u[0]}&bookId={s.b[1]}'))==1
    elif bug=='B3':
        h=s.hold(0,0);k=s.hold(1,1);s.hold(2,2);s.cancel(h);s.hold(0,2);s.cancel(k)
        assert not any(x['id']==k for x in s.call('GET','/holds'))
    elif bug=='B4':
        s.loan(0,0);q=f'/loans?userId={s.u[0]}&bookId={s.b[0]}'
        assert len(s.call('GET',q))==1
        s.ret(0,0);assert s.call('GET',q)==[]
    elif bug=='B5':
        s.loan(0,0);s.ret(0,0);s.loan(0,1);s.loan(1,0);s.ret(0,1);s.ret(1,0);s.loan(0,0);s.ret(0,0)
        assert s.call('GET','/loans')==[]
    elif bug=='B6':
        s.loan(0,0);h=s.hold(1,0);s.ret(0,0);s.cancel(h);s.delete(0)
        s.call('GET',f'/books/{s.b[0]}',expected=404)
        assert not any(x['id']==s.b[0] for x in s.call('GET','/books'))
    return s.steps

def verify():
    result={}
    for bug in ['B1','B2','B3','B4','B5','B6']:
        for mode in ['original','baseline']:witness(bug,mode)
        try:witness(bug,bug)
        except AssertionError as exc:result[bug]={'original':'PASS','baseline':'PASS','mutant':'DETECTED','assertion':str(exc)}
        else:raise AssertionError(f'{bug} was not exposed')
    return result
if __name__=='__main__':print(json.dumps(verify(),indent=2))
