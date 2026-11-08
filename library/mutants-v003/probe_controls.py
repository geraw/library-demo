"""Independent functional probe, not a Provengo sample or rarity measurement."""
import json,logging,random,tempfile
from pathlib import Path
from urllib.parse import urlsplit
from mutants import create
from replay import replay
logging.disable(logging.CRITICAL)

def generate(seed,steps=200):
    random.seed(seed);rng=random.Random(seed+100000);c=create('original').test_client();c.post('/reset',json={})
    users=[];books=[];loans=[];holds=[];rows=[]
    def call(method,path,body=None):
        r=c.open(path,method=method,json=body) if body is not None else c.open(path,method=method)
        response=r.get_json();assert 200<=r.status_code<300,(method,path,r.status_code)
        rows.append({'role':'tool','method':method,'url':'http://127.0.0.1'+path,'input':body,'status':r.status_code,'response':response,'order':len(rows)+1})
        return response
    for i in range(3):users.append(call('POST','/users',{'name':f'U{i}'})['id'])
    for i in range(3):books.append(call('POST','/books',{'title':f'Book-{i}'})['id'])
    for _ in range(steps):
        freeu=[u for u in users if not any(x['userId']==u for x in loans)]
        freeb=[b for b in books if not any(x['bookId']==b for x in loans)]
        deletable=[b for b in books if not any(x['bookId']==b for x in loans+holds)]
        actions=['readbooks','readholds','query','query']
        if freeu and freeb:actions+=['loan']
        if loans:actions+=['return']
        if len(holds)<12:actions+=['hold']
        if holds:actions+=['cancel']
        if len(books)>1 and deletable:actions+=['deletebook']
        if len(books)<3:actions+=['createbook']
        action=rng.choice(actions)
        if action=='loan':loans.append(call('POST','/loans',{'userId':rng.choice(freeu),'bookId':rng.choice(freeb)}))
        elif action=='return':
            x=rng.choice(loans);call('DELETE',f"/loans/{x['userId']}/{x['bookId']}");loans.remove(x)
        elif action=='hold':holds.append(call('POST','/holds',{'userId':rng.choice(users),'bookId':rng.choice(books)}))
        elif action=='cancel':
            x=rng.choice(holds);call('DELETE',f"/holds/{x['id']}");holds.remove(x)
        elif action=='readbooks':call('GET','/books')
        elif action=='readholds':call('GET','/holds')
        elif action=='query':call('GET',f'/loans?userId={rng.choice(users)}&bookId={rng.choice(books)}')
        elif action=='deletebook':
            b=rng.choice(deletable);call('DELETE',f'/books/{b}');books.remove(b)
        elif action=='createbook':books.append(call('POST','/books',{'title':f'Book-{len(rows)}'})['id'])
    return rows

def run():
    count=0
    with tempfile.TemporaryDirectory() as d:
        for seed in range(100):
            rows=generate(seed)
            for mode in ['original','baseline']:
                result=replay(rows,mode,Path(d)/'trace.jsonl',seed+5000)
                assert result['status']=='PASS',(seed,mode,result)
                count+=1
    return {'generator':'independent functional probe, not Provengo','scenarios':100,'steps_per_scenario':200,'replays':count,'controls':'PASS'}
if __name__=='__main__':print(json.dumps(run(),indent=2))
