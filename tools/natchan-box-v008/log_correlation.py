"""Conservative source-addressed request/log joins. No adjacency-to-cause inference."""
from collections import defaultdict
from datetime import datetime
import json
import re
from urllib.parse import urlsplit


def instant(v):
    if not isinstance(v,str):return None
    try:d=datetime.fromisoformat(v.replace('Z','+00:00'))
    except ValueError:return None
    return d.timestamp() if d.tzinfo is not None else None


def correlate(rows,observations,logs,config,gap):
    config=config or {};parsed=[];by_position={o['_position']:o for o in observations};joins=[]
    pattern=config.get('structured_regex')
    try:rx=re.compile(pattern) if pattern else None
    except re.error:
        gap('SERVER_LOG_REGEX_INVALID');return dict(joins=[],unmatched_http=len(rows),unparsed_lines=0)
    skipped=0
    for raw,source in logs:
        for i,line in enumerate(raw.splitlines()):
            try:record=json.loads(line)
            except ValueError:
                m=rx.search(line) if rx else None
                if not m:skipped+=1;continue
                record=m.groupdict()
            if not isinstance(record,dict):skipped+=1;continue
            try:status=int(record.get('status')) if record.get('status') is not None else None
            except (TypeError,ValueError):status=None
            parsed.append(dict(request_id=record.get('request_id'),method=record.get('method'),path=record.get('path') or record.get('uri'),status=status,time=instant(record.get('timestamp') or record.get('t_utc')),message=record.get('message') or record.get('error'),source=dict(source,record=i,line_1based=i+1)))
    edges=defaultdict(list);reverse=defaultdict(list)
    for row in rows:
        for n,log in enumerate(parsed):
            if log['method'] and log['method']!=row.get('method'):continue
            if log['path'] and urlsplit(log['path']).path not in {urlsplit(row.get('path') or '').path,urlsplit(row.get('captured_path') or '').path}:continue
            if log['status'] is not None and log['status']!=row.get('status'):continue
            rid=row.get('request_id');basis=None
            if rid and log['request_id']==rid:basis='request_id'
            elif rid and log['request_id']:continue
            elif config.get('allow_time_join') and log['time'] is not None and row.get('t_utc'):
                t=instant(row['t_utc']);window=float(config.get('window_seconds',2))
                if t is not None and abs(log['time']-t)<=window and log['method'] and log['path'] and log['status'] is not None:basis='unique_method_path_status_time'
            if basis:edges[row['_position']].append((n,basis));reverse[n].append(row['_position'])
    for pos,eligible in edges.items():
        if len(eligible)!=1 or len(reverse[eligible[0][0]])!=1:continue
        n,basis=eligible[0];log=parsed[n];o=by_position[pos]
        joined=dict(http_source=o['source'],log_source=log['source'],basis=basis,root_cause_proven=False)
        if log['message'] is not None:joined['associated_log_message']=log['message']
        signatures=[]
        for name,pattern in config.get('signatures',{}).items():
            try:matched=re.search(pattern,str(log['message'] or ''))
            except (re.error,TypeError):gap('SERVER_LOG_SIGNATURE_INVALID',signature=name);continue
            if matched:signatures.append(name)
        if signatures and (by_position[pos].get('status') or 0)>=500:
            joined['server_reported_signatures']=signatures
            o.setdefault('facts',{})['server_reported_error_signature']=True
        o.setdefault('server_log_joins',[]).append(joined);o.setdefault('witnesses',[]).append(log['source']);joins.append(joined)
    if len(joins)<len(rows):gap('SERVER_LOG_JOINS_INCOMPLETE',joined=len(joins),http_records=len(rows),unparsed_lines=skipped,affects='No cause inferred for unjoined or ambiguous records')
    return dict(joins=joins,unmatched_http=len(rows)-len(joins),unparsed_lines=skipped,root_cause_identity_proven=False)
