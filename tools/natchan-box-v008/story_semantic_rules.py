"""Product-neutral, source-bound projection and arithmetic hypotheses over retained HTTP."""
from collections import defaultdict
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re

from toolkit_formats import InvalidEvidence, UnsupportedEvidence
from stories_evidence import successful, identity, path, same_actor, number, annotate, add_witnesses

ROOT=Path(__file__).resolve().parent


def matches(template, actual):
    if not isinstance(template,str):return None
    names=re.findall(r'\{([^}]+)\}',template)
    parts=re.split(r'\{[^}]+\}',template.rstrip('/'))
    rx='([^/]+)'.join(re.escape(p) for p in parts)
    m=re.fullmatch(rx,actual.rstrip('/'))
    return dict(zip(names,m.groups())) if m else None


def equal_id(a,b):return type(a) is type(b) and type(a) in (str,int) and a==b


def disambiguate(candidates,row):
    if len({c[0] for c in candidates})==1:return candidates
    if row.get('_entity'):
        return [c for c in candidates if c[0]==row['_entity']]
    if len(candidates)<=1:return candidates
    hint=re.match(r'^(?:create|stale write|read) (\S+)(?: |$)',row.get('_label') or '')
    return [c for c in candidates if c[0]==hint[1]] if hint else []


def walk(value, at):
    if not isinstance(at,str) or not re.fullmatch(r'\$(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)*',at):
        raise ValueError('Unsupported projection path')
    values=[value]
    for seg in (["[]"] if at.startswith('$[]') else [])+[x for x in at.removeprefix('$[]').removeprefix('$').split('.') if x]:
        key=seg[:-2] if seg.endswith('[]') else seg;array=seg.endswith('[]');out=[]
        for v in values:
            v=v if not key else v.get(key) if isinstance(v,dict) else None
            if array:
                if isinstance(v,list):out.extend(v)
            elif v is not None:out.append(v)
        values=out
    return values


def scoped(value, at, parent_at, parent_id, child_id):
    if parent_at=='$':kids=walk(value,at)
    else:
        parents=[p for p in walk(value,parent_at) if isinstance(p,dict) and equal_id(p.get('id'),parent_id)]
        if len(parents)!=1:return [],len(parents)
        segment=at.rsplit('.',1)[-1][:-2]
        kids=parents[0].get(segment,[]) or []
        if not isinstance(kids,list):return [],len(parents)
    return [k for k in kids if isinstance(k,dict) and equal_id(k.get('id'),child_id)],1


def load_profile(reader, files, chain, root, product, result):
    embedded=root+'story-semantics.json';external=getattr(reader,'story_semantics',None)
    defaults={p.stem:p for p in (ROOT/'semantics').glob('*.json')}
    if embedded in files and external:raise InvalidEvidence('Choose embedded or external story semantics, not both')
    if embedded in files:
        raw=files[embedded];source=reader.source(files,embedded,chain)
    elif external:
        raw=Path(external).read_bytes();source=dict(path=str(external),sha256=hashlib.sha256(raw).hexdigest(),role='external_story_semantics')
    elif product in defaults:
        file=defaults[product];raw=file.read_bytes();source=dict(path=str(file),sha256=hashlib.sha256(raw).hexdigest(),role='bundled_contract_bound_story_semantics')
    else:
        reader.gap('STORY_SEMANTIC_PROFILE_MISSING',product=product);return None
    try:spec=json.loads(raw)
    except (ValueError,UnicodeError) as e:raise InvalidEvidence('Invalid story semantics JSON') from e
    if not isinstance(spec,dict) or spec.get('schema_version')!='natchan-story-semantics/1':raise UnsupportedEvidence('Unsupported story semantics schema')
    if spec.get('product')!=product:raise InvalidEvidence('Story semantics product conflict')
    if not result.get('contract_sha256') or spec.get('contract_sha256')!=result['contract_sha256']:
        reader.gap('STORY_SEMANTICS_CONTRACT_BINDING_MISMATCH',product=product,source=source);return None
    if not isinstance(spec.get('entities'),dict) or not all(isinstance(spec.get(k),list) for k in ('projections','arithmetic')):raise InvalidEvidence('Story semantics requires entities, projections and arithmetic')
    try:
        for e in spec['entities'].values():
            if not isinstance(e,dict) or not isinstance(e.get('refs',[]),list):raise ValueError('Entity metadata must include reference lists')
            for r in e.get('refs',[]):
                if not all(isinstance(r.get(k),str) for k in ('field','target','shape')):raise ValueError('Invalid reference metadata')
        for projection in spec['projections']:
            if not isinstance(projection.get('view_template'),str) or not isinstance(projection.get('places'),list):raise ValueError('Invalid projection metadata')
            for place in projection['places']:
                if not all(isinstance(place.get(k),str) for k in ('at','parent_at','child','parent_entity','reference_field')):raise ValueError('Invalid projection place')
                walk({},place['at']);walk({},place['parent_at'])
        for rule in spec['arithmetic']:
            if not all(isinstance(rule.get(k),str) for k in ('entity','parent_field','operator_field','iteration_field','value_field','view_template','items_at','item_parent_field','output_field')):raise ValueError('Invalid arithmetic metadata')
            if not isinstance(rule.get('operators'),dict) or not isinstance(rule.get('modes'),dict):raise ValueError('Arithmetic maps must be objects')
            walk({},rule['items_at'])
            policy=rule.get('rounding',{'mode':'unspecified'})
            if not isinstance(policy,dict):raise ValueError('Rounding policy must be an object')
            if set(policy)-{'mode','quantum','display_steps'}:raise UnsupportedEvidence('Unsupported rounding policy fields')
            if policy.get('mode') not in ('unspecified','none','floor','half_up'):raise UnsupportedEvidence('Unsupported rounding policy')
            if 'quantum' in policy and number(policy['quantum'])<=0:raise ValueError('Rounding quantum must be positive')
            if not isinstance(policy.get('display_steps',[]),list):raise ValueError('Display rounding steps must be a list')
            if any(number(x)<=0 for x in policy.get('display_steps',[])):raise ValueError('Display rounding steps must be positive')
    except UnsupportedEvidence:raise
    except (ValueError,TypeError,AttributeError) as e:raise InvalidEvidence('Invalid semantic metadata: '+str(e)) from e
    try:
        for key in ('contributions','copies','aggregates'):
            if not isinstance(spec.get(key,[]),list):raise ValueError(key+' must be an array')
        for rule in spec.get('contributions',[]):
            for k in ('method','action_template','source_template','container_template','source_action_parameter','scale_field','quantity','source_items','container_items'):
                if not isinstance(rule.get(k),str):raise ValueError('Invalid contribution field '+k)
            for k in ('container_bindings','source_bindings'):
                if not isinstance(rule.get(k),dict) or any(not isinstance(v,str) for v in rule[k].values()):raise ValueError('Invalid contribution bindings')
            if type(rule.get('sign')) is not int or rule['sign'] not in (-1,1):raise ValueError('Contribution sign must be +1 or -1')
            for k in ('source_keys','container_keys'):
                if not isinstance(rule.get(k),list) or any(not isinstance(v,list) or any(not isinstance(x,str) for x in v) for v in rule[k]):raise ValueError('Invalid contribution key accessors')
            if len(rule['source_keys'])!=len(rule['container_keys']):raise ValueError('Contribution key cardinality mismatch')
            walk({},rule['source_items']);walk({},rule['container_items'])
        for rule in spec.get('copies',[]):
            if not all(isinstance(rule.get(k),str) for k in ('method','action_template','source_template','identity_items','reference_items','field')) or not isinstance(rule.get('source_bindings'),dict) or any(not isinstance(v,str) for v in rule['source_bindings'].values()):raise ValueError('Invalid copy metadata')
            walk({},rule['identity_items']);walk({},rule['reference_items'])
        for rule in spec.get('aggregates',[]):
            if not all(isinstance(rule.get(k),str) for k in ('child','parent','reference_field','child_view','parent_view')) or not isinstance(rule.get('fields'),list) or any(not isinstance(f,str) for f in rule['fields']):raise ValueError('Invalid aggregate metadata')
        if not isinstance(spec.get('api_base_path',''),str):raise ValueError('API base path must be a string')
        config=spec.get('log_correlation',{})
        if not isinstance(config,dict):raise ValueError('Log correlation must be an object')
        if not isinstance(config.get('allow_time_join',False),bool):raise ValueError('allow_time_join must be boolean')
        if float(config.get('window_seconds',2))<=0:raise ValueError('Log time window must be positive')
        if config.get('structured_regex'):re.compile(config['structured_regex'])
        if not isinstance(config.get('signatures',{}),dict):raise ValueError('Log signatures must be an object')
        for pattern in config.get('signatures',{}).values():re.compile(pattern)
    except (ValueError,TypeError,AttributeError,re.error) as e:raise InvalidEvidence('Invalid optional semantic metadata: '+str(e)) from e
    source['role']='semantic_profile'
    spec['_profile_sha256']=hashlib.sha256(raw).hexdigest()
    if spec.get('contract_materialization')=='not_retained':reader.gap('SEMANTIC_PROFILE_ORIGINAL_CONTRACT_BYTES_NOT_RETAINED',source=source)
    reader.inputs.append(source)
    reader.gap('STORY_PRODUCT_INVARIANTS_ARE_HYPOTHESES',product=product,source=source,
               affects='Recorded comparisons do not independently establish intended product semantics or defect causality')
    return spec


def check(obs, family, expected, observed, witnesses, **detail):
    obs.setdefault('story_semantic_checks',[]).append(dict(family=family,expected=expected,observed=observed,**detail))
    add_witnesses(obs,*witnesses)


def attempts(rows,gap):
    grouped=defaultdict(list)
    for r in rows:
        if r['_story']:grouped[r['_story']].append(r)
    for sid,group in grouped.items():
        segments=[];current=[]
        for r in group:
            if current and r['_step']==1 and current[-1]['_step']>1:segments.append(current);current=[]
            current.append(r)
        if current:segments.append(current)
        if len(segments)>1:gap('STORY_ATTEMPTS_SEPARATED',story=sid,attempts=len(segments))
        for n,segment in enumerate(segments):
            steps=[r['_step'] for r in segment]
            if len(set(steps))!=len(steps) or steps!=sorted(steps):continue
            yield sid,n,segment


def creations(rows,spec):
    result=[]
    for r in rows:
        if not successful(r):continue
        eligible=[]
        for n,e in spec['entities'].items():
            if r.get('method','').lower()!=e.get('create_method'):continue
            bindings=matches(e.get('path'),path(r))
            if bindings is None:continue
            body=r.get('response')
            nodes=walk(body,e['create_result_items']) if e.get('create_result_items') else [body]
            if e.get('scalar_create_key') and type(body) in (str,int):nodes=[{e.get('id_field') or 'id':body}]
            for node in nodes:
                if isinstance(node,dict) and node.get(e.get('id_field') or 'id') is not None:eligible.append((n,e,bindings,node))
        chosen=disambiguate(eligible,r)
        names={x[0] for x in chosen}
        if len(names)!=1:continue
        for n,e,bindings,node in chosen:
            pk=node[e.get('id_field') or 'id'];bindings=dict(bindings)
            bindings.update({e.get('detail_key_parameter') or e.get('id_field') or 'id':str(pk),'id':str(pk)})
            uri=e.get('detail')
            if uri:
                for k,v in bindings.items():uri=uri.replace('{'+k+'}',v)
                if '{' in uri:uri=None
            result.append(dict(entity=n,pk=pk,node_id=node.get('id',pk),row=r,representation=node,uri=uri.rstrip('/') if uri else None))
    return result


def prior_state(fixture, before, rows):
    state=dict(fixture['row'].get('input') or {});state.update(fixture.get('representation',fixture['row'].get('response')) or {})
    for r in rows:
        if fixture['row']['_position']<r['_position']<before['_position'] and path(r)==fixture['uri'] and successful(r) and r.get('method') in ('PATCH','PUT','POST'):
            if isinstance(r.get('input'),dict):state.update(r['input'])
            if isinstance(r.get('response'),dict):state.update(r['response'])
    return state


def projection_paths(projection,place):
    result=[(place['at'],place['parent_at'])]
    if projection.get('response_array') and projection['places']:
        first=projection['places'][0]['at']
        if place['at'].startswith(first):
            alt='$[]'+place['at'][len(first):]
            parent=place['parent_at'];parent='$[]'+parent[len(first):] if parent.startswith(first) else parent
            if (alt,parent) not in result:result.append((alt,parent))
    return result


def raw_projections(rows,obs,spec,gap):
    created=creations(rows,spec)
    reads=[r for r in rows if r.get('method')=='GET' and successful(r)]
    for write in rows:
        if not successful(write) or write.get('method') not in ('PATCH','PUT','POST','DELETE'):continue
        fixtures=[f for f in created if f['uri']==path(write) and f['row']['_position']<write['_position']]
        if len(fixtures)!=1:continue
        child=fixtures[0];before=prior_state(child,write,rows)
        for projection in spec['projections']:
            for place in projection['places']:
                if place['child']!=child['entity']:continue
                field=place['reference_field'];old_id=before.get(field)
                # Context-specific fields may read as zero outside the view. Retain the accepted creation relation.
                if old_id in (None,0,''):
                    old_id=(child['row'].get('input') or {}).get(field)
                if old_id is None:continue
                parents=[f for f in created if f['entity']==place['parent_entity'] and equal_id(f['pk'],old_id)]
                if len(parents)!=1:continue
                old_parent=parents[0]
                cache=[r for r in reads if r['_position']<write['_position'] and matches(projection['view_template'],path(r)) is not None and same_actor(r,write)]
                # A qualified preimage fixes the exact view path, shape, parent and child identity.
                qualified=[]
                for pre in cache:
                    for at,pat in projection_paths(projection,place):
                        hits,pcount=scoped(pre['response'],at,pat,old_id,child['node_id'])
                        if len(hits)==1 and pcount==1:
                            if pat=='$' and old_parent['uri'] and not (path(pre)==old_parent['uri'] or path(pre).startswith(old_parent['uri']+'/')):continue
                            if pat=='$' and isinstance(pre['response'],dict) and not equal_id(pre['response'].get('id'),old_id):continue
                            qualified.append((pre,at,pat,hits[0]))
                if not qualified:continue
                lastpos=max(p[0]['_position'] for p in qualified);qualified=[p for p in qualified if p[0]['_position']==lastpos]
                if len(qualified)!=1:gap('STORY_PROJECTION_SHAPE_AMBIGUOUS',source=write['source']);continue
                pre,at,pat,old_node=qualified[0]
                body=write.get('input') if isinstance(write.get('input'),dict) else {}
                moving=field in body and not equal_id(body[field],old_id)
                if moving:
                    new_id=body[field];newparents=[f for f in created if f['entity']==place['parent_entity'] and equal_id(f['pk'],new_id) and f['row']['_position']<write['_position']]
                    if len(newparents)!=1 or not isinstance(write.get('response'),dict) or not equal_id(write['response'].get(field),new_id):
                        gap('STORY_MOVE_ACKNOWLEDGEMENT_NOT_QUALIFIED',source=write['source']);continue
                    newparent=newparents[0]
                    candidate_reads=[r for r in reads if r['_position']>write['_position'] and matches(projection['view_template'],path(r)) is not None and same_actor(r,write)]
                    barrier=min((r['_position'] for r in rows if r['_position']>write['_position'] and r.get('method')!='GET'),default=10**18)
                    candidate_reads=[r for r in candidate_reads if r['_position']<barrier]
                    newcache=[r for r in cache if path(r)!=path(pre) and len([p for p in walk(r['response'],pat) if isinstance(p,dict) and equal_id(p.get('id'),newparent['node_id'])])==1] if pat!='$' else [r for r in cache if path(r)!=path(pre) and newparent['uri'] and (path(r)==newparent['uri'] or path(r).startswith(newparent['uri']+'/'))]
                    if not newcache:gap('STORY_MOVE_NEW_PARENT_PREIMAGE_MISSING',source=write['source']);continue
                    nc=newcache[-1]
                    initial_new,_=scoped(nc['response'],at,pat,new_id,child['node_id'])
                    if initial_new:gap('STORY_MOVE_DESTINATION_ALREADY_CONTAINS_CHILD',source=write['source']);continue
                    first_by_path={}
                    for r in candidate_reads:first_by_path.setdefault(path(r),r)
                    candidate_reads=list(first_by_path.values())
                    for read in candidate_reads:
                        if path(read) not in (path(pre),path(nc)):continue
                        old=path(read)==path(pre);pid=old_id if old else new_id
                        hits,np=scoped(read['response'],at,pat,pid,child['node_id']);expected=0 if old else 1
                        if (old and hits) or (not old and (len(hits)!=1 or np!=1)):
                            o=obs[read['_position']];annotate(o,story_move_projection_mismatch=True,raw_story_state_verified=True,
                                move_projection_side='old' if old else 'new',projection_path=at,projection_view_path=path(read),projection_entity=child['entity'])
                            check(o,'PROJ-NEST/MOVE',expected,len(hits),[child['row'],old_parent['row'],newparent['row'],pre,nc,write],parent_matches=np,
                                  child_id=child['node_id'],parent_id=pid,view_path=path(read),at=at,
                                  reference_scope='configured parent relation hypothesis; view-specific semantics may differ')
                else:
                    after=[r for r in reads if r['_position']>write['_position'] and path(r)==path(pre) and same_actor(r,write)]
                    if not after:continue
                    read=after[0]
                    if any(write['_position']<r['_position']<read['_position'] and path(r)==path(write) and r.get('method')!='GET' for r in rows):continue
                    hits,np=scoped(read['response'],at,pat,old_id,child['node_id']);o=obs[read['_position']]
                    if write['method']=='DELETE':
                        if hits:
                            annotate(o,story_deleted_child_still_projected=True,raw_story_state_verified=True,projection_view_path=path(read))
                            check(o,'PROJ-NEST/DELETE',0,len(hits),[child['row'],pre,write],at=at,child_id=child['node_id'])
                    elif len(hits)==1:
                        diffs={f:dict(sent=v,observed=hits[0].get(f)) for f,v in body.items() if f!=field and f in old_node and type(v) in (str,int,float,bool) and old_node[f]!=v and isinstance(write.get('response'),dict) and write['response'].get(f)==v and hits[0].get(f)!=v}
                        if diffs:
                            annotate(o,story_projection_update_not_visible=True,raw_story_state_verified=True,projection_view_path=path(read))
                            check(o,'PROJ-NEST/UPDATE',body,{f:hits[0].get(f) for f in diffs},[child['row'],pre,write],at=at,differences=diffs)


def reference_ids(value):
    if isinstance(value,list):return [x.get('id') if isinstance(x,dict) else x for x in value]
    if isinstance(value,dict):return [value.get('id')]
    return [value]


def raw_stale_context(rows,obs,spec,gap):
    for write in rows:
        if write.get('method') not in ('PATCH','PUT','POST') or not 500<=(write.get('status') or 0)<600 or not isinstance(write.get('input'),dict):continue
        entity=disambiguate([(n,e) for n,e in spec['entities'].items() if matches(e.get('detail'),path(write)) is not None],write)
        if len(entity)!=1:continue
        _,e=entity[0]
        for ref in e.get('refs',[]):
            if ref['shape']=='path' or ref['field'] not in write['input']:continue
            target=spec['entities'].get(ref['target'],{})
            deleted=[r for r in rows if r['_position']<write['_position'] and r.get('method')=='DELETE' and successful(r) and matches(target.get('detail'),path(r)) is not None and same_actor(r,write)]
            for deletion in deleted:
                prior=[r for r in rows if r['_position']<deletion['_position'] and r.get('method')=='GET' and path(r)==path(deletion) and successful(r) and same_actor(r,write) and identity(r) is not None]
                pre=[r for r in rows if r['_position']<deletion['_position'] and r.get('method')=='GET' and path(r)==path(write) and successful(r) and same_actor(r,write) and isinstance(r.get('response'),dict)]
                absence=[r for r in rows if r['_position']>deletion['_position'] and r.get('method')=='GET' and path(r)==path(deletion) and r.get('status')==404 and same_actor(r,write)]
                if not prior or not pre or not absence:continue
                if any(deletion['_position']<r['_position']<write['_position'] and path(r)==path(deletion) and r.get('method')!='GET' and successful(r) for r in rows):
                    gap('STORY_REFERENCE_RECREATED_OR_ASSOCIATION_UNCLEAR',source=write['source']);continue
                tid=identity(prior[-1]);field=ref['field'];snapshot=pre[-1]['response'];sent=reference_ids(write['input'][field]);stored=reference_ids(snapshot.get(field));qualified=any(equal_id(tid,x) for x in sent) and any(equal_id(tid,x) for x in stored)
                changes=[f for f,v in write['input'].items() if f in snapshot and snapshot[f]!=v]
                o=obs[write['_position']]
                if qualified:
                    annotate(o,story_missing_reference_write_5xx=True,story_stale_reference_context_verified=True,raw_story_state_verified=True,reference_field=field,reference_shape=ref['shape'],non_reference_changed_fields=[f for f in changes if f!=field])
                    check(o,'STALE/5XX',{'target_status':404,'mutation_status':'<500'},{'mutation_status':write['status']},[prior[-1],pre[-1],deletion,absence[0]],reference_field=field,other_changed_fields=[f for f in changes if f!=field],causality_proven=False)
                else:
                    annotate(o,story_reference_precondition_failed=True,stale_reference_field=field,stale_other_changed_fields=changes)
                    check(o,'STALE/PRECONDITION',{'snapshot_and_request_reference_target':True},{'snapshot_references_target':any(equal_id(tid,x) for x in stored),'request_references_target':any(equal_id(tid,x) for x in sent)},[prior[-1],pre[-1],deletion,absence[0]],reference_field=field,other_changed_fields=changes,causality_proven=False)
                    gap('STORY_REFERENCE_PRECONDITION_NOT_ESTABLISHED',source=write['source'],field=field,other_changed_fields=changes,
                        affects='The 5xx cannot be attributed to the deleted reference from this retained sequence')


def apply_rounding(value,policy):
    mode=policy.get('mode','unspecified')
    if mode in ('unspecified','none'):return value
    quantum=number(policy.get('quantum',1))
    if quantum<=0:raise ValueError('Rounding quantum must be positive')
    if mode not in ('floor','half_up'):raise ValueError('Unsupported rounding policy')
    return (value/quantum).to_integral_value(rounding=ROUND_FLOOR if mode=='floor' else ROUND_HALF_UP)*quantum


def raw_arithmetic(rows,obs,spec,gap):
    created=creations(rows,spec)
    for rule in spec['arithmetic']:
        configs=[f for f in created if f['entity']==rule['entity']]
        for read in rows:
            if read.get('method')!='GET' or not successful(read) or matches(rule['view_template'],path(read)) is None:continue
            plans=defaultdict(list)
            for c in configs:
                r=c['row'];b=r.get('input') or {};reply=r.get('response') or {}
                if r['_position']>=read['_position'] or not same_actor(r,read):continue
                required=[rule[k] for k in ('parent_field','operator_field','iteration_field','value_field')]
                if not all(k in b for k in required):continue
                if any(k in reply and str(reply[k])!=str(b[k]) for k in required):continue
                plans[(type(b[rule['parent_field']]).__name__,str(b[rule['parent_field']]))].append(c)
            for plan in plans.values():
                first=plan[0]['row']['input'];pid=first[rule['parent_field']];by_iteration={};bad=False
                for c in plan:
                    b=c['row']['input'];it=b[rule['iteration_field']]
                    if type(it) is not int or it<1 or it in by_iteration:bad=True;break
                    by_iteration[it]=c
                if bad:gap('STORY_ARITHMETIC_PLAN_AMBIGUOUS',source=read['source']);continue
                tops=read['response'] if isinstance(read['response'],list) else [read['response']];observed={}
                for top in tops:
                    if not isinstance(top,dict):continue
                    it=top.get(rule['iteration_field'])
                    if type(it) is not int:continue
                    items=[x for x in walk(top,rule['items_at']) if isinstance(x,dict) and equal_id(x.get(rule['item_parent_field']),pid)]
                    if len(items)!=1 or it in observed:bad=True;continue
                    try:observed[it]=number(items[0][rule['output_field']])
                    except (ValueError,KeyError):bad=True
                if bad or not observed:gap('STORY_ARITHMETIC_VIEW_NOT_UNIQUE',source=read['source']);continue
                state=None;expected={};policy=rule.get('rounding',{'mode':'unspecified'});witnesses=[]
                try:
                    for it in range(1,min(max(observed),10000)+1):
                        if it in by_iteration:
                            c=by_iteration[it];b=c['row']['input'];op=rule['operators'].get(str(b[rule['operator_field']]));amount=number(b[rule['value_field']]);witnesses.append(c['row'])
                            if op=='=':state=amount
                            elif state is None:raise ValueError('No replacement control')
                            elif op in ('+','-'):
                                mode=rule['modes'].get(str(b.get(rule.get('step_field'))),'absolute' if not rule.get('step_field') else None)
                                if mode is None:raise ValueError('Unknown arithmetic step meaning')
                                delta=amount if mode=='absolute' else state*amount/100
                                state=state+delta if op=='+' else state-delta
                            else:raise ValueError('Unknown arithmetic operation')
                            state=apply_rounding(state,policy)
                        if state is not None and it in observed:expected[it]=state
                except ValueError:
                    gap('STORY_ARITHMETIC_MEANING_NOT_EVALUABLE',source=read['source']);continue
                replace_controls=[it for it,c in by_iteration.items() if rule['operators'].get(str(c['row']['input'][rule['operator_field']]))=='=' and it in observed and abs(observed[it]-expected.get(it,Decimal('Infinity')))<Decimal('0.011')]
                if not replace_controls:gap('STORY_ARITHMETIC_REPLACE_CONTROL_FAILED',source=read['source']);continue
                differences=[];rounded=[]
                for it,v in expected.items():
                    if abs(v-observed[it])<Decimal('0.011'):continue
                    compatible=any(abs((v/number(step)).to_integral_value(rounding=ROUND_HALF_UP)*number(step)-observed[it])<Decimal('0.011') for step in policy.get('display_steps',[]) if number(step)>0)
                    item=dict(iteration=it,expected=float(v),observed=float(observed[it]))
                    (rounded if compatible else differences).append(item)
                if rounded:gap('STORY_ARITHMETIC_DISPLAY_ROUNDING_COMPATIBLE',source=read['source'],comparisons=rounded,affects='Retained as observations; not classified as arithmetic failures')
                if differences:
                    o=obs[read['_position']];annotate(o,story_arithmetic_discrepancy=True,arithmetic_entity=rule['entity'],raw_story_state_verified=True,rounding_policy_unspecified=policy.get('mode')=='unspecified')
                    check(o,'OP-ENUM',{str(k):float(v) for k,v in expected.items()},{str(k):float(v) for k,v in observed.items()},witnesses,
                          differences=differences,rounding_policy=policy,product_semantics_confirmed=False)
                    if policy.get('mode')=='unspecified':gap('STORY_ARITHMETIC_ROUNDING_POLICY_UNSPECIFIED',source=read['source'],affects='Arithmetic discrepancy is a candidate, not a confirmed product bug')


def analyze(rows,observations,spec,gap):
    obs={o['_position']:o for o in observations}
    for sid,attempt,group in attempts(rows,gap):
        if sid.startswith(('PROJNEST_','MOVE_')):raw_projections(group,obs,spec,gap)
        elif sid.startswith('OPENUM_'):raw_arithmetic(group,obs,spec,gap)
        elif sid.startswith('STALE_'):raw_stale_context(group,obs,spec,gap)
