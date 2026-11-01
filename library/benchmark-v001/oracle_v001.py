"""Independent, passive Library oracle. No mutant switches or SUT internals are inputs."""
import json
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

IDS=['B1','B2','B3','B4','B5','B6']
def ident(x):
    if isinstance(x,bool):return None
    try:
        y=int(x)
        return y if y>0 and str(x).strip().lstrip('0')==str(y) else None
    except (ValueError,TypeError):return None

def evaluate(rows,scope='sequence-local'):
    states={}; findings=[]; server=[]; checked={k:0 for k in IDS}; boundaries=0
    def finding(code,row,reason,witness):
        findings.append({'bug':code,'request_id':row['request_id'],'case_id':row.get('case_id'),'reason':reason,'witness_request_ids':witness+[row['request_id']],'scope':scope})
    for row in rows:
        if row.get('role')=='boundary':
            if row.get('empty_verified') is not True:raise ValueError('Unverified case boundary')
            key=(row['epoch'],row['case_id']);states[key]={'books':{},'deleted':{},'holds':{},'loans':{},'rejected':{},'users':{},'last_hold_delete':None};boundaries+=1;continue
        if row.get('role','tool')!='tool':continue
        key=(row.get('epoch'),row.get('case_id'))
        if key not in states:raise ValueError('HTTP row without a verified reset boundary')
        s=states[key];method=row['method'];p=urlsplit(row.get('url',row.get('path','')));path=p.path
        status=row['status'];body=row.get('input');res=row.get('response');rid=row['request_id']
        if 500<=status<600:server.append({'request_id':rid,'case_id':row['case_id'],'status':status})
        if method=='POST' and path in ['/users','/books','/holds','/loans'] and status==201 and isinstance(res,dict):
            entity=path[1:];id_=ident(res.get('id'))
            if entity in ['books','users','holds'] and id_ is not None:s[entity][id_]=(res,rid)
            if entity=='books':s['deleted'].pop(id_,None)
            if entity=='loans':
                pair=(ident(res.get('userId')),ident(res.get('bookId')))
                s['loans'][pair]=(res,rid);s['rejected'].pop(pair,None)
        if method=='DELETE' and status==204:
            parts=path.strip('/').split('/')
            if len(parts)==2 and parts[0]=='books':
                id_=ident(parts[1]);known=s['books'].pop(id_,None)
                if known:s['deleted'][id_]=[known[1],rid]
            elif len(parts)==2 and parts[0]=='users':s['users'].pop(ident(parts[1]),None)
            elif len(parts)==2 and parts[0]=='holds':
                s['holds'].pop(ident(parts[1]),None);s['last_hold_delete']=rid
            elif len(parts)==3 and parts[0]=='loans':s['loans'].pop((ident(parts[1]),ident(parts[2])),None)
        if method=='POST' and path=='/loans' and isinstance(body,dict):
            pair=(ident(body.get('userId')),ident(body.get('bookId')))
            if status==400 and None not in pair and pair not in s['loans']:
                s['rejected'][pair]=rid
            if pair[1] in s['deleted'] and pair[0] in s['users']:
                checked['B6']+=1
                if status==500:finding('B6',row,'Missing deleted book causes server error',s['deleted'][pair[1]])
        if method=='GET' and path.startswith('/books/'):
            id_=ident(path.rsplit('/',1)[1])
            if id_ in s['books']:
                checked['B1']+=1
                if status==404:finding('B1',row,'Created, undeleted book is unavailable',[s['books'][id_][1]])
            if id_ in s['deleted']:
                checked['B2']+=1
                if status==200:finding('B2',row,'Deleted book remains readable',s['deleted'][id_])
        if method=='GET' and path=='/loans' and status==200 and isinstance(res,list):
            q=parse_qs(p.query);u=ident(q.get('userId',[None])[0]);b=ident(q.get('bookId',[None])[0])
            if u is not None and b is not None:
                checked['B4']+=1
                if any(isinstance(x,dict) and (ident(x.get('userId'))!=u or ident(x.get('bookId'))!=b) for x in res):finding('B4',row,'Compound-filter response includes a nonmatching loan',[])
            for pair,request in s['rejected'].items():
                if (u is None or u==pair[0]) and (b is None or b==pair[1]):
                    checked['B3']+=1
                    if any(isinstance(x,dict) and (ident(x.get('userId')),ident(x.get('bookId')))==pair for x in res):finding('B3',row,'Rejected loan creation is visible in readback',[request])
        if method=='GET' and path=='/holds' and not p.query and status==200 and isinstance(res,list):
            present={ident(x.get('id')) for x in res if isinstance(x,dict)}
            # Require an earlier successful deletion in this case before calling it collateral deletion.
            deleted=s['last_hold_delete']
            if deleted:
                checked['B5']+=1
                for id_,(_,created) in s['holds'].items():
                    if id_ not in present:finding('B5',row,'An undeleted hold disappeared',[created,deleted])
    return {'schema_version':'library-oracle-v001/1','scope':scope,'boundaries':boundaries,'http_requests':sum(r.get('role','tool')=='tool' for r in rows),'confirmed_bug_ids':sorted({x['bug'] for x in findings}),'findings':findings,'server_errors':server,'coverage':{k:{'observations':checked[k],'status':'OBSERVED' if checked[k] else 'NOT_EVALUATED'} for k in IDS},'native_tool_findings':'NOT_INFERRED_FROM_ORACLE'}

def read_trace(path):return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip()]
