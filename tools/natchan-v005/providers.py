"""Recomputing trap providers over explicit, source-linked measurements.

No provider consumes a previous verdict. Missing context is unevaluable.
"""
from datetime import datetime, timezone
from decimal import Decimal
import re


def equal(a,b):
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return a==b
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return type(a) is type(b) and a==b


def instant(value):
    match=re.fullmatch(r'(.*T\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)',value)
    if not match:raise ValueError('A timezone-qualified ISO timestamp is required')
    dt=datetime.fromisoformat(match[1]+match[3].replace('Z','+00:00'))
    seconds=int((dt-datetime(1970,1,1,tzinfo=timezone.utc)).total_seconds())
    return Decimal(seconds)+(Decimal('0.'+match[2]) if match[2] else Decimal(0))


def evaluate(probe):
    family=probe['family']
    result={'family':family,'source':probe.get('source'),'status':'not_evaluable','facts':{},'missing':[]}
    required={
        'RESPONSE':['status'], 'EDGE-1':['status','value','constraints'],
        'RT-1':['status','sent','readback','readable_fields','context'],
        'ATOM-1-2':['status','operation','before','after','request','context'],
        'EDGE-U':['create','update','context'],
        'KNOWN':['status','response','operation','trigger_time','request_time','definition'],
        'CASCADE-1':['parent_delete_status','child_read_status','cascade_required','context'],
        'ADJ':['status','trigger_time','request_time','window_seconds','context'],
        'IDEM':['first_request','second_request','status','context'],
        'VIEW':['expected_ids','actual_ids','membership_required','context'],
        'LINK':['operation','target_id','actual_ids','context']}
    if family not in required:raise ValueError('Unsupported trap family '+family)
    result['missing']=[k for k in required[family] if k not in probe]
    if result['missing'] or not probe.get('source'):return result
    needs_context=family in ('RT-1','ATOM-1-2','EDGE-U','CASCADE-1','ADJ','IDEM','VIEW','LINK')
    if needs_context:
        c=probe['context']
        keys=['same_run','ordered','complete']
        extra={'EDGE-U':['same_pair','compatible_preconditions'],
               'CASCADE-1':['relationship_verified','actor_scope_verified','no_intervening_write'],
               'ADJ':['trigger_scope_verified','actor_scope_verified','no_intervening_trigger'],
               'VIEW':['view_scope_verified','actor_scope_verified','no_intervening_write']}
        keys+=extra.get(family,['same_resource','same_actor','no_intervening_write'])
        result['missing']=['context.'+k for k in keys if c.get(k) is not True]
        if result['missing']:return result
    f=result['facts'];status=probe.get('status')
    if type(status) is int:f['server_error']=500<=status<=599
    if family=='RESPONSE':
        f['transport_failure']=status is None and bool(probe.get('transport_error'))
        if 'documented_statuses' in probe and type(status) is int:f['response_documented']=str(status) in [str(s) for s in probe['documented_statuses']]
    elif family=='EDGE-1':
        value=probe['value'];c=probe['constraints'];violated=False
        if isinstance(value,str):violated=('minLength' in c and len(value)<c['minLength']) or ('maxLength' in c and len(value)>c['maxLength'])
        if type(value) in (int,float):violated=('minimum' in c and value<c['minimum']) or ('maximum' in c and value>c['maximum'])
        f.update(explicit_bound_violated=bool(violated),request_accepted=type(status) is int and 200<=status<300)
    elif family=='RT-1':
        if type(status) is not int or not 200<=status<300:result['status']='not_applicable';return result
        changed=[];dropped=[];subtypes={}
        for key in probe['readable_fields']:
            if key not in probe['sent']:continue
            sent=probe['sent'][key]
            if key in probe.get('before',{}) and equal(sent,probe['before'][key]):continue
            if key not in probe['readback']:dropped.append(key);subtypes[key]='dropped';continue
            stored=probe['readback'][key]
            eq=equal(sent,stored)
            if probe.get('field_formats',{}).get(key)=='date-time' and isinstance(sent,str) and isinstance(stored,str):
                try:eq=instant(sent)==instant(stored)
                except ValueError:pass
            if eq:continue
            changed.append(key)
            if probe.get('field_formats',{}).get(key)=='date-time':subtypes[key]='time_change'
            elif isinstance(sent,str) and isinstance(stored,str):
                subtypes[key]=('truncation' if stored and len(stored)<len(sent) and
                               (sent.startswith(stored) or any(stored.endswith(m) and len(stored)>len(m) and sent.startswith(stored[:-len(m)]) for m in ('...','\u2026'))) else
                               'normalization_candidate' if stored in (sent.strip(),sent.lower(),sent.upper(),sent.lstrip('#')) else 'changed')
            else:subtypes[key]='changed'
        f.update(silent_change=bool(changed or dropped),changed_fields=changed,dropped_fields=dropped,change_subtypes=subtypes)
    elif family=='ATOM-1-2':
        if not f.get('server_error'):result['status']='not_applicable';return result
        op=probe['operation']
        if op=='update':
            states={}
            for key,value in probe['request'].items():
                if key not in probe['before'] or equal(value,probe['before'][key]):continue
                if key not in probe['after']:states[key]='unknown'
                elif equal(probe['after'][key],value):states[key]='applied'
                elif equal(probe['after'][key],probe['before'][key]):states[key]='kept'
                else:states[key]='other'
            values=set(states.values())
            f['field_states']=states
            f['atomicity']='partial' if values=={'applied','kept'} else 'committed_despite_error' if values=={'applied'} else 'rolled_back' if values=={'kept'} else 'unknown'
        elif op=='create':
            a,b=probe['before'],probe['after']
            if type(a) is not int or type(b) is not int:result['missing']=['integer before/after matching-item counts'];return result
            f['atomicity']='duplicate' if b-a>1 else 'committed_despite_error' if b-a==1 else 'rolled_back' if b==a else 'unknown'
        elif op=='delete':
            f['atomicity']='committed_despite_error' if probe['before'] is True and probe['after'] is False else 'rolled_back' if probe['before'] is True and probe['after'] is True else 'unknown'
        else:raise ValueError('Unsupported write operation')
    elif family=='EDGE-U':
        a,b=probe['create'],probe['update']
        if 'sent' not in a or 'sent' not in b:result['missing']=['original sent value pair'];return result
        if not equal(a.get('sent'),b.get('sent')):result['missing']=['same sent value'];return result
        x,y=a['status'],b['status']
        if type(x) is not int or type(y) is not int:result['missing']=['HTTP status pair'];return result
        f['pair_qualified']=True
        f['create_update_diverge']=x//100!=y//100
        f['update_accepts_create_rejected']=400<=x<500 and 200<=y<300
        f['update_rejects_create_accepted']=200<=x<300 and 400<=y<500
        if 200<=x<300 and 200<=y<300:
            if 'stored' not in a or 'stored' not in b:result['missing']=['stored value pair'];return result
            f['create_update_diverge']=not equal(a['stored'],b['stored'])
    elif family=='KNOWN':
        d=probe['definition'];delta=instant(probe['request_time'])-instant(probe['trigger_time'])
        f['known_failure_signature_match']=(status in d['statuses'] and probe['operation'] in d['operations'] and 0<=delta<=d['window_seconds'] and re.search(d['response_regex'],str(probe['response'])) is not None)
        f['suppress_failure']=False
    elif family=='CASCADE-1':
        if type(probe['child_read_status']) is not int or not (200<=probe['child_read_status']<300 or probe['child_read_status'] in (404,410)):
            result['missing']=['observable child presence/absence'];return result
        f.update(cascade_required=probe['cascade_required'] is True,child_still_present=type(probe['child_read_status']) is int and 200<=probe['child_read_status']<300,state_qualified=200<=probe['parent_delete_status']<300)
    elif family=='ADJ':
        delta=instant(probe['request_time'])-instant(probe['trigger_time'])
        f.update(adjacency_qualified=0<=delta<=probe['window_seconds'],seconds_after_trigger=str(delta),causation_proven=False)
    elif family=='IDEM':
        f['repeated_write_qualified']=equal(probe['first_request'],probe['second_request'])
    elif family=='VIEW':
        f.update(view_membership_required=probe['membership_required'] is True,view_missing=any(not any(equal(x,y) for y in probe['actual_ids']) for x in probe['expected_ids']),state_qualified=True)
    elif family=='LINK':
        count=sum(equal(x,probe['target_id']) for x in probe['actual_ids']);op=probe['operation']
        if op not in ('add','remove','add_again'):raise ValueError('Unsupported link operation')
        f.update(link_violation=count!=1 if op in ('add','add_again') else count!=0,state_qualified=True)
    result['status']='evaluated'
    return result
