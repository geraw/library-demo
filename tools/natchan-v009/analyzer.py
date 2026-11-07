"""Automatic source-linked probe assembly and shared classification, offline only."""
import argparse
from collections import Counter,defaultdict
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v005'))
from providers import evaluate as legacy_evaluate, equal, instant
from coverage_classifier import classify
from classify_measurements import make_observation

FAMILIES=('RESPONSE','EDGE-1','RT-1','ATOM-1-2','EDGE-U','KNOWN','CASCADE-1','ADJ','IDEM','VIEW','LINK','REF-1','LINK-2','DIV-1')
WRITES=('POST','PUT','PATCH','DELETE')
class Missing(ValueError):pass

def require(value,message):
    if not value:raise Missing(message)

def success(e):return type(e.get('status')) is int and 200<=e['status']<300

def project(body,path):
    value=body
    for key in path:
        require(isinstance(value,dict) and key in value,'Missing response projection '+'.'.join(path))
        value=value[key]
    return value

def evaluate(measurement):
    """Extend retained providers, preserving original implementations."""
    p=deepcopy(measurement);family=p['family']
    if family not in FAMILIES:raise ValueError('Unsupported family '+family)
    if family not in ('REF-1','LINK-2','DIV-1'):
        invalid=[]
        if family=='RT-1':invalid=[k for k in ('sent','readback') if not isinstance(p.get(k),dict)]
        if family=='ATOM-1-2' and p.get('operation')=='update':invalid=[k for k in ('before','after','request') if not isinstance(p.get(k),dict)]
        if family=='KNOWN' and p.get('response') is None:invalid=['recorded response body']
        if invalid:return dict(family=family,status='not_evaluable',source=p.get('source'),facts={},missing=invalid)
        r=legacy_evaluate(p)
        # A definite applied/kept pair proves partiality even if other fields are unknown.
        if family=='ATOM-1-2' and r.get('status')=='evaluated':
            states=set(r['facts'].get('field_states',{}).values())
            if {'applied','kept'}<=states:r['facts']['atomicity']='partial'
        return r
    if family=='DIV-1':
        p['family']='EDGE-U';r=legacy_evaluate(p);r['family']=family;return r
    r=dict(family=family,status='not_evaluable',source=p.get('source'),facts={},missing=[])
    required=['sent_ids','actual_ids','readback_status','context']
    r['missing']=[x for x in required if x not in p]
    if r['missing']:return r
    context=p['context'];keys=['same_run','ordered','complete','same_resource','same_actor','no_intervening_write']
    r['missing']=['context.'+k for k in keys if context.get(k) is not True]
    if r['missing']:return r
    if not p.get('source') or type(p['readback_status']) is not int or not 200<=p['readback_status']<300:
        r['missing']=['source-linked successful readback'];return r
    if not isinstance(p['sent_ids'],list) or not isinstance(p['actual_ids'],list):
        r['missing']=['ID arrays'];return r
    status=p.get('status')
    if type(status) is not int or not 200<=status<300:
        r['status']='not_applicable';return r
    # Reference arrays are sets by declared profile; multiplicity remains separate.
    missing=[x for x in p['sent_ids'] if not any(equal(x,y) for y in p['actual_ids'])]
    added=[x for x in p['actual_ids'] if not any(equal(x,y) for y in p['sent_ids'])]
    r['facts']=dict(reference_projection_differs=bool(missing or added),missing_reference_ids=missing,
                    additional_reference_ids=added,reference_semantics=p.get('semantics'),
                    reference_policy_violation=p.get('semantics')=='exact_set' and bool(missing or added),
                    relationship_cleared=bool(p.get('before_ids')) and not p['actual_ids'] and p.get('semantics')=='exact_set',
                    projection_evidence=p.get('evidence_tier','full_readback'))
    r['status']='evaluated';return r


def assemble(document):
    """The producer tags probe roles; context comes from trace, never supplied booleans."""
    require(document.get('schema_version')=='natchan-events/1','Expected natchan-events/1')
    profile=document['profile'];events=document['events'];policies=profile.get('families',{})
    require(profile.get('id') and profile.get('version'),'Versioned product profile required')
    require(document.get('capture_complete') is True,'Recorder must declare complete capture')
    ids=[e['id'] for e in events];require(len(ids)==len(set(ids)),'Duplicate event ID')
    groups=defaultdict(list)
    for position,e in enumerate(events):
        require(e.get('run_id') and e.get('case_id') and e.get('actor') and e.get('resource'),'Missing event scope')
        if 'probe' in e:
            require(e['probe'].get('id') and e['probe'].get('family') in FAMILIES,'Invalid probe metadata')
            groups[(e['run_id'],e['case_id'],e['probe']['id'],e['probe']['family'])].append((position,e))
    measurements=[];failures=[]
    for (run,case,probe_id,family),items in groups.items():
        base=dict(id=run+':'+case+':'+probe_id,product=profile['id'],product_version=profile['version'],run_id=run,
                  family=family,entity=items[-1][1].get('entity'),tool=document.get('tool'),source=dict(event_ids=[e['id'] for _,e in items],profile_id=profile['id'],
                    profile_version=profile['version'],events_sha256=hashlib.sha256(json.dumps(events,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
        roles=defaultdict(list)
        for i,e in items:roles[e['probe'].get('role','request')].append((i,e))
        def role(name):
            require(len(roles[name])==1,'Exactly one '+name+' event required')
            return roles[name][0][1]
        def principal(e):return profile.get('identities',{}).get(e['actor'],e['actor'])
        def context(selected,allow_resources=False,allow_actors=False):
            positions=[ids.index(e['id']) for e in selected]
            require(positions==sorted(positions) and len(set(positions))==len(positions),'Probe event order invalid')
            require(len({(e['run_id'],e['case_id']) for e in selected})==1,'Cross-case probe')
            if not allow_actors:require(len({principal(e) for e in selected})==1,'Actor identity mismatch')
            if not allow_resources:require(len({e['resource'] for e in selected})==1,'Resource mismatch')
            resources={e['resource'] for e in selected};selected_ids={e['id'] for e in selected}
            for e in events[min(positions):max(positions)+1]:
                require(not (e['run_id']==run and e.get('role')=='reset'),'Reset inside probe')
                if (e['run_id'],e['case_id'])!=(run,case):continue
                if e['id'] not in selected_ids and e['resource'] in resources and e.get('method') in WRITES:
                    raise Missing('Intervening resource write')
            return dict(same_run=True,ordered=True,complete=True,same_actor=True,same_resource=True,no_intervening_write=True)
        try:
            policy=policies.get(family,{})
            policy_id=items[-1][1]['probe'].get('policy')
            if policy_id:
                require(policy_id in profile.get('policies',{}),'Unknown product policy ID')
                policy=profile['policies'][policy_id]
                require(policy.get('family')==family,'Policy family differs')
            if family in ('EDGE-U','DIV-1'):
                a,b=role('create'),role('update');pre=role('update_before')
                c=context([a,pre,b],allow_resources=True)
                field=a['probe'].get('field');require(field and field==b['probe'].get('field'),'Field pair mismatch')
                require(a.get('parent_scope')==b.get('parent_scope') and a.get('parent_scope') is not None,'Parent scope missing or differs')
                require(success(pre),'Successful update preimage required')
                require(policy.get('comparable_preconditions') is True,'Product profile must declare comparable create/update preconditions')
                require(pre['resource']==b['resource'],'Update preimage resource mismatch')
                c.update(same_pair=True,compatible_preconditions=True)
                require(field in a.get('request',{}) and field in b.get('request',{}),'Original sent values missing')
                base.update(context=c,field=field,create=dict(status=a['status'],sent=a['request'][field]),update=dict(status=b['status'],sent=b['request'][field]),operation='update',status=b['status'])
                base['email_validation_context']=(field=='email' and isinstance(a.get('response'),dict) and equal(a['response'].get('email'),a['request'][field]) and re.search('email',str(b.get('response','')),re.I) is not None)
                if success(a) and success(b):
                    ca,ub=role('create_after'),role('update_after')
                    context([a,ca]);context([pre,b,ub]);require(ca['resource']==a['resource'] and ub['resource']==b['resource'],'Paired readback resource mismatch')
                    require(success(ca) and success(ub),'Successful paired readbacks required')
                    base['create']['stored']=project(ca['response'],[field]);base['update']['stored']=project(ub['response'],[field])
            elif family=='CASCADE-1':
                before,delete,after=role('child_before'),role('parent_delete'),role('child_after')
                c=context([before,delete,after],allow_resources=True)
                require(before['resource']==after['resource'],'Child resource mismatch')
                require(success(before),'Child must exist before deletion')
                relation=next((r for r in profile.get('relationships',[]) if r.get('id')==after['probe'].get('relationship')),None)
                require(relation is not None,'Declared relationship required')
                require(before.get('parent_resource')==delete['resource'],'Recorded child parent differs')
                require(before.get('entity')==relation['child'] and delete.get('entity')==relation['parent'],'Relationship entity mismatch')
                c.update(relationship_verified=True,actor_scope_verified=True)
                base.update(context=c,parent_delete_status=delete['status'],child_read_status=after['status'],cascade_required=relation['cascade_required'])
            elif family in ('ADJ','KNOWN'):
                trigger,request=role('trigger'),role('request');c=context([trigger,request],allow_resources=True)
                require(success(trigger),'Trigger was not successful')
                require(trigger.get('operation')==policy.get('trigger_operation') and policy.get('trigger_operation'),'Unexpected trigger operation')
                between=events[ids.index(trigger['id'])+1:ids.index(request['id'])]
                require(not any(e.get('operation')==policy['trigger_operation'] and (e['run_id'],e['case_id'])==(run,case) for e in between),'Intervening trigger')
                c.update(trigger_scope_verified=True,actor_scope_verified=True,no_intervening_trigger=True)
                base.update(context=c,status=request['status'],trigger_time=trigger['time'],request_time=request['time'],window_seconds=policy['window_seconds'])
                if family=='KNOWN':base.update(response=request.get('response'),operation=request['operation'],definition=policy['definition'])
            elif family=='IDEM':
                first,second=role('first'),role('second');c=context([first,second])
                def req(e):return dict(method=e['method'],resource=e['resource'],body=e.get('request'))
                require(first['method'] in WRITES and second['method'] in WRITES,'Writes required')
                base.update(context=c,first_request=req(first),second_request=req(second),status=second['status'])
                base['first_status']=first['status']
            elif family in ('RT-1','ATOM-1-2','REF-1','LINK-2','VIEW','LINK'):
                write,after=role('write'),role('after');selected=[write,after]
                before=role('before') if roles['before'] else None
                if before:selected.insert(0,before)
                c=context(selected)
                require(success(after) or family=='ATOM-1-2' and policy.get('operation')=='delete' and after.get('status') in (404,410),'Successful readback or observed deletion required')
                base.update(context=c,status=write['status'])
                if family=='RT-1':
                    require(policy.get('readable_fields') is not None,'Readable schema fields required')
                    base.update(sent=write['request'],readback=after['response'],readable_fields=policy['readable_fields'],field_formats=policy.get('field_formats',{}))
                    if before:require(success(before),'Successful preimage required');base['before']=before['response']
                elif family=='ATOM-1-2':
                    require(before is not None and success(before),'Successful preimage required')
                    op=policy.get('operation');base.update(operation=op,request=write.get('request',{}))
                    if op=='update':base.update(before=before['response'],after=after['response'])
                    elif op=='delete':base.update(before=True,after=False if after['status'] in (404,410) else True)
                    elif op=='create':
                        path=policy['count_path'];base.update(before=len(project(before['response'],path)),after=len(project(after['response'],path)))
                        require(policy.get('matching_item_scope') is True,'Matching-item list scope required')
                    else:raise Missing('Unsupported atomicity operation')
                elif family in ('REF-1','LINK-2'):
                    require(policy.get('semantics') in ('observe','exact_set'),'Reference semantics required')
                    base.update(sent_ids=project(write['request'],policy['request_path']),actual_ids=project(after['response'],policy['response_path']),readback_status=after['status'],semantics=policy['semantics'])
                    if before:require(success(before),'Successful preimage required');base['before_ids']=project(before['response'],policy['response_path'])
                elif family=='VIEW':
                    require(policy.get('membership_required') is not None,'View policy required')
                    base.update(expected_ids=project(write['request'],policy['expected_path']),actual_ids=project(after['response'],policy['response_path']),membership_required=policy['membership_required'])
                    c.update(view_scope_verified=True,actor_scope_verified=True)
                elif family=='LINK':
                    base.update(operation=policy['operation'],target_id=project(write['request'],policy['target_path']),actual_ids=project(after['response'],policy['response_path']))
            else:
                request=role('request');base['status']=request.get('status')
                if family=='EDGE-1':base.update(value=project(request['request'],policy['request_path']),constraints=policy['constraints'])
                if family=='RESPONSE':base.update(transport_error=request.get('transport_error'),documented_statuses=policy.get('documented_statuses',[]))
            measurements.append(base)
        except (Missing,KeyError,TypeError,ValueError) as error:
            failures.append(dict(id=base['id'],family=family,status='not_evaluable',missing=[str(error)],source=base['source']))
    return measurements,failures


def analyze(document):
    if document.get('schema_version')=='natchan-events/1':measurements,failures=assemble(document)
    elif document.get('schema_version')=='natchan-measurements/1':measurements,failures=document['measurements'],[]
    else:raise ValueError('Unsupported evidence schema')
    observations=[];results=list(failures)
    for p in measurements:
        try:r=evaluate(p)
        except (KeyError,TypeError,ValueError) as error:r=dict(status='not_evaluable',missing=[str(error)],facts={})
        r.update(id=p['id'],family=p['family'],source=p.get('source'));results.append(r)
        if r['status']=='evaluated':
            observation=make_observation(p,r);observation['producer']='natchan-v009'
            if p.get('product')=='gitea' and p.get('entity')=='organization' and p.get('field')=='email' and p.get('email_validation_context') is not True:
                for key in ('same_email_value_pair_verified','create_accepted_update_rejected','update_status'):observation['facts'].pop(key,None)
            observations.append(observation)
            # Both repeated-write responses remain visible, including first-write failure.
            if p['family']=='IDEM' and type(p.get('first_status')) is int and 500<=p['first_status']<=599:
                extra=deepcopy(observation);extra['id']+=':first';extra['status']=p['first_status'];extra['facts']['server_error']=True;observations.append(extra)
    report=classify(observations,ROOT/'catalogs');report['provider_evaluations']=results
    report['family_coverage']={f:dict(Counter(r['status'] for r in results if r['family']==f)) or {'no_measurements':True} for f in FAMILIES}
    report['new_sut_requests']=0
    report['native_results']=document.get('native_results')
    report['native_results_inferred_from_external_findings']=False
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output already exists')
    raw=a.input.read_bytes();r=analyze(json.loads(raw.decode('utf-8-sig')));r['input_sha256']=hashlib.sha256(raw).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print('NATCHAN_V009_COMPLETE '+str(a.output.resolve()))
