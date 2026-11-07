"""Observe collection changes after rejected creation, using original snapshots.
Only consecutive GET(array), POST(4xx/5xx), GET(array) on the same URI.
No query/pagination interpretation, count-only summaries, or producer verdicts.
"""
from common import canonical, digest
from historical_providers import equal
from state_semantics import MAX_STATE_BODY_BYTES


class RejectedCreateJudge:
    def __init__(self, context, state):
        self.context, self.state = context, state
        self.previous = None
        self.pending = None
        self.audit = {'rejected_creates': 0, 'evaluated': 0, 'missing_preimage': 0}
        self.gets = {o['path']: o for o in context['operations'] if o['method'] == 'GET'}

    def emit(self, row, op, reason, value='not_evaluable', witnesses=(), details=None):
        policy = self.context.get('semantic_policies', {}).get('rejected_create_no_effect')
        self.state.verdict('S5', row, op, value, reason, witnesses,
                           binding={'provenance': [policy['pointer']] if policy else []},
                           details={'semantic_guarantee': policy, **(details or {})})

    def consume(self, row, op):
        pending, self.pending = self.pending, None
        if pending:
            before, write, write_op, get_op, fields = pending
            gap = self.state.precondition(row)
            if (not op or op['key'] != get_op['key'] or
                    self.state.scope(row) != self.state.scope(write)):
                gap = gap or 'COLLECTION_READBACK_NOT_ADJACENT_IN_SAME_SCOPE'
            if row['status'] != 200 or not row.get('response_available') or not isinstance(row.get('response'), list):
                gap = gap or 'COLLECTION_READBACK_ARRAY_UNAVAILABLE'
            if gap:
                self.emit(write, write_op, gap, witnesses=[before])
            elif len(canonical(row['response'])) > MAX_STATE_BODY_BYTES:
                self.emit(write, write_op, 'COLLECTION_READBACK_STATE_BODY_BUDGET', witnesses=[before])
            elif not all(isinstance(x, dict) for x in before['response'] + row['response']):
                self.emit(write, write_op, 'COLLECTION_ITEM_OBJECT_REQUIRED', witnesses=[before,row])
            else:
                # Strict multiset inclusion: every preimage remains byte-equivalent.
                # A matching object added afterwards is an observable state effect.
                remaining = list(row['response'])
                retained = True
                for item in before['response']:
                    match = next((i for i,x in enumerate(remaining) if equal(x,item)), None)
                    if match is None:
                        retained = False; break
                    remaining.pop(match)
                added = [x for x in remaining if all(f in x and equal(x[f],write['input'][f]) for f in fields)] if retained else []
                policy = self.context.get('semantic_policies', {}).get('rejected_create_no_effect') if get_op.get('collection_complete') else None
                self.audit['evaluated'] += 1
                if added:
                    self.emit(write,write_op,'REJECTED_CREATE_STATE_APPEARED',
                              'violation' if policy else 'policy_observation',[before,row],
                              {'matching_added_count':len(added),'matched_fields':fields,'collection_completeness_declared':get_op.get('collection_complete',False),
                               'evidence_level':'contract_violation' if policy else 'state_effect_without_contract_guarantee'})
                elif retained and not remaining:
                    self.emit(write,write_op,'REJECTED_CREATE_COLLECTION_UNCHANGED','consistent',[before,row])
                else:
                    self.emit(write,write_op,'COLLECTION_CHANGE_NOT_ATTRIBUTABLE_TO_REQUEST',witnesses=[before,row])
        if op and op['method'] == 'POST' and op['declared_write_role']['value'] == 'create' and 400 <= (row['status'] or 0) < 600:
            self.audit['rejected_creates'] += 1
            before = self.previous
            get = self.gets.get(op['path'])
            gap = self.state.precondition(row)
            items = (get or {}).get('responses',{}).get('200',{}).get('items',{})
            req_fields = (op.get('request_schema') or {}).get('fields',{})
            if not gap and not (before and get and before['method']=='GET' and before['status']==200
                    and self.state.scope(before)==self.state.scope(row) and not self.state.precondition(before)
                    and before.get('response_available') and isinstance(before.get('response'),list)):
                gap = 'PRECREATE_COLLECTION_SNAPSHOT_UNAVAILABLE'
            if not gap and len(canonical(before['response'])) > MAX_STATE_BODY_BYTES:
                gap = 'COLLECTION_PREIMAGE_STATE_BODY_BUDGET'
            fields = sorted(row['input']) if isinstance(row.get('input'),dict) else []
            if not fields or not row.get('input_available') or not all(
                f in req_fields and f in items.get('fields',{}) and
                items['fields'][f].get('constraints',{}).get('type') in ([req_fields[f].get('constraints',{}).get('type')] + req_fields[f].get('scalar_alternative_types',[])) and
                not any(req_fields[f].get('constraints',{}).get(k) or items['fields'][f].get('constraints',{}).get(k) for k in ('readOnly','writeOnly'))
                for f in fields):
                gap = gap or 'CREATE_COLLECTION_FIELD_BINDING_UNAVAILABLE'
            if gap:
                self.audit['missing_preimage'] += 1
                self.emit(row,op,gap)
            else:
                self.pending = (before,row,op,get,fields)
        self.previous = row

    def finish(self):
        if self.pending:
            before,row,op,_,_ = self.pending
            self.emit(row,op,'COLLECTION_READBACK_NOT_RETAINED',witnesses=[before])
        return self.audit
