#!/usr/bin/env python3
"""External evaluator for the real-Provengo Todoist runtime smoke.

This does not claim semantic bug discovery. It verifies the transport/runtime
contract that the audit requested: real HTTP responses are observed, a
server-assigned identifier is returned from create and subsequently reused,
and create/update/delete all execute through the generated model.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path


def load(path):
    events=[]
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        m=re.search(r'MODEL_EVENT\s+(\{.*\})',line)
        if m:
            try: events.append(json.loads(m.group(1)))
            except json.JSONDecodeError: pass
    return events


def rid(v):
    return None if v is None else str(v)


def evaluate(events):
    created={}
    reused=[]
    update_seen=False
    delete_seen=False
    unexpected_statuses=[]
    for i,e in enumerate(events):
        method=e.get('method'); path=e.get('path',''); status=int(e.get('status',999)); resp=e.get('response')
        if status >= 500:
            unexpected_statuses.append({'index':i,'method':method,'path':path,'status':status})
        if method=='POST' and path in {'/projects','/sections','/tasks','/comments','/labels'} and 200 <= status < 300 and isinstance(resp,dict):
            ident=rid(resp.get('id'))
            if ident:
                created[(path,ident)]=i
        for (collection, ident), create_i in list(created.items()):
            item_prefix=collection+'/'+ident
            if i>create_i and path==item_prefix:
                reused.append({'collection':collection,'id':ident,'create_index':create_i,'reuse_index':i,'method':method})
                if method in {'POST','PUT','PATCH'} and 200 <= status < 300: update_seen=True
                if method=='DELETE' and 200 <= status < 300: delete_seen=True
    result={
        'rule_basis':'External evaluation of immutable HTTP trace produced by real Provengo run',
        'event_count':len(events),
        'server_assigned_id_created':bool(created),
        'server_assigned_id_reused':bool(reused),
        'create_count':len(created),
        'update_seen':update_seen,
        'delete_seen':delete_seen,
        'unexpected_5xx_count':len(unexpected_statuses),
        'unexpected_5xx':unexpected_statuses[:20],
        'sample_reuse':reused[:10],
    }
    result['runtime_contract_confirmed']=all([
        result['event_count']>0,
        result['server_assigned_id_created'],
        result['server_assigned_id_reused'],
        result['update_seen'],
        result['delete_seen'],
        result['unexpected_5xx_count']==0,
    ])
    return result

if __name__=='__main__':
    print(json.dumps(evaluate(load(sys.argv[1])),indent=2,sort_keys=True))
