"""Common offline semantic judge. No tool-name branch and no producer verdict input."""
from collections import Counter,defaultdict
from decimal import Decimal
import copy
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit
from stories_evidence import successful,identity,path,same_actor,annotate,add_witnesses,raw_references,raw_absent_errors,raw_aggregates,number,vector,close_vectors
from story_semantic_rules import matches,walk,equal_id,reference_ids,creations,raw_projections,raw_arithmetic,raw_stale_context,check


def canonical(spec):
    spec=copy.deepcopy(spec)
    for alias,target in spec.get('entity_aliases',{}).items():
        if alias not in spec['entities'] or target not in spec['entities']:continue
        a,b=spec['entities'][alias],spec['entities'][target]
        if any(a.get(k)!=b.get(k) for k in ('path','detail','create_method','id_field')):continue
        del spec['entities'][alias]
        for e in spec['entities'].values():
            for ref in e.get('refs',[]):
                if ref['target']==alias:ref['target']=target
    return spec


def epochs(rows,gap):
    groups=defaultdict(list)
    for r in rows:groups[(r.get('epoch',0),r.get('case_id') or r.get('_story') or 'traffic')].append(r)
    for key,group in groups.items():
        # Clean step-1 restarts are explicit attempt boundaries; never borrow an earlier prefix.
        parts=[];current=[]
        for r in group:
            if current and r.get('_step')==1 and (current[-1].get('_step') or 0)>1:parts.append(current);current=[]
            current.append(r)
        if current:parts.append(current)
        if len(parts)>1:gap('STORY_ATTEMPTS_SEPARATED',story=str(key),attempts=len(parts))
        for part in parts:
            steps=[r['_step'] for r in part if r.get('_step') is not None]
            if steps and (len(steps)!=len(set(steps)) or steps!=sorted(steps)):
                gap('SEMANTIC_SEQUENCE_ASSOCIATION_AMBIGUOUS',scope=str(key));continue
            yield part


def ref_audit(rows,obs,spec,gap):
    records=[]
    created=creations(rows,spec)
    for deletion in rows:
        if deletion.get('method')!='DELETE' or not successful(deletion):continue
        target_entities=[n for n,e in spec['entities'].items() if matches(e.get('detail'),path(deletion)) is not None]
        if len(target_entities)!=1:continue
        target=target_entities[0]
        target_reads=[r for r in rows if r['_position']<deletion['_position'] and r.get('method')=='GET' and path(r)==path(deletion) and successful(r) and identity(r) is not None and same_actor(r,deletion)]
        if not target_reads:continue
        tid=identity(target_reads[-1]);seen=set()
        for fixture in created:
            if fixture['row']['_position']>=deletion['_position'] or not fixture['uri'] or not same_actor(fixture['row'],deletion):continue
            for ref in spec['entities'][fixture['entity']].get('refs',[]):
                if ref['target']!=target or ref['shape']=='path':continue
                f=ref['field'];sent=reference_ids((fixture['row'].get('input') or {}).get(f))
                if not any(equal_id(tid,x) for x in sent):continue
                key=(fixture['uri'],f,str(tid))
                if key in seen:continue
                seen.add(key)
                pre=[r for r in rows if fixture['row']['_position']<r['_position']<deletion['_position'] and r.get('method')=='GET' and path(r)==fixture['uri'] and successful(r) and same_actor(r,deletion) and isinstance(r.get('response'),dict)]
                post=[r for r in rows if r['_position']>deletion['_position'] and r.get('method')=='GET' and path(r)==fixture['uri'] and same_actor(r,deletion)]
                errors=[r for r in rows if r['_position']>deletion['_position'] and path(r)==fixture['uri'] and r.get('method') in ('PATCH','PUT','POST') and 500<=(r.get('status') or 0)<600 and same_actor(r,deletion)]
                anchor=errors[0] if errors else post[0] if post else deletion
                rec=dict(entity=fixture['entity'],field=f,target=target,target_id=tid,source=anchor['source'],precondition='missing_preimage',postcondition='not_evaluable',witnesses=[fixture['row']['source'],target_reads[-1]['source'],deletion['source']])
                if not pre or f not in pre[-1]['response']:
                    gap('REFERENCE_PRECONDITION_PREIMAGE_MISSING',source=anchor['source'],field=f);records.append(rec);continue
                rec['witnesses'].append(pre[-1]['source'])
                present=any(equal_id(tid,x) for x in reference_ids(pre[-1]['response'].get(f)))
                rec['precondition']='established' if present else 'not_established'
                if not present:
                    o=obs[anchor['_position']];annotate(o,story_reference_precondition_failed=True,reference_field=f)
                    check(o,'REFERENCE/PRECONDITION',{'reference_observed_before_delete':True},{'reference_observed_before_delete':False},[fixture['row'],target_reads[-1],pre[-1],deletion],field=f,producer_verdict_used=False)
                    gap('REFERENCE_PRECONDITION_NOT_ESTABLISHED',source=anchor['source'],field=f,affects='A passing outcome cannot be credited as an evaluated reference test')
                    records.append(rec);continue
                absence=[r for r in rows if r['_position']>deletion['_position'] and path(r)==path(deletion) and r.get('method')=='GET' and r.get('status')==404 and same_actor(r,deletion)]
                if not absence:records.append(rec);continue
                if any(r['_position']>deletion['_position'] and r['_position']<absence[0]['_position'] and path(r)==path(deletion) and r.get('method')!='GET' and successful(r) for r in rows):records.append(rec);continue
                after=[r for r in post if r['_position']>absence[0]['_position']]
                if not after:records.append(rec);continue
                read=after[0];rec['witnesses'] += [absence[0]['source'],read['source']]
                if read['status']==404:rec['postcondition']='referrer_removed'
                elif successful(read) and isinstance(read.get('response'),dict) and f in read['response']:
                    dangling=any(equal_id(tid,x) for x in reference_ids(read['response'].get(f)))
                    rec['postcondition']='dangling' if dangling else 'reference_cleared'
                    if dangling:
                        writes=[r for r in rows if deletion['_position']<r['_position']<read['_position'] and path(r)==fixture['uri'] and r.get('method') in ('PATCH','PUT','POST') and successful(r) and same_actor(r,read) and any(equal_id(tid,x) for x in reference_ids((r.get('input') or {}).get(f)))]
                        o=obs[read['_position']];annotate(o,story_dangling_reference=True,story_dangling_delete_only=not writes,dangling_after_stale_write=bool(writes),reference_field=f,raw_story_state_verified=True)
                        check(o,'REFERENCE/AFTER-DELETE',{'references_deleted_target':False},{'references_deleted_target':True},[fixture['row'],pre[-1],deletion,absence[0]],field=f)
                records.append(rec)
    return records


def latest_read(rows,template,binding,until,actor):
    candidates=[]
    for r in rows:
        params=matches(template,path(r))
        if r['_position']<until and r.get('method')=='GET' and successful(r) and same_actor(r,actor) and params is not None and all(params.get(k)==str(v) for k,v in binding.items()):candidates.append(r)
    return candidates[-1] if candidates else None


def key_value(item,paths):
    vals=[]
    for p in paths:
        node=item
        for segment in p.split('.'):
            node=node.get(segment) if isinstance(node,dict) else None
        vals.append(node)
    nonnull=[v for v in vals if v is not None]
    if any(type(v) not in (str,int) for v in nonnull):raise ValueError('Contribution identity accessors must resolve to scalar identifiers')
    if nonnull and any(type(v) is not type(nonnull[0]) or v!=nonnull[0] for v in nonnull):raise ValueError('Conflicting key accessors')
    return nonnull[0] if nonnull else None


def sums(body,at,quantity,keys):
    # A missing array is unavailable evidence, not an observed empty collection.
    projection=at[:-2] if at.endswith('[]') else at
    nodes=walk(body,projection)
    if not nodes or any(not isinstance(node,list) for node in nodes):raise ValueError('Missing contribution collection')
    result=defaultdict(Decimal)
    for item in walk(body,at):
        if not isinstance(item,dict) or quantity not in item:raise ValueError('Missing quantity')
        values=[key_value(item,k) for k in keys]
        if keys and all(v is None for v in values):raise ValueError('No observable contribution identity')
        key=tuple((type(v).__name__,str(v)) for v in values)
        result[key]+=number(item[quantity])
    return dict(result)


def raw_contributions(rows,obs,spec,gap):
    audit=[];evaluated=[]
    for rule in spec.get('contributions',[]):
        actions=[]
        for r in rows:
            if r.get('method')!=rule['method']:continue
            params=matches(rule['action_template'],path(r))
            if params is not None:actions.append((r,params))
        for action,params in actions:
            rec=dict(family='CONTRIB',source=action['source'],status='not_evaluable');audit.append(rec)
            if not successful(action):rec['reason']='action_not_accepted';continue
            if any(v not in params for mapping in (rule['container_bindings'],rule['source_bindings']) for v in mapping.values()):rec['reason']='action_binding_missing';continue
            cb={k:params[v] for k,v in rule['container_bindings'].items()}
            sb={k:params[v] for k,v in rule['source_bindings'].items()}
            container=latest_read(rows,rule['container_template'],cb,action['_position'],action)
            # Source route keys (slug) may differ from the action's stable object ID.
            sources=[r for r in rows if r['_position']<action['_position'] and r.get('method')=='GET' and successful(r) and same_actor(r,action) and matches(rule['source_template'],path(r)) is not None and isinstance(r.get('response'),dict) and equal_id(r['response'].get(rule.get('source_id_field','id')),params.get(rule['source_action_parameter']))]
            # JSON numeric IDs are compared to numeric URL bindings without inventing resource identities.
            if not sources:
                sources=[r for r in rows if r['_position']<action['_position'] and r.get('method')=='GET' and successful(r) and same_actor(r,action) and matches(rule['source_template'],path(r)) is not None and isinstance(r.get('response'),dict) and str(r['response'].get(rule.get('source_id_field','id')))==params.get(rule['source_action_parameter'])]
            sources=[r for r in sources if all(matches(rule['source_template'],path(r)).get(k)==v for k,v in sb.items())]
            source=sources[-1] if sources else None
            if not source or not container:rec['reason']='missing_source_or_container_preimage';continue
            after=[r for r in rows if r['_position']>action['_position'] and path(r)==path(container) and r.get('method')=='GET' and successful(r) and same_actor(r,action)]
            if not after:rec['reason']='missing_readback';continue
            read=after[0]
            # Do not attribute a batch of unobserved/intervening writes to one operation.
            if any(action['_position']<r['_position']<read['_position'] and r.get('method')!='GET' for r in rows):rec['reason']='intervening_mutation';continue
            if any(container['_position']<r['_position']<action['_position'] and r.get('method')!='GET' for r in rows):rec['reason']='container_preimage_not_current';continue
            if any(source['_position']<r['_position']<action['_position'] and path(r)==path(source) and r.get('method')!='GET' for r in rows):rec['reason']='source_preimage_not_current';continue
            try:
                scale=number((action.get('input') or {})[rule['scale_field']]);src=sums(source['response'],rule['source_items'],rule['quantity'],rule['source_keys']);before=sums(container['response'],rule['container_items'],rule['quantity'],rule['container_keys']);actual=sums(read['response'],rule['container_items'],rule['quantity'],rule['container_keys'])
            except (ValueError,KeyError,TypeError):rec['reason']='incomplete_quantity_or_key_values';continue
            if not src:rec['reason']='empty_source';continue
            expected={k:before.get(k,Decimal(0))+rule['sign']*scale*src.get(k,Decimal(0)) for k in set(before)|set(src)|set(actual)}
            differences=[dict(key=list(k),expected=float(v),observed=float(actual.get(k,0))) for k,v in expected.items() if abs(v-actual.get(k,0))>Decimal('1e-9')]
            rec.update(status='failed' if differences else 'passed',expected_total=float(sum(expected.values())),observed_total=float(sum(actual.values())))
            evaluated.append(dict(rule=rule,source=source,container=container,action=action,read=read,before=before,actual=actual,delta={k:rule['sign']*scale*v for k,v in src.items()}))
            if differences:
                o=obs[read['_position']];annotate(o,raw_contribution_discrepancy=True,raw_story_state_verified=True)
                check(o,'CONTRIB/RAW',rec['expected_total'],rec['observed_total'],[source,container,action],differences=differences,producer_verdict_used=False)
    cycles=defaultdict(list)
    for e in evaluated:cycles[(path(e['container']),path(e['source']),e['action'].get('session'))].append(e)
    for group in cycles.values():
        group.sort(key=lambda e:e['action']['_position']);delta=defaultdict(Decimal)
        for e in group:
            for k,v in e['delta'].items():delta[k]+=v
        if len(group)<2 or any(abs(v)>Decimal('1e-9') for v in delta.values()):continue
        first,last=group[0],group[-1]
        allowed={e['action']['_position'] for e in group}
        if any(first['container']['_position']<r['_position']<last['read']['_position'] and r.get('method')!='GET' and r['_position'] not in allowed for r in rows):continue
        failed=any(abs(first['before'].get(k,0)-last['actual'].get(k,0))>Decimal('1e-9') for k in set(first['before'])|set(last['actual']))
        audit.append(dict(family='CONTRIB-ROUNDTRIP',source=last['read']['source'],status='failed' if failed else 'passed'))
        if failed:
            o=obs[last['read']['_position']];annotate(o,raw_contribution_discrepancy=True,raw_story_state_verified=True)
            check(o,'CONTRIB/RAW-ROUNDTRIP',float(sum(first['before'].values())),float(sum(last['actual'].values())),[first['container'],*[e['action'] for e in group]],producer_verdict_used=False)
    return audit


def projection_ids(body,at,field):
    items=walk(body,at)
    if any(not isinstance(x,dict) or field not in x or type(x[field]) not in (str,int) for x in items):raise ValueError('Incomplete internal reference body')
    return [x[field] for x in items]


def raw_copies(rows,obs,spec,gap):
    audit=[]
    for rule in spec.get('copies',[]):
        for action in rows:
            if action.get('method')!=rule['method']:continue
            params=matches(rule['action_template'],path(action))
            if params is None:continue
            rec=dict(family='COPY',source=action['source'],status='not_evaluable');audit.append(rec)
            if not successful(action) or not isinstance(action.get('response'),dict):rec['reason']='action_not_accepted_or_no_body';continue
            if any(v not in params for v in rule['source_bindings'].values()):rec['reason']='action_binding_missing';continue
            source=latest_read(rows,rule['source_template'],{k:params[v] for k,v in rule['source_bindings'].items()},action['_position'],action)
            if not source or not isinstance(source.get('response'),dict):rec['reason']='source_preimage_missing';continue
            if any(source['_position']<r['_position']<action['_position'] and path(r)==path(source) and r.get('method')!='GET' for r in rows):rec['reason']='source_preimage_not_current';continue
            try:
                a=projection_ids(source['response'],rule['identity_items'],rule['field']);b=projection_ids(source['response'],rule['reference_items'],rule['field'])
            except ValueError:rec['reason']='source_projection_incomplete';continue
            if not a or not b or any(x not in a for x in b):
                rec['reason']='source_internal_reference_precondition_failed';gap('COPY_SOURCE_REFERENCE_PRECONDITION_NOT_ESTABLISHED',source=source['source']);continue
            if identity(action)==identity(source) or identity(action) is None:rec['reason']='new_copy_identity_not_observed';continue
            candidates=[action]
            candidates += [r for r in rows if r['_position']>action['_position'] and r.get('method')=='GET' and successful(r) and same_actor(r,action) and isinstance(r.get('response'),dict) and identity(r)==identity(action) and matches(rule['source_template'],path(r)) is not None][:1]
            candidates=[r for r in candidates if r is action or not any(action['_position']<w['_position']<r['_position'] and w.get('method')!='GET' for w in rows)]
            failures=0;compared=0
            for read in candidates:
                try:aa=projection_ids(read['response'],rule['identity_items'],rule['field']);bb=projection_ids(read['response'],rule['reference_items'],rule['field'])
                except ValueError:rec['reason']='copy_projection_incomplete';continue
                if not aa or not bb:rec['reason']='copy_projection_empty';continue
                compared+=1;bad=[x for x in bb if x not in aa]
                if bad:
                    failures+=1;o=obs[read['_position']];annotate(o,raw_copy_internal_reference_discrepancy=True,raw_story_state_verified=True)
                    check(o,'COPY/RAW',{'unresolved_references':[]},{'unresolved_references':bad},[source,action],identity_items=rule['identity_items'],reference_items=rule['reference_items'],producer_verdict_used=False)
            rec.update(status='failed' if failures else 'passed' if compared else 'not_evaluable',compared_bodies=compared,failed_bodies=failures)
    return audit


def raw_aggregate_moves(rows,obs,spec,gap):
    fixtures=creations(rows,spec);audit=[]
    for rule in spec.get('aggregates',[]):
        for move in rows:
            if move.get('method') not in ('PATCH','PUT','POST') or not successful(move) or not isinstance(move.get('input'),dict):continue
            child=[f for f in fixtures if f['entity']==rule['child'] and f['uri']==path(move) and f['row']['_position']<move['_position']]
            if len(child)!=1:continue
            field=rule['reference_field'];new_id=move['input'].get(field);old_id=(child[0]['row'].get('input') or {}).get(field)
            if new_id is None or old_id is None or equal_id(new_id,old_id) or not isinstance(move.get('response'),dict) or not equal_id(move['response'].get(field),new_id):continue
            parents={}
            for tag,pid in [('old',old_id),('new',new_id)]:
                fs=[f for f in fixtures if f['entity']==rule['parent'] and equal_id(f['pk'],pid) and f['row']['_position']<move['_position']]
                if len(fs)==1:parents[tag]=fs[0]
            if len(parents)!=2:continue
            reads=[r for r in rows if r.get('method')=='GET' and successful(r) and same_actor(r,move)]
            def parent_read(tag,before=True):
                candidates=[r for r in reads if matches(rule['parent_view'],path(r)) is not None and path(r).startswith(parents[tag]['uri']+'/') and (r['_position']<move['_position'] if before else r['_position']>move['_position'])]
                return (candidates[-1] if before else candidates[0]) if candidates else None
            old,new=parent_read('old'),parent_read('new');cv=[r for r in reads if r['_position']<move['_position'] and path(r).startswith(child[0]['uri']+'/') and matches(rule['child_view'],path(r)) is not None]
            if not old or not new or not cv:continue
            cv=cv[-1]
            # Qualify the additive hypothesis on a witnessed child creation delta.
            baselines=[r for r in reads if r['_position']<child[0]['row']['_position'] and path(r)==path(old)]
            postadd=[r for r in reads if child[0]['row']['_position']<r['_position']<move['_position'] and path(r)==path(old)]
            if not baselines or not postadd:continue
            try:
                value=vector(cv,rule['fields']);base=vector(baselines[-1],rule['fields']);added=vector(postadd[0],rule['fields'])
                if not close_vectors(added,{f:base[f]+value[f] for f in value},1):continue
                previous={'old':vector(old,rule['fields']),'new':vector(new,rule['fields'])}
            except ValueError:continue
            for tag,sign in [('old',-1),('new',1)]:
                after=parent_read(tag,False)
                if not after or any(move['_position']<r['_position']<after['_position'] and r.get('method')!='GET' for r in rows):continue
                try:actual=vector(after,rule['fields'])
                except ValueError:continue
                expected={f:previous[tag][f]+sign*value[f] for f in value};failed=not close_vectors(actual,expected,1)
                audit.append(dict(family='AGG',source=after['source'],status='failed' if failed else 'passed'))
                if failed:
                    o=obs[after['_position']];annotate(o,story_aggregate_after_move_mismatch=True,raw_story_state_verified=True,aggregate_side=tag)
                    if tag=='old':
                        new_after=parent_read('new',False)
                        if new_after and not any(move['_position']<r['_position']<new_after['_position'] and r.get('method')!='GET' for r in rows):
                            try:o['facts']['new_parent_aggregate_correct']=close_vectors(vector(new_after,rule['fields']),{f:previous['new'][f]+value[f] for f in value},1)
                            except ValueError:pass
                    check(o,'AGG/MOVE',{k:float(v) for k,v in expected.items()},{k:float(v) for k,v in actual.items()},[baselines[-1],postadd[0],old,new,cv,move],hypothesis_controlled=True)
    return audit


def evaluate(rows,observations,spec,gap):
    spec=canonical(spec or dict(entities={},projections=[],arithmetic=[]));obs={o['_position']:o for o in observations};reference=[];operations=[]
    for o in observations:o['semantic_origin']='shared-http-semantics/1'
    for r in rows:
        choices=[n for template,n in spec.get('detail_route_entities',{}).items() if matches(template,path(r)) is not None]
        if len(choices)==1:r['_entity']=choices[0]
    for group in epochs(rows,gap):
        # Each origin uses the identical functions, catalog facts and precondition policy.
        selected=[obs[r['_position']] for r in group]
        raw_references(group,selected,gap);raw_absent_errors(group,selected)
        if not spec.get('aggregates'):raw_aggregates(group,selected,gap)
        raw_projections(group,obs,spec,gap);raw_arithmetic(group,obs,spec,gap);raw_stale_context(group,obs,spec,gap)
        reference += ref_audit(group,obs,spec,gap)
        operations += raw_contributions(group,obs,spec,gap)+raw_copies(group,obs,spec,gap)+raw_aggregate_moves(group,obs,spec,gap)
    missing=[r for r in operations if r['status']=='not_evaluable']
    for r in missing:gap('SEMANTIC_OPERATION_NOT_EVALUABLE',family=r['family'],source=r['source'],reason=r.get('reason'))
    return dict(engine='shared-http-semantics/1',tool_neutral=True,producer_verdicts_used=False,judge_identity=dict(shared_engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),semantic_profile_sha256=spec.get('_profile_sha256')), 
        reference_preconditions=reference,reference_precondition_counts=dict(Counter(r['precondition'] for r in reference)),
        reference_postcondition_counts=dict(Counter(r['postcondition'] for r in reference)),operation_checks=operations,
        operation_counts={f:dict(Counter(r['status'] for r in operations if r['family']==f)) for f in sorted({r['family'] for r in operations})},
        transport_records=len(rows),independent_product_semantics_proven=False)
