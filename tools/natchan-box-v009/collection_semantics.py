"""Contract-qualified equality filters and collateral deletion over complete lists."""
import re
from urllib.parse import unquote
from historical_providers import evaluate
from legacy_state import qualified_context
from common import canonical
from state_semantics import MAX_STATE_BODY_BYTES


def identity_field(schema):
    fields=schema.get('fields',{})
    ids=[k for k,v in fields.items() if k.lower() in ('id','uuid','key') and v.get('constraints',{}).get('type') in ('string','integer')]
    return ids[0] if len(ids)==1 else None


def query_scalar(value,schema):
    kind=schema.get('constraints',{}).get('type')
    if kind=='integer' and re.fullmatch(r'-?[0-9]+',value) and len(value)<20:return int(value)
    if kind=='string':return value
    if kind=='boolean' and value in ('true','false'):return value=='true'
    return None


class CollectionJudge:
    def __init__(self,context,state):
        self.context,self.state=context,state
        self.previous=None;self.pending=None
        self.reads={o['path'].rstrip('/'):o for o in context['operations'] if o['method']=='GET' and o['responses'].get('200',{}).get('constraints',{}).get('type')=='array'}
        self.audit={'filter_checks':0,'delete_checks':0,'missing_evidence':0}

    def emit(self,prop,row,op,value,reason,witnesses=(),details=None):
        pointers=[op['provenance']+'/description']
        policy=self.context.get('semantic_policies',{}).get('deletion_preserves_others')
        if prop=='S4' and policy:pointers.append(policy['pointer'])
        self.state.verdict(prop,row,op,value,reason,witnesses,binding={'provenance':pointers},details=details)

    def consume(self,row,op):
        pending,self.pending=self.pending,None
        if pending:
            before,write,wop,get,identity,target=pending
            gap=self.state.precondition(row)
            if not (op and op['key']==get['key'] and row['path']==before['path'] and self.state.scope(row)==self.state.scope(before)):
                gap=gap or 'DELETE_COLLECTION_READBACK_NOT_ADJACENT'
            if row['status']!=200 or not isinstance(row.get('response'),list) or not row.get('response_available'):
                gap=gap or 'DELETE_COLLECTION_READBACK_UNAVAILABLE'
            if not gap and len(canonical(row['response']))>MAX_STATE_BODY_BYTES:gap='COLLECTION_BODY_BUDGET'
            if not gap and not all(isinstance(x,dict) and identity in x and type(x[identity]) in (int,str) for x in row['response']):gap='COLLECTION_IDENTITY_UNAVAILABLE'
            if gap:
                self.audit['missing_evidence']+=1;self.emit('S4',write,wop,'not_evaluable',gap,[before])
            else:
                expected=[x[identity] for x in before['response'] if str(x[identity])!=target]
                actual=[x[identity] for x in row['response']]
                if len(set(map(str,actual)))!=len(actual):
                    self.emit('S4',write,wop,'not_evaluable','DUPLICATE_COLLECTION_IDENTITIES',[before,row])
                else:
                    facts=evaluate({'family':'VIEW','source':'raw-http','expected_ids':expected,'actual_ids':actual,'membership_required':True,
                      'context':dict(qualified_context(),view_scope_verified=True,actor_scope_verified=True)})['facts']
                    policy=self.context.get('semantic_policies',{}).get('deletion_preserves_others')
                    self.audit['delete_checks']+=1
                    self.emit('S4',write,wop,('violation' if policy and get.get('collection_complete') else 'policy_observation') if facts['view_missing'] else 'consistent',
                      'DELETE_REMOVED_NON_TARGET_RESOURCES' if facts['view_missing'] else 'DELETE_PRESERVED_NON_TARGET_RESOURCES',[before,row],
                      {'missing_non_target_count':sum(x not in actual for x in expected),'historical_provider':'VIEW','semantic_guarantee':policy,
                       'collection_completeness_declared':bool(get.get('collection_complete'))})
        if not op:self.previous=row;return
        if row['method']=='GET' and row['query_present'] and op.get('conjunctive_equality_filters'):
            all_pairs=row.get('query_pairs',[])
            fields=op['responses'].get('200',{}).get('items',{}).get('fields',{})
            params={p['name']:p['schema'] for p in op['parameters'] if p['in']=='query'}
            pairs=[(k,v) for k,v in all_pairs if k in params and k in fields]
            names=[k for k,v in pairs]
            extra=sorted({k for k,v in all_pairs if k not in names})
            if row['status']==200 and isinstance(row.get('response'),list) and row.get('response_available'):
                if not pairs or len(names)!=len(set(names)):
                    self.emit('S6',row,op,'not_evaluable','FILTER_BINDING_OR_DUPLICATE_QUERY_UNSUPPORTED')
                elif len(canonical(row['response']))>MAX_STATE_BODY_BYTES:self.emit('S6',row,op,'not_evaluable','COLLECTION_BODY_BUDGET')
                else:
                    values={k:query_scalar(v,params[k]) for k,v in pairs}
                    if any(v is None for v in values.values()):self.emit('S6',row,op,'not_evaluable','FILTER_VALUE_NOT_COMPARABLE')
                    elif not all(isinstance(x,dict) and all(k in x for k in values) for x in row['response']):self.emit('S6',row,op,'not_evaluable','FILTER_RESPONSE_FIELDS_MISSING')
                    else:
                        wrong=sum(any(type(x[k]) is not type(v) or x[k]!=v for k,v in values.items()) for x in row['response'])
                        self.audit['filter_checks']+=1
                        self.emit('S6',row,op,'violation' if wrong else 'consistent','CONJUNCTIVE_FILTER_VIOLATION' if wrong else 'RETURNED_ITEMS_SATISFY_FILTERS',
                          details={'mismatching_items':wrong,'filter_fields':sorted(values),'scope':'returned_items_only_not_completeness','additional_query_names':extra,'basis':'explicit_conjunction_requires_each_known_predicate_even_with_additional_parameters'})
        if row['method']=='DELETE' and row['status'] in (200,204):
            m=re.fullmatch(r'(.*)/\{[^/{}]+\}/?',op['path'])
            get=self.reads.get(m[1]) if m else None
            before=self.previous
            if get:
                identity=identity_field(get['responses']['200'].get('items',{}))
                gap=self.state.precondition(row)
                # This bounded check requires an explicit complete-collection promise.
                if any(p['in']=='query' for p in get['parameters']) and not get.get('collection_complete'):gap=gap or 'COLLECTION_COMPLETENESS_NOT_DECLARED'
                prefix=row['path'].rstrip('/').rsplit('/',1)[0]
                target=unquote(row['path'].rstrip('/').rsplit('/',1)[1])
                if not (before and before['method']=='GET' and before['path'].rstrip('/')==prefix and before['status']==200 and
                   self.state.scope(before)[0]==self.state.scope(row)[0] and self.state.scope(before)[2:]==self.state.scope(row)[2:] and not self.state.precondition(before)
                   and isinstance(before.get('response'),list) and before.get('response_available') and identity and
                   all(isinstance(x,dict) and type(x.get(identity)) in (int,str) for x in before['response'])):
                    gap=gap or 'PREDELETE_COMPLETE_COLLECTION_UNAVAILABLE'
                if not gap and len({(type(x[identity]).__name__,str(x[identity])) for x in before['response']})!=len(before['response']):gap='DUPLICATE_COLLECTION_IDENTITIES'
                if not gap and len(canonical(before['response']))>MAX_STATE_BODY_BYTES:gap='COLLECTION_BODY_BUDGET'
                if gap:self.audit['missing_evidence']+=1;self.emit('S4',row,op,'not_evaluable',gap)
                else:self.pending=(before,row,op,get,identity,target)
        self.previous=row

    def finish(self):
        if self.pending:
            before,row,op,*_=self.pending;self.emit('S4',row,op,'not_evaluable','DELETE_COLLECTION_READBACK_NOT_RETAINED',[before])
        return self.audit
