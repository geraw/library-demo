"""Source-linked family evidence audit. Never trust stored oracle verdicts."""
import argparse
from collections import Counter,defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'natchan-v005'))
from providers import equal

FAMILIES=['IDEM','CASCADE-1','ADJ','EDGE-U','KNOWN','REF-1','LINK-2','DIV-1','ATOM-1-2']

def digest(raw):return hashlib.sha256(raw).hexdigest()

def journals(raw,chain,budget,depth=0):
    if depth>5:raise ValueError('Nested ZIP depth exceeds 5')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        seen=set()
        for info in z.infolist():
            name=info.filename
            if name in seen:raise ValueError('Duplicate ZIP member')
            seen.add(name)
            if info.is_dir() or not (name.endswith('.zip') or name.endswith('gateway-journal.jsonl')):continue
            if info.file_size>100_000_000:raise ValueError('Member exceeds 100 MB')
            budget[0]-=info.file_size
            if budget[0]<0:raise ValueError('Expanded input exceeds 500 MB')
            body=z.read(info);source=chain+[dict(member=name,sha256=digest(body))]
            if name.endswith('.zip'):yield from journals(body,source,budget,depth+1)
            else:yield source,body

def response(row):
    body=row.get('response')
    if isinstance(body,str):
        try:return json.loads(body)
        except ValueError:return None
    return body

def analyze_rows(rows,source):
    counts=Counter();observations=[];groups=defaultdict(list)
    def emit(family,level,indices,**facts):
        counts[family+':'+level]+=1
        observations.append(dict(family=family,evidence_level=level,lines=indices,source=source,facts=facts))
    for pos,row in enumerate(rows):
        groups[(row.get('action'),row.get('case_id'),row.get('logical_id'))].append((pos,row))
        cat=row.get('category');action=row.get('action');status=row.get('status')
        if cat=='known-failure':
            emit('KNOWN','retained-attempt', [pos+1],status=status,attempt=row.get('attempt'),
                 declared_signature=row.get('known_failure'),ms_since_after=row.get('ms_since_after'),
                 server_error=type(status) is int and 500<=status<=599,
                 limitation='Retry attempt retained; signature definition and trigger/log cause not independently verified')
        if cat in ('reference-check','link2-check'):
            family='REF-1' if cat=='reference-check' else 'LINK-2'
            actual=row.get('stored') if family=='REF-1' else row.get('listed')
            sent=row.get('sent');read=row.get('readback_status')
            if sent is not None and actual is not None and type(read) is int and 200<=read<300:
                emit(family,'recomputed-from-projected-ids',[pos+1],status=status,readback_status=read,
                     ids_equal=equal(sent,actual),sent=sent,observed_ids=actual,field=row.get('field'),mode=row.get('mode'),
                     limitation='Recorded ID projection; full readback absent; stored verdict ignored')
            else:emit(family,'incomplete-projection',[pos+1],status=status)
        if cat=='divergence-check':
            emit('DIV-1','retained-summary',[pos+1],limitation='Stored outcomes are not independently recomputed observations; use raw EDGE-U pairs')
        if cat=='atomicity-check' or cat=='atomicity':
            fields=row.get('fields',row.get('field_states'))
            emit('ATOM-1-2','retained-summary',[pos+1],limitation='Full before/after bodies required for independent atomicity proof')
        if action=='cascade_verify':
            previous=[(i,r) for i,r in enumerate(rows[:pos]) if r.get('action')=='cascade_delete' and
                      r.get('session')==row.get('session') and r.get('path')==row.get('path')]
            if previous:
                i,delete=previous[-1]
                writes=[r for r in rows[i+1:pos] if r.get('path')==row.get('path') and r.get('method') in ('POST','PUT','PATCH','DELETE')]
                if not writes and type(delete.get('status')) is int and 200<=delete['status']<300:
                    emit('CASCADE-1','same-target-delete-readback',[i+1,pos+1],status=status,
                         still_readable=type(status) is int and 200<=status<300,
                         absence_observed=status in (404,410),limitation='Same target only; child/parent relationship not inferred from names')
                    continue
            emit('CASCADE-1','unresolved-relationship',[pos+1],status=status)
        if action=='adjacency_probe':
            verifies=[(j,r) for j,r in enumerate(rows[pos+1:],pos+1) if r.get('action')=='adjacency_verify' and
                      r.get('case_id')==row.get('case_id') and r.get('logical_id')==row.get('logical_id') and r.get('path')==row.get('path')]
            if len(verifies)==1:
                j,verify=verifies[0]
                emit('ADJ','probe-and-readback',[pos+1,j+1],status=status,readback_status=verify.get('status'),
                     server_error=type(status) is int and 500<=status<=599,
                     limitation='Temporal trigger/window and confounder classification remain unverified')
            else:emit('ADJ','probe-only',[pos+1],status=status)
    for (action,case,logical),group in groups.items():
        if action!='idem_write':continue
        if not case or len(group)!=2:
            emit('IDEM','ambiguous-pair',[i+1 for i,_ in group]);continue
        (i,a),(j,b)=group
        same=all(equal(a.get(k),b.get(k)) for k in ('method','path','input'))
        interference=any(r.get('path')==a.get('path') and r.get('method') in ('POST','PUT','PATCH','DELETE') for r in rows[i+1:j])
        if not same or interference:
            emit('IDEM','unqualified-pair',[i+1,j+1]);continue
        statuses=[a.get('status'),b.get('status')]
        emit('IDEM','identical-write-pair',[i+1,j+1],statuses=statuses,sessions=[a.get('session'),b.get('session')],
             server_error=any(type(s) is int and 500<=s<=599 for s in statuses),
             limitation='Identical HTTP writes; session equivalence and operation idempotency are separate requirements')
    creates=defaultdict(list)
    for i,r in enumerate(rows):
        if r.get('action')=='edge_create':creates[r.get('logical_id')].append((i,r))
    for j,u in enumerate(rows):
        logical=u.get('logical_id','')
        if u.get('action')!='edge_update' or '_EDGEU_' not in logical:continue
        key=logical.replace('_EDGEU_','_EDGE_',1);candidates=creates[key]
        if len(candidates)!=1:emit('EDGE-U','ambiguous-pair',[j+1]);continue
        i,c=candidates[0];suffix=logical.split('_EDGEU_',1)[1]
        field=next((k for k in sorted((u.get('input') or {}),key=len,reverse=True) if suffix.startswith(k+'_')),None)
        if not field or field not in (c.get('input') or {}) or not equal(c['input'][field],u['input'][field]):
            emit('EDGE-U','unqualified-pair',[i+1,j+1]);continue
        def kind(s):return s//100 if type(s) is int else None
        emit('EDGE-U','same-field-value-status-comparison',[i+1,j+1],field=field,
             create_status=c.get('status'),update_status=u.get('status'),response_class_differs=kind(c.get('status'))!=kind(u.get('status')),
             limitation='Status comparison only; compatibility of business preconditions and stored-value divergence require additional checks')
    return dict(counts=dict(counts),observations=observations)

def audit(paths):
    result=dict(schema_version='natchan-family-audit/1',journals=[],totals={},new_sut_requests=0)
    total=Counter();seen=set()
    for path in paths:
        raw=path.read_bytes();outer=dict(file=str(path),sha256=digest(raw))
        streams=[([outer],raw)] if path.name.endswith('.jsonl') else journals(raw,[outer],[500_000_000])
        for source,body in streams:
            # Exact duplicate journals are not counted twice across archives/caches.
            h=digest(body)
            if h in seen:continue
            seen.add(h)
            rows=[json.loads(line) for line in body.decode('utf-8-sig').splitlines() if line.strip()]
            report=analyze_rows(rows,source);total.update(report['counts'])
            result['journals'].append(dict(source=source,row_count=len(rows),**report))
    result['totals']=dict(total)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output already exists')
    r=audit(a.input);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r['totals'],indent=2))
