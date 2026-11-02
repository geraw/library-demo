"""Bounded raw-evidence observations: relationships, views and numeric actions.
No product names, story identifiers, expected checks or bug catalog. Structural
inferences stay policy observations; only separate contract-qualified rules may
establish violations. No object bodies or identifiers are emitted in findings.
"""
from collections import OrderedDict,Counter
from decimal import Decimal,InvalidOperation
import re
from common import canonical,digest
from historical_providers import equal

MAX_ROWS=128
MAX_BODY=256*1024
MAX_NODES=4096
SAFE={'GET','HEAD','OPTIONS'}


def norm(x):
    x=re.sub(r'[^a-z0-9]','',x.lower())
    if x.endswith('id'):x=x[:-2]
    return x[:-1] if x.endswith('s') else x


def number(x):
    if type(x) not in (int,float):return None
    try:
        d=Decimal(str(x));return d if d.is_finite() else None
    except InvalidOperation:return None


def close(a,b):return abs(a-b)<=Decimal('1e-8')*max(Decimal(1),abs(a),abs(b))


def walk(body):
    stack=[(body,(),())];seen=0
    while stack and seen<MAX_NODES:
        value,path,parents=stack.pop();seen+=1
        if isinstance(value,dict):
            yield value,path,parents
            parent=parents+((value,path),)
            for k,v in value.items():
                if isinstance(v,(dict,list)):stack.append((v,path+(k,),parent))
        elif isinstance(value,list):
            for v in value:
                if isinstance(v,(dict,list)):stack.append((v,path+('*',),parents))


def metrics(body,quantity_only=False):
    result={}
    for obj,path,_ in walk(body):
        for k,v in obj.items():
            n=number(v)
            # ID/count/position metadata does not express an additive quantity.
            if n is None or k.lower().endswith('id') or norm(k) in ('uuid','key','position','order','count','index'):continue
            if quantity_only and not re.search(r'quantity|amount',k,re.I):continue
            key='/'.join(path+(k,));result[key]=result.get(key,Decimal(0))+n
    return result


def signature(row):
    return (row.get('origin'),row.get('actor'),type(row.get('epoch')).__name__,row.get('epoch'),row.get('case_id'))


def item_type(op):
    segments=op['path'].rstrip('/').split('/')
    if segments[-1].startswith('{') and len(segments)>1:return norm(segments[-2])
    return None


def same_entity(a,b):
    if not isinstance(a,dict) or not isinstance(b,dict) or 'id' not in a or not equal(a['id'],b.get('id')):return False
    # Avoid interpreting colliding IDs from unrelated entity types as a join.
    common=[k for k in a.keys()&b.keys() if k!='id' and not isinstance(a[k],(dict,list)) and a[k] is not None]
    return len(common)>=2 and sum(equal(a[k],b[k]) for k in common)>=2


class RelationalJudge:
    def __init__(self,context,state):
        self.context,self.state=context,state
        self.snapshots=OrderedDict();self.absences=OrderedDict();self.moves=[];self.scaled={};self.scope=None
        self.tick=0;self.last_write=0;self.last_time=None;self.ref_seen=set()
        self.audit={'observations':Counter(),'snapshot_evictions':0,'body_budget_skips':0,'supported_modes':['observational_references','nested_views','move_conservation','scaled_deltas','copy_internal_references']}

    def emit(self,prop,row,op,reason,witnesses,details):
        self.audit['observations'][reason]+=1
        self.state.verdict(prop,row,op,'policy_observation',reason,witnesses,
            details={'evidence_level':'structural_raw_evidence_observation','semantic_guarantee':None,
                     'background_concurrency_excluded':False,'root_cause_proven':False,**details})

    def store(self,row,op):
        self.snapshots[row['path']]=(row,op,self.tick)
        self.snapshots.move_to_end(row['path'])
        while len(self.snapshots)>MAX_ROWS:self.snapshots.popitem(last=False);self.audit['snapshot_evictions']+=1

    def check_references(self,row,op):
        # Only same post-mutation read interval. Historical absences are discarded
        # at every write; a later successful GET also invalidates its absence.
        for target,(absent,aop,at) in list(self.absences.items()):
            typ=item_type(aop)
            if not typ:continue
            identity=target.rstrip('/').rsplit('/',1)[-1]
            for current,cop,ct in list(self.snapshots.values()):
                if ct<self.last_write or current['path']==target or self.tick-ct>32:continue
                body=current.get('response')
                for obj,path,_ in walk(body):
                    fields=[k for k,v in obj.items() if k.lower()!='id' and norm(k)==typ and type(v) in (int,str) and str(v)==identity]
                    for f in fields:
                        schema=cop['responses'].get(str(current['status']),{})
                        for part in path+(f,):
                            schema=schema.get('items',{}) if part=='*' else schema.get('fields',{}).get(part,{})
                        if 'enum' in schema.get('constraints',{}):continue
                        key=(target,current['path'],'/'.join(path+(f,)))
                        if key in getattr(self,'ref_seen',set()):continue
                        if len(self.ref_seen)>=MAX_NODES:return
                        self.ref_seen.add(key)
                        self.emit('S4',current,cop,'REFERENCE_TO_OBSERVED_ABSENT_RESOURCE',[absent],
                            {'reference_pointer':'/'+ '/'.join(path+(f,)),
                             'binding_basis':'matching_field_and_resource_name_candidate',
                             'absence_status':absent['status'],'no_intervening_recorded_mutation':True})

    def copy_check(self,row,op):
        if op.get('semantic_action')!='copy' or not isinstance(row.get('response'),dict):return
        candidates=[x for p,x in self.snapshots.items() if row['path'].startswith(p.rstrip('/')+'/') and isinstance(x[0].get('response'),dict)]
        if not candidates:return
        before,_,_=max(candidates,key=lambda x:len(x[0]['path']))
        # Same-name reference values that were contained in one source array are
        # checked against that corresponding array in the returned copy.
        def containers(body):
            result={}
            for obj,path,_ in walk(body):
                if not path or path[-1]!='*':continue
                for k,v in obj.items():
                    if k.lower().endswith('id') and type(v) in (str,int):
                        result.setdefault((path,k),[]).append(v)
            return result
        b=containers(before['response']);a=containers(row['response'])
        reference_paths={path for obj,path,_ in walk(before['response']) if len(obj)==1}
        target_paths={path for obj,path,_ in walk(before['response']) if len(obj)>1}
        for (ref_path,key),refs in b.items():
            if ref_path not in reference_paths or ref_path in target_paths:continue
            targets=[p for (p,k),values in b.items() if k==key and p!=ref_path and p in target_paths and refs and all(v in values for v in refs)]
            if len(targets)!=1:continue
            target=targets[0];new_refs=a.get((ref_path,key));new_ids=a.get((target,key))
            if new_refs is None or new_ids is None:continue
            missing=[v for v in new_refs if v not in new_ids]
            if missing:
                self.emit('S4',row,op,'COPY_INTERNAL_REFERENCE_NOT_IN_COPIED_TARGETS',[before],
                    {'reference_pointer':'/'+ '/'.join(ref_path+(key,)),
                     'target_pointer':'/'+ '/'.join(target+(key,)),
                     'unresolved_count':len(missing),'binding_basis':'unique_source_value_inclusion_candidate'})

    def scaling(self,row,op,before):
        if row['method']!='POST' or not isinstance(row.get('input'),dict) or not isinstance(row.get('response'),dict):return
        nums={k:number(v) for k,v in row['input'].items() if number(v) is not None}
        if len(nums)!=1 or len(row['input'])!=1:return
        scale_field,factor=next(iter(nums.items()))
        if factor==0 or not before:return
        bm,am=metrics(before['response'],True),metrics(row['response'],True)
        delta={k:am[k]-bm[k] for k in bm.keys()&am.keys()}
        # All successful writes invalidate a series except repetitions of this
        # exact action URI and operation. Factors and metrics remain candidates.
        key=(op['key'],row['path'],scale_field)
        previous=self.scaled.get(key)
        if previous and previous['last_write']==self.last_write-1 and previous['factor']!=factor:
            common=delta.keys()&previous['delta'].keys()
            bad=[k for k in common if previous['delta'][k]!=0 and not close(delta[k]*previous['factor'],previous['delta'][k]*factor)]
            if bad:self.emit('S6',row,op,'SCALED_ACTION_NONLINEAR_DELTA',[previous['before'],previous['row'],before],
                {'metric_pointers':sorted(bad),'scale_field':scale_field,
                 'linearity_guarantee':'not_declared','scope':'two_observed_deltas_no_other_recorded_write'})
        self.scaled={key:{'before':before,'row':row,'factor':factor,'delta':delta,'last_write':self.last_write}}

    def prepare_move(self,row,op,before):
        if not before or not isinstance(before.get('response'),dict) or not isinstance(row.get('input'),dict):return
        old=before['response'];new=row.get('response')
        if not isinstance(new,dict):return
        # A state-bearing successful response provides evidence of an applied
        # move. An ignored update is separately observable in the view checker.
        changed=[k for k,v in row['input'].items() if type(v) in (int,str) and k in old and not equal(v,old[k])]
        views=list(self.snapshots.values())
        for field in changed:
            source,dest=str(old[field]),str(row['input'][field])
            own=[x for p,x in self.snapshots.items() if p.startswith(row['path'].rstrip('/')+'/') and isinstance(x[0].get('response'),dict)]
            for child,cop,_ in own:
                suffix=child['path'].rstrip('/').rsplit('/',1)[-1]
                olds=[x for p,x in self.snapshots.items() if source in p.split('/') and p.rstrip('/').endswith('/'+suffix) and x[1]['key']!=cop['key']]
                news=[x for p,x in self.snapshots.items() if dest in p.split('/') and p.rstrip('/').endswith('/'+suffix) and x[1]['key']!=cop['key']]
                if len(olds)!=1 or len(news)!=1 or olds[0][1]['key']!=news[0][1]['key']:continue
                if not equal(new.get(field),row['input'][field]):continue
                cm=metrics(child['response']);om=metrics(olds[0][0]['response']);nm=metrics(news[0][0]['response'])
                common=cm.keys()&om.keys()&nm.keys()
                if common:self.moves.append({'kind':'aggregate','write':row,'op':op,'field':field,'child':child,
                    'entity_before':before,'old':olds[0][0],'new':news[0][0],'metrics':(cm,om,nm),'fields':common,'after':{}})
            # Compare nested view membership under a parent that matches a
            # requested reference. The parent relation itself is only inferred.
            if not (norm(field).endswith('bucket') or norm(field).endswith('parent') or any(norm(field).endswith(norm(seg)) for seg in op['path'].split('/') if seg and '{' not in seg)):
                # Generic *_id relations are also eligible, not ordinary titles.
                if not field.lower().endswith('id'):continue
            for view,vop,_ in views:
                if view['path']==before['path']:continue
                matches=[(obj,path,parents) for obj,path,parents in walk(view.get('response')) if same_entity(obj,old) and len(parents)>=1]
                if matches:self.moves.append({'kind':'view','write':row,'op':op,'before':before,'view':view,'view_op':vop,'field':field,'wanted':row['input'][field]})

    def after_move(self,row,op):
        for move in self.moves:
            if move['kind']=='aggregate' and row['path'] in (move['old']['path'],move['new']['path']):
                move['after'][row['path']]=row
                if len(move['after'])!=2:continue
                a,b=move['after'][move['old']['path']],move['after'][move['new']['path']]
                am,bm=metrics(a['response']),metrics(b['response']);cm,om,nm=move['metrics']
                fields=move['fields']&am.keys()&bm.keys()
                bad=[f for f in fields if cm[f]!=0 and (not close(am[f],om[f]-cm[f]) or not close(bm[f],nm[f]+cm[f]))]
                if bad:self.emit('S6',row,op,'MOVE_AGGREGATE_TRANSFER_MISMATCH',[move['child'],move['old'],move['new'],move['entity_before'],move['write'],a,b],
                    {'metric_pointers':sorted(bad),'moved_field':move['field'],'additive_semantics':'inferred_same_metric_routes_not_guaranteed'})
                move['after'].clear();move['fields']=set()
            if move['kind']=='view' and row['path']==move['view']['path']:
                found=[]
                for obj,path,parents in walk(row.get('response')):
                    if not same_entity(obj,move['before']['response']):continue
                    # Parent object identity is a concrete membership witness.
                    ids=[p.get('id') for p,_ in parents if 'id' in p]
                    if ids and move['wanted'] not in ids and obj.get(move['field'])!=move['wanted']:found.append(path)
                if found:self.emit('S6',row,op,'MOVED_ENTITY_REMAINS_UNDER_OTHER_PARENT',[move['before'],move['view'],move['write']],
                    {'reference_field':move['field'],'membership_pointers':['/'+'/'.join(p) for p in found],
                     'binding_basis':'nested_identity_membership_candidate','view_policy':'not_declared'})

    def consume(self,row,op):
        self.tick+=1
        # Limit stale joins as well as total memory. A window is not an isolation guarantee.
        for path,(_,_,at) in list(self.snapshots.items()):
            if self.tick-at>32:self.snapshots.pop(path)
        if self.tick-self.last_write>32:self.moves=[]
        scope=signature(row)
        if scope!=self.scope:
            self.snapshots.clear();self.absences.clear();self.moves=[];self.scaled={};self.ref_seen=set();self.scope=scope
        stamp=row.get('observed') if row.get('observed') is not None else row.get('started')
        ordered=stamp is not None and (self.last_time is None or stamp>=self.last_time)
        strict=not self.state.precondition(row)
        self.last_time=stamp
        if not ordered and not strict:
            self.snapshots.clear();self.absences.clear();self.moves=[];self.scaled={};return
        if not row.get('actor') or self.state.capture.get('_contradicted_serial') or not op:
            if row['method'] not in SAFE:self.snapshots.clear();self.absences.clear();self.moves=[];self.scaled={}
            return
        if len(canonical(row.get('response'))) > MAX_BODY or len(canonical(row.get('input'))) > MAX_BODY:
            self.audit['body_budget_skips']+=1;self.snapshots.clear();self.moves=[];self.absences.clear();self.scaled={};return
        if row['method'] not in SAFE:
            self.last_write=self.tick;self.absences.clear();self.ref_seen=set();self.moves=[]
            # scaling series tracks ordinal mutation count, not raw HTTP count.
            self.write_number=getattr(self,'write_number',0)+1
            before=self.snapshots.get(row['path'],(None,None,None))[0]
            if 200<=(row['status'] or 0)<300 and row['status']!=202:
                self.copy_check(row,op)
                targets=[v[0] for p,v in self.snapshots.items() if row['path'].startswith(p.rstrip('/')+'/') and isinstance(v[0].get('response'),dict) and isinstance(row.get('response'),dict) and equal(v[0]['response'].get('id'),row['response'].get('id')) and v[0]['response'].get('id') is not None]
                saved_last=self.last_write;self.last_write=self.write_number
                self.scaling(row,op,max(targets,key=lambda r:len(r['path'])) if targets else None)
                self.last_write=saved_last
                if row['method'] in ('PUT','PATCH','POST') and before:self.prepare_move(row,op,before)
                self.moves=self.moves[:MAX_ROWS]
                if isinstance(row.get('response'),dict) and 'id' in row['response'] and (row['method'] in ('PUT','PATCH') or op.get('declared_write_role')=='update'):self.store(row,op)
            else:self.scaled={}
            return
        if row['method']!='GET' or row['query_present']:return
        if row['status'] in (404,410) and item_type(op):self.absences[row['path']]=(row,op,self.tick)
        elif row['status']==200 and row.get('response_available'):
            self.absences.pop(row['path'],None)
            self.after_move(row,op);self.store(row,op)
        while len(self.absences)>MAX_ROWS:self.absences.popitem(last=False)
        self.check_references(row,op)

    def finish(self):
        return {**self.audit,'observations':dict(self.audit['observations']),'snapshot_limit':MAX_ROWS,'max_body_bytes':MAX_BODY,'max_walk_nodes':MAX_NODES}
