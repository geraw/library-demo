"""Limited observations from adjacent legacy captures with unknown isolation.
These never establish atomicity guarantees or become confirmed violations.
"""
from collections import deque
from legacy_state import failed_update, project_read
from common import canonical
from state_semantics import MAX_STATE_BODY_BYTES


class LocalSequenceJudge:
    def __init__(self, state):
        self.state = state
        self.rows = deque(maxlen=3)
        self.observations = 0

    def consume(self, row, op):
        if (row['method'] == 'GET' and not row.get('response_available')) or len(canonical(row.get('response'))) > MAX_STATE_BODY_BYTES:
            self.rows.clear(); return
        self.rows.append((row,op))
        if len(self.rows) != 3:
            return
        (before,bop),(write,wop),(after,aop) = self.rows
        if not all((bop,wop,aop)) or [r['method'] for r in (before,write,after)] not in (['GET','PATCH','GET'],['GET','PUT','GET']):
            return
        if not 400 <= (write['status'] or 0) < 600 or before['status'] != 200 or after['status'] != 200:
            return
        # The strict evaluator already handles fully qualified captures.
        if not self.state.precondition(write):
            return
        rows = (before,write,after)
        if self.state.capture.get('_contradicted_serial') or any(r['query_present'] for r in rows):
            return
        if not write.get('actor') or len({self.state.scope(r) for r in rows}) != 1:
            return
        times = [r.get('observed') for r in rows]
        if any(t is None for t in times) or not times[0] < times[1] < times[2]:
            return
        binding = self.state.bindings.get(wop['key'],{})
        if binding.get('status') != 'structural_candidate' or binding['read_operation'] != bop['key'] or bop['key'] != aop['key']:
            return
        b,w,a = before.get('response'),write.get('input'),after.get('response')
        if not all(isinstance(x,dict) for x in (b,w,a)) or not write.get('input_available'):
            return
        if len(canonical(w)) > MAX_STATE_BODY_BYTES:
            return
        b,a = project_read(b,binding),project_read(a,binding)
        fields = [f for f in binding['fields'] if f in b and f in w and f in a]
        if not fields:
            return
        facts = failed_update(write['status'],{f:b[f] for f in fields},{f:w[f] for f in fields},{f:a[f] for f in fields})
        if facts.get('atomicity') not in ('partial','committed_despite_error'):
            return
        self.observations += 1
        self.state.verdict('S5',write,wop,'policy_observation','OBSERVED_FAILED_WRITE_'+facts['atomicity'].upper(),
                           [before,after],fields,binding,
                           {'outcome':facts['atomicity'],'field_states':facts['field_states'],
                            'historical_provider':'ATOM-1-2', 'background_concurrency_excluded':False,
                            'capture_completeness_established':False,'causation_proven':False,
                            'evidence_level':'adjacent_raw_sequence_observation',
                            'scope':'requested_comparable_fields_only',
                            'full_resource_atomicity_proven':False})

    def finish(self):
        return {'observations':self.observations,'maximum_retained_records':3,
                'claims_isolation_or_completeness':False}
