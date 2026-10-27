"""Raw JSON/HAR/RESTler network ingestion into the common HTTP semantic judge."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from toolkit_formats import InvalidEvidence,UnsupportedEvidence,text
from toolkit_adapter import Reader,members,MAX_BYTES
from stories_evidence import parsed
from story_semantic_rules import load_profile
from shared_semantics import evaluate


def decode_body(value,encoding=None):
    if encoding=='base64':
        try:value=base64.b64decode(value,validate=True).decode('utf-8')
        except (ValueError,UnicodeError) as e:raise InvalidEvidence('Invalid base64 HTTP body') from e
    elif encoding not in (None,''):raise UnsupportedEvidence('Unsupported HTTP body encoding')
    return parsed(value)


def actor_from(headers,declared=None):
    if declared:return str(declared)
    auth=next((v for k,v in headers.items() if k.lower()=='authorization'),None)
    if auth and not any(x in auth.upper() for x in ('REDACTED','***','<TOKEN>')):
        return 'credential-sha256:'+hashlib.sha256(auth.encode()).hexdigest()
    return None


def har_records(document):
    result=[]
    log=document.get('log')
    if not isinstance(log,dict) or not isinstance(log.get('entries'),list):raise InvalidEvidence('HAR requires log.entries array')
    for i,e in enumerate(log['entries']):
        if not isinstance(e,dict) or not isinstance(e.get('request'),dict) or not isinstance(e.get('response'),dict):raise InvalidEvidence('Invalid HAR entry')
        req=e.get('request',{});res=e.get('response',{});headers={h['name']:h['value'] for h in req.get('headers',[])};content=res.get('content',{})
        result.append(dict(method=req.get('method'),path=req.get('url'),input=decode_body(req.get('postData',{}).get('text')),response=decode_body(content.get('text'),content.get('encoding')),status=res.get('status'),actor=actor_from(headers,e.get('_actor')),request_id=e.get('_request_id') or headers.get('X-Request-ID') or headers.get('x-request-id'),t_utc=e.get('startedDateTime'),case_id=e.get('_case_id'),epoch=e.get('_epoch',0),_source_record=i))
    return result


def split_http(raw,response=False,gap=None):
    raw=raw.replace('\r\n','\n');head,sep,body=raw.partition('\n\n');lines=head.splitlines()
    if not lines:raise InvalidEvidence('Empty native HTTP message')
    headers={}
    for line in lines[1:]:
        k,sep,v=line.partition(':')
        if sep:headers[k.strip()]=v.strip()
    if any(k.lower() in ('transfer-encoding','content-encoding') and v.lower() not in ('identity','') for k,v in headers.items()):
        if gap:gap('RESTLER_HTTP_BODY_ENCODING_UNSUPPORTED',affects='Status retained; encoded body withheld from semantic checks')
        body=None
    if response:
        m=re.match(r'HTTP/\d(?:\.\d)?\s+(\d{3})\b',lines[0])
        if not m:raise InvalidEvidence('Invalid RESTler HTTP response status')
        return dict(status=int(m[1]),response=decode_body(body)),headers
    m=re.match(r'([A-Z]+)\s+(\S+)\s+HTTP/\d(?:\.\d)?$',lines[0])
    if not m:raise InvalidEvidence('Invalid RESTler HTTP request line')
    return dict(method=m[1],path=m[2],input=decode_body(body)),headers


def restler_records(raw,meta,gap):
    pending=None;records=[];markers=0;ambiguous=False
    # RESTler raw_network_logging writes a timestamp followed by repr(message).
    for i,line in enumerate(text(raw).splitlines()):
        m=re.search(r'\b(Sending|Received):\s*(.+?)\s*$',line)
        if not m:continue
        markers+=1
        try:message=ast.literal_eval(m[2])
        except (ValueError,SyntaxError) as e:raise InvalidEvidence('Invalid RESTler repr-encoded message at line '+str(i+1)) from e
        if isinstance(message,bytes):message=message.decode('utf-8',errors='replace')
        if not isinstance(message,str):raise InvalidEvidence('RESTler message must decode to text')
        if m[1]=='Sending':
            if pending is not None:
                gap('RESTLER_UNPAIRED_OR_INTERLEAVED_REQUEST',line_1based=i+1)
                pending['status']=None;records.append(pending);ambiguous=True
            pending,headers=split_http(message,gap=gap)
            pending.update(actor=actor_from(headers,meta.get('default_actor')),request_id=next((v for k,v in headers.items() if k.lower()=='x-request-id'),None),epoch=0,_source_record=i,t_utc=line[:m.start()].strip().rstrip(':'))
        elif pending is None:gap('RESTLER_ORPHAN_RESPONSE',line_1based=i+1)
        else:
            if ambiguous:
                pending['status']=None;records.append(pending);pending=None;gap('RESTLER_RESPONSE_ASSOCIATION_UNRESOLVED',line_1based=i+1)
            else:
                response,_=split_http(message,True,gap);pending.update(response);records.append(pending);pending=None
    if pending is not None:pending['status']=None;records.append(pending);gap('RESTLER_REQUEST_WITHOUT_RESPONSE')
    if not markers:raise UnsupportedEvidence('No RESTler Sending/Received network messages found; provide a native network.* log')
    return records


def normalize(records,context,source,gap,base_path=''):
    rows=[];values=[]
    for i,r in enumerate(records):
        if not isinstance(r,dict):raise InvalidEvidence('HTTP exchange must be an object')
        if 'request' in r and isinstance(r['request'],dict):
            req=r['request'];res=r.get('response',{});headers=req.get('headers',{})
            if not isinstance(res,dict) or not isinstance(headers,dict):raise InvalidEvidence('HTTP request/response structures invalid')
            r=dict(r,method=req.get('method'),path=req.get('url') or req.get('path'),input=decode_body(req.get('body')),response=decode_body(res.get('body')),status=res.get('status'),actor=actor_from(headers,r.get('actor')))
        method=r.get('method');uri=r.get('path') or r.get('url');status=r.get('status')
        if not isinstance(method,str) or not re.fullmatch('[A-Z]+',method) or not isinstance(uri,str):raise InvalidEvidence('HTTP method/path missing')
        if status not in (None,0) and (type(status) is not int or not 100<=status<=599):raise InvalidEvidence('Invalid captured HTTP status')
        actor=r.get('actor') or r.get('session');pos=r.get('_source_record',i);src=dict(source,record=pos)
        if actor is not None and not isinstance(actor,str):raise InvalidEvidence('Captured actor/session must be a string')
        if type(r.get('epoch',0)) not in (str,int) or (r.get('case_id') is not None and not isinstance(r['case_id'],str)):raise InvalidEvidence('Captured epoch/case_id invalid')
        captured=urlsplit(uri).path
        canonical=captured[len(base_path):] if base_path and (captured==base_path or captured.startswith(base_path+'/')) else captured
        row=dict(r,method=method,captured_path=captured,path=(canonical or '/')+('?' + urlsplit(uri).query if urlsplit(uri).query else ''),status=status or None,input=decode_body(r.get('input')),response=decode_body(r.get('response')),session=actor,_position=i,_story=r.get('case_id') or 'traffic',_step=None,_label='',source=src)
        if status in (None,0):gap('HTTP_RESPONSE_MISSING',source=src)
        if not actor:gap('HTTP_ACTOR_NOT_RECORDED',source=src,affects='Semantic same-actor preconditions cannot be established')
        rows.append(row);values.append(dict(context,id=context['run_id']+':'+str(i),source=src,method=method,path=row['path'],captured_path=captured,status=row['status'],request=row['input'],response=row['response'],facts={},fact_basis='recomputed',evidence_tier='recorded_http_sequence',witnesses=[],_position=i))
    return rows,values


def read_into(reader,files,chain,member,meta=None):
    if meta is not None and not isinstance(meta,dict):raise InvalidEvidence('Traffic metadata must be an object')
    meta=dict(meta or {});raw=files[member];lower=member.lower();records=None
    if lower.endswith(('.json','.har','.jsonl')):
        try:document=json.loads(text(raw))
        except ValueError:
            if lower.endswith('.jsonl'):
                try:records=[json.loads(l) for l in text(raw).splitlines() if l.strip()]
                except ValueError as e:raise InvalidEvidence('Invalid HTTP JSONL') from e
            else:raise InvalidEvidence('Invalid HTTP evidence JSON')
        else:
            if isinstance(document,dict) and document.get('schema_version')=='natchan-http-evidence/1':
                for k in ('sut','sut_version','tool','contract_sha256'):
                    if meta.get(k) is not None and document.get(k) is not None and meta[k]!=document[k]:raise InvalidEvidence('HTTP metadata conflict: '+k)
                meta.update({k:v for k,v in document.items() if k!='records'});records=document.get('records')
            elif isinstance(document,dict) and 'log' in document:
                try:records=har_records(document)
                except (AttributeError,KeyError,TypeError) as e:raise InvalidEvidence('Invalid HAR exchange structures') from e
            else:raise UnsupportedEvidence('Unsupported HTTP JSON structure')
    else:records=restler_records(raw,meta,reader.gap)
    if not isinstance(records,list):raise InvalidEvidence('HTTP records must be an array')
    from stories_evidence import ALIASES
    label=meta.get('sut');product=ALIASES.get(label,label);tool=meta.get('tool');version=meta.get('sut_version')
    if not isinstance(product,str) or not isinstance(tool,str):raise UnsupportedEvidence('Raw HTTP evidence requires recorded sut/tool metadata (inline or traffic-meta.json)')
    if version is not None and not isinstance(version,str):raise InvalidEvidence('Observed SUT version must be a string')
    if not version:reader.gap('HTTP_SUT_VERSION_NOT_RECORDED',product=product)
    if meta.get('default_actor') is not None and not isinstance(meta['default_actor'],str):raise InvalidEvidence('Declared capture actor must be a string')
    if reader.sut_config and not reader.story_semantics:reader.gap('SUT_CONFIG_IS_NOT_SEMANTIC_PROFILE')
    run_id='/'.join([reader.path.stem,*chain,member]);context=dict(product=product,product_version=version,tool=tool,run_id=run_id,seed=meta.get('seed'))
    src=reader.source(files,member,chain);reader.inputs.append(src)
    if meta.get('default_actor'):
        for r in records:
            if not isinstance(r,dict):raise InvalidEvidence('HTTP exchange must be an object')
            if not r.get('actor') and not r.get('session'):r['actor']=meta['default_actor']
        reader.gap('HTTP_ACTOR_DECLARED_BY_CAPTURE_METADATA',source=src)
    spec=load_profile(reader,files,chain,member.rsplit('/',1)[0]+'/' if '/' in member else '',product,meta)
    base_path=meta.get('api_base_path') or (spec or {}).get('api_base_path','')
    if not isinstance(base_path,str) or (base_path and not base_path.startswith('/')):raise InvalidEvidence('Invalid captured API base path')
    base_path=base_path.rstrip('/')
    rows,values=normalize(records,context,src,reader.gap,base_path)
    for r in rows:r['case_id']=member+':'+str(r.get('case_id') or 'stream')
    audit=evaluate(rows,values,spec,reader.gap)
    if not hasattr(reader,'semantic_audits'):reader.semantic_audits=[]
    reader.semantic_audits.append(dict(run_id=run_id,tool=tool,product=product,**audit))
    logs=[]
    prefix=member.rsplit('/',1)[0]+'/' if '/' in member else ''
    for name in (prefix+'sut.log',prefix+'server-log.jsonl'):
        if name in files:logs.append((text(files[name]),reader.source(files,name,chain)));reader.inputs.append(reader.source(files,name,chain))
    if logs:
        from log_correlation import correlate
        joins=correlate(rows,values,logs,(spec or {}).get('log_correlation',{}),reader.gap)
        if not hasattr(reader,'log_audits'):reader.log_audits=[]
        reader.log_audits.append(dict(run_id=run_id,**joins))
    else:reader.gap('SERVER_LOG_MISSING',run=run_id)
    for o in values:o.pop('_position',None)
    summary=dict(id=run_id,product=product,version=version,tool=tool,http_records=sum(r['status'] is not None for r in rows),http_5xx=sum((r['status'] or 0)>=500 for r in rows),transport_failures=sum(r['status'] is None for r in rows),evidence_format='http-traffic',source=src)
    reader.summaries.append(summary);reader.parts.append((run_id,dict(observations=values,runs=[summary],original_oracles=[])))
    if not hasattr(reader,'stories_audits'):reader.stories_audits=[]
    reader.stories_audits.append(dict(run_id=run_id,format='raw-http-traffic',retained_research_requests=summary['http_records'],retained_research_5xx=summary['http_5xx']))


class TrafficReader(Reader):
    def __init__(self,path,story_semantics=None,traffic_metadata=None):
        super().__init__(path,story_semantics=story_semantics);self.traffic_metadata=traffic_metadata
    def walk(self,raw,chain=None,inherited=None,depth=0,budget=None):
        if raw.startswith(b'PK'):
            files=members(raw,[MAX_BYTES])
        else:files={self.path.name:raw}
        meta={}
        if self.traffic_metadata:
            content=Path(self.traffic_metadata).read_bytes();meta=json.loads(text(content));self.inputs.append(dict(path=str(self.traffic_metadata),sha256=hashlib.sha256(content).hexdigest()))
        if 'traffic-meta.json' in files:
            if meta:raise InvalidEvidence('Choose embedded or external traffic metadata')
            meta=json.loads(text(files['traffic-meta.json']));self.inputs.append(self.source(files,'traffic-meta.json',[]))
        names=[n for n in files if n.endswith(('http-evidence.json','traffic.har','traffic.jsonl')) or re.search(r'network\.[^/]+\.(?:txt|log)$',n)]
        if len(files)==1:names=list(files)
        if not names:raise UnsupportedEvidence('No recognized raw HTTP evidence file')
        for name in names:read_into(self,files,[],name,meta)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--story-semantics',type=Path);p.add_argument('--traffic-metadata',type=Path);a=p.parse_args()
    try:report=TrafficReader(a.input,a.story_semantics,a.traffic_metadata).finish()
    except UnsupportedEvidence as e:print(json.dumps(dict(code='UNSUPPORTED_TOOLKIT_EVIDENCE',message=str(e))),file=sys.stderr);return 3
    except (InvalidEvidence,UnicodeError,json.JSONDecodeError) as e:print(json.dumps(dict(code='INVALID_TOOLKIT_EVIDENCE',message=str(e))),file=sys.stderr);return 2
    a.output.mkdir(parents=True);(a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');return 0

if __name__=='__main__':raise SystemExit(main())
