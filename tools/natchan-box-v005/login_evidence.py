"""Offline login-path facts. Recorded retries, filtered server logs and measurements stay separate."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile

from toolkit_formats import text,UnsupportedEvidence

LOGIN_STATUSES={'V1_LOGIN_SAMPLE_COMPLETED','V1_LOGIN_TIME_BUDGET_STABLE_PARTIAL','NOT_ACCEPTED','V1_LOGIN_STATIC_READY'}
CONTROL_CATEGORIES={'trap-wait','authentication-validation','model-invariant','recovery-phase','post-write-observation',
    'recovery','recovery-control','interaction-phase','interaction','interaction-restore','infrastructure-error','roundtrip-error','reference-error'}


def route(template,path):
    if not isinstance(template,str) or not isinstance(path,str):return False
    pattern=re.escape(template)
    for name in re.findall(r'\{[^}]+\}',template):pattern=pattern.replace(re.escape(name),'[^/?]+',1)
    return re.fullmatch(pattern,path.split('?')[0]) is not None


def parsed(value):
    if isinstance(value,str):
        try:return json.loads(value)
        except ValueError:pass
    return value


def same(a,b):
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return a==b
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return type(a) is type(b) and a==b


def retained_equal(sent,stored):
    """RT-1's documented number/date-time/request-key normalization, not raw request binding."""
    if type(sent) is bool or type(stored) is bool:return type(sent) is type(stored) and sent==stored
    if isinstance(sent,(int,float)) and isinstance(stored,(int,float)):return sent==stored
    if isinstance(sent,str) and isinstance(stored,str):
        if sent==stored:return True
        try:
            a=datetime.fromisoformat(sent.replace('Z','+00:00'));b=datetime.fromisoformat(stored.replace('Z','+00:00'))
            return a.tzinfo is not None and b.tzinfo is not None and a==b
        except ValueError:return False
    if isinstance(sent,dict) and isinstance(stored,dict):return all(k in stored and retained_equal(v,stored[k]) for k,v in sent.items())
    if isinstance(sent,list) and isinstance(stored,list):return len(sent)==len(stored) and all(retained_equal(x,y) for x,y in zip(sent,stored))
    return same(sent,stored)


def context(row,ir,canonical=False):
    candidates=[]
    for e in ir.get('entities',[]):
        for action,key,verb in [('create','path',e.get('create_method')),('update','detail',e.get('update_method')),('read','detail','get'),('delete','detail','delete')]:
            if str(verb).lower()!=str(row.get('method')).lower() or not route(e.get(key),row.get('path')):continue
            entity=e['name'].lower()
            if canonical:
                segments=[s for s in e[key].split('/') if s and '{' not in s]
                if segments:entity=segments[-1]
            schema=e.get(action+'_schema',{})
            properties=schema.get('properties',schema) if isinstance(schema,dict) else {}
            candidates.append(dict(entity=entity,ir_entity=e['name'],operation=action,properties=properties,
                documented_statuses=list(e.get(action,{}).get('responses',{}))))
    unique={json.dumps(c,sort_keys=True):c for c in candidates}
    return next(iter(unique.values())) if len(unique)==1 else dict(entity=None,ir_entity=None,operation='unknown',properties={},documented_statuses=[])


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def timestamp(row):
    try:
        if row.get('t_utc'):return datetime.fromisoformat(row['t_utc'].replace('Z','+00:00')).timestamp()
        if type(row.get('wall_time')) in (int,float):return row['wall_time']
    except (ValueError,TypeError,OverflowError):pass
    return None


def lock_links(rows,log,base_path):
    """Unique method/path/status/time join in both directions, including recorded retry attempts."""
    logs=[]
    for line_number,line in enumerate(log.splitlines(),1):
        match=re.search(r'time=(\S+).*?method=(\w+) uri=(\S+) status=(\d+).*?err="([^"]+)"',line)
        if not match:continue
        moment=timestamp({'t_utc':match[1]});path=match[3]
        if path.startswith(base_path+'/'):path=path[len(base_path):]
        if moment is not None and 'database is locked' in match[5].lower():logs.append(dict(time=moment,method=match[2],path=path,status=int(match[4]),line=line_number,message=line))
    exchanges=[(i,r,timestamp(r)) for i,r in enumerate(rows) if r.get('category') in ('research','known-failure') and type(r.get('status')) is int and r['status']>=500]
    result={}
    for index,row,moment in exchanges:
        if moment is None:continue
        candidates=[l for l in logs if (l['method'],l['path'],l['status'])==(row.get('method'),row.get('path'),row.get('status')) and abs(moment-l['time'])<=2]
        if len(candidates)!=1:continue
        chosen=candidates[0]
        reverse=[r for _,r,t in exchanges if t is not None and (r.get('method'),r.get('path'),r.get('status'))==(chosen['method'],chosen['path'],chosen['status']) and abs(t-chosen['time'])<=2]
        if len(reverse)==1:result[index]=chosen
    return result


def enrich(rows,values,ir,context_data,log_scope):
    """No findings come from reported pass/known-failure/recovery verdicts."""
    source=context_data['source'];index={o['source']['record']:o for o in values};audits=[];gaps=[];attempts=[]
    def src(i):return dict(source,record=i)
    def gap(code,i,**kw):gaps.append(dict(code=code,source=src(i),**kw))
    for i,row in enumerate(rows):
        if row.get('category') in ('infrastructure-error','roundtrip-error','reference-error'):
            gap('RECORDED_TRANSPORT_OR_ORACLE_ERROR',i,category=row.get('category'))
        if row.get('category')=='authentication-validation' and row.get('status')!=200:
            gap('AUTHENTICATION_VALIDATION_FAILED',i,status=row.get('status'))
        if row.get('category')=='known-failure':
            if type(row.get('status')) is not int or not 100<=row['status']<=599:
                gap('RETRY_ATTEMPT_STATUS_INVALID',i);continue
            facts=dict(server_error=row['status']>=500,retry_attempt_status=row['status'],reported_known_failure=row.get('known_failure'))
            # Do not add another research/HTTP record. The attempt remains independently source-addressable.
            o=dict(id='retry-'+str(i),product=context_data['product'],product_version=context_data.get('version'),run_id=context_data['id'],tool='provengo',source=src(i),facts=facts,fact_basis='recomputed',
                evidence_tier='recorded_retry_attempt',http_attempt={k:row.get(k) for k in ('method','path','status','response','attempt','logical_id','session')},witnesses=[])
            values.append(o);index[i]=o;attempts.append(dict(source=src(i),status=row['status'],reported_known_failure=row.get('known_failure')))
        if row.get('category')=='roundtrip-check':
            preceding=next(((j,r) for j,r in reversed(list(enumerate(rows[:i]))) if r.get('category')=='research'),None)
            candidates=[preceding] if preceding and all(preceding[1].get(k)==row.get(k) for k in ('action','logical_id','method','path','session')) and type(preceding[1].get('status')) is int and 200<=preceding[1]['status']<300 else []
            if len(candidates)!=1 or row.get('readback_status')!=200 or not isinstance(row.get('mismatches'),dict):
                gap('ROUNDTRIP_MEASUREMENT_UNBOUND_OR_UNREADABLE',i);continue
            j,raw=candidates[0];request=parsed(raw.get('input'));changes={};dropped=[];bad=False
            if not isinstance(request,dict):gap('ROUNDTRIP_REQUEST_BODY_MISSING',i);continue
            for field,measurement in row['mismatches'].items():
                if field in row.get('skipped_read_only',[]) or field in row.get('skipped_carried_unchanged',[]) or field not in row.get('fields',[]) or field not in request or not isinstance(measurement,dict) or 'sent' not in measurement or not same(measurement['sent'],request[field]):bad=True;break
                if measurement.get('class')=='dropped':dropped.append(field)
                elif measurement.get('class')=='changed' and 'stored' in measurement:
                    if not retained_equal(measurement['sent'],measurement['stored']):changes[field]=measurement
                else:bad=True;break
            if bad:gap('ROUNDTRIP_MEASUREMENT_CONTRADICTION',i);continue
            if changes or dropped:
                o=index[j]
                e=next((e for e in ir.get('entities',[]) if e.get('name')==o.get('ir_entity')),None)
                writable=(e or {}).get(o.get('operation','')+'_schema',{}).get('properties',{})
                readable=(e or {}).get('read_schema',{}).get('properties',{})
                excluded=set(ir.get('roundtrip',{}).get('entities',{}).get((e or {}).get('name'),[]))
                qualified=[k for k in set(changes)|set(dropped) if k in writable and k in readable and isinstance(writable[k],dict) and isinstance(readable[k],dict) and not writable[k].get('readOnly') and not readable[k].get('readOnly') and k not in excluded]
                if set(qualified)!=(set(changes)|set(dropped)):gap('ROUNDTRIP_FIELD_SCHEMA_NOT_QUALIFIED',i)
                if qualified:
                    o['facts'].update(silent_change=True,changed_fields=sorted(k for k in changes if k in qualified),dropped_fields=sorted(k for k in dropped if k in qualified),roundtrip_full_state_verified=False)
                    o['evidence_tier']='producer_readback_values';o.setdefault('witnesses',[]).append(dict(roundtrip_measurement_source=src(i),mismatches={k:v for k,v in changes.items() if k in qualified},dropped_fields=[k for k in dropped if k in qualified]))
            audits.append(dict(category='roundtrip-check',source=src(i),status='PRODUCER_MEASUREMENT_COMPARED',write_source=src(j),changed_fields=sorted(changes),dropped_fields=sorted(dropped),independent_raw_state_verified=False,
                unchanged_fields_not_independently_inferred=True))
        if row.get('category')=='recovery':
            outcome=row.get('outcome');case=row.get('case_id')
            if not isinstance(outcome,dict):gap('RECOVERY_OUTCOME_MISSING',i);continue
            before=outcome.get('prefix_before');after=outcome.get('prefix_restored')
            if before is None or after is None:gap('RECOVERY_PREFIX_BODIES_MISSING',i);continue
            expected_before=fingerprint(before);expected_after=fingerprint(after)
            if outcome.get('prefix_before_sha256')!=expected_before or outcome.get('prefix_restored_sha256')!=expected_after:
                gap('RECOVERY_PREFIX_HASH_CONTRADICTION',i);continue
            equal=same(before,after)
            if outcome.get('api_prefix_equal') is not equal:
                gap('RECOVERY_PREFIX_EQUALITY_CONTRADICTION',i);continue
            attempts_for_case=[(j,r) for j,r in enumerate(rows[:i]) if r.get('category')=='research' and r.get('action')=='negative_attempt' and r.get('case_id')==case]
            if len(attempts_for_case)!=1:gap('RECOVERY_WRITE_ASSOCIATION_AMBIGUOUS',i);continue
            j,write=attempts_for_case[0]
            if write.get('status')!=outcome.get('actual_status'):gap('RECOVERY_WRITE_STATUS_CONTRADICTION',i);continue
            audits.append(dict(category='recovery',source=src(i),case_id=case,status='RECORDED_PREFIX_COMPARISON_VERIFIED',
                prefix_equal=equal,write_source=src(j),before_sha256=expected_before,restored_sha256=expected_after,
                storage_restore_independently_verified=False,snapshot_restored_reported=outcome.get('snapshot_restored')))
            if not equal:gap('RECOVERY_PREFIX_DIFFERENCE_OBSERVED',i)
    if log_scope:
        links=lock_links(rows,log_scope['text'],log_scope.get('base_path','/api/v1'))
        for i,link in links.items():
            if i not in index:continue
            row=rows[i];o=index[i]
            prior=any(r.get('category')=='research' and r.get('method')=='PUT' and re.fullmatch(r'/projects/[^/]+/tasks',r.get('path','')) and type(r.get('status')) is int and 200<=r['status']<300 for r in rows[:i])
            o['facts'].update(correlated_lock=True,prior_task_create_seen=prior)
            o.setdefault('witnesses',[]).append(dict(server_log_source=dict(log_scope['source'],record=link['line']-1,line_1based=link['line']),message=link['message'],basis='unique method/path/status/time within 2 seconds in both directions; no causal inference'))
        audits.append(dict(category='server-log-correlation',source=log_scope['source'],uniquely_linked_error_records=len(links),scope='filtered_log_only',causality_proven=False))
    return dict(audits=audits,gaps=gaps,retry_attempts=attempts)


def analyze_version_aliases(legacy,parts,catalogs):
    """Lossless syntactic v2.6.0 -> 2.6.0 catalog alias; observed metadata stays byte-for-byte literal."""
    aliases={(a['product'],a['observed'],a['catalog']) for _,part in parts for a in part.get('catalog_version_aliases',[])}
    if not aliases:return legacy.analyze(parts,catalogs)
    originals=[];transforms=[]
    with tempfile.TemporaryDirectory(prefix='natchan-version-alias-') as folder:
        for path in sorted(Path(catalogs).glob('*.json')):
            raw=path.read_bytes();doc=json.loads(raw);changed=[]
            for entry in doc['entries']:
                for product,observed,canonical in aliases:
                    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?',observed) or canonical!=observed[1:]:raise ValueError('Invalid lossless catalog version alias')
                    if entry['product']==product and canonical in entry['versions'] and observed not in entry['versions']:
                        entry['versions'].append(observed);changed.append(entry['id'])
            output=json.dumps(doc,indent=2).encode() if changed else raw
            (Path(folder)/path.name).write_bytes(output)
            originals.append(dict(name=path.name,sha256=hashlib.sha256(raw).hexdigest()))
            if changed:transforms.append(dict(name=path.name,source_sha256=hashlib.sha256(raw).hexdigest(),effective_sha256=hashlib.sha256(output).hexdigest(),entries=changed))
        report=legacy.analyze(parts,Path(folder))
    report['catalog_version_aliases']=[dict(product=p,observed=o,catalog=c,policy='single literal v prefix before the same semantic version; no range expansion') for p,o,c in sorted(aliases)]
    report['catalog_source_snapshots']=originals;report['catalog_alias_transformations']=transforms
    return report
