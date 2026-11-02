"""Bounded, raw-HTTP state checks. No product names, stories or known-bug signatures."""
from collections import OrderedDict
from datetime import datetime

from common import canonical, digest
from legacy_state import failed_update, roundtrip, project_read

MAX_SNAPSHOTS = 128
MAX_STATE_BODY_BYTES = 64 * 1024
SAFE = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}


def scalar_valid(value, schema):
    """Supported constraint subset; None means this schema/value is not interpretable here."""
    if not schema or schema.get('status') != 'declared':
        return None
    c = schema.get('constraints', {})
    kind = c.get('type')
    if value is None and c.get('nullable'):
        if 'enum' in c:
            if not isinstance(c['enum'], list):
                return None
            if None not in c['enum']:
                return ['enum']
        return ['const'] if 'const' in c and c['const'] is not None else []
    types = {'string': isinstance(value, str), 'boolean': type(value) is bool,
             'number': type(value) in (int, float),
             'integer': type(value) is int or (type(value) is float and value.is_integer())}
    if not isinstance(kind, str) or kind not in types:
        return None
    if not types[kind]:
        return ['type']
    problems = []
    if 'enum' in c:
        if not isinstance(c['enum'], list):
            return None
        if not any(equal(value, v, {}) for v in c['enum']):
            problems.append('enum')
    if 'const' in c and not equal(value, c['const'], {}):
        problems.append('const')
    if kind == 'string':
        for key, violated in (('minLength', lambda n: len(value) < n), ('maxLength', lambda n: len(value) > n)):
            if key in c:
                if type(c[key]) is not int or c[key] < 0:
                    return None
                if violated(c[key]):
                    problems.append(key)
    if kind in ('integer', 'number'):
        for key, violated in (('minimum', lambda n: value < n), ('maximum', lambda n: value > n)):
            if key in c:
                if type(c[key]) not in (int, float):
                    return None
                exclusive = c.get('exclusive' + key.capitalize()) is True
                if violated(c[key]) or (exclusive and value == c[key]):
                    problems.append(key)
        for key, violated in (('exclusiveMinimum', lambda n: value <= n), ('exclusiveMaximum', lambda n: value >= n)):
            if key in c and type(c[key]) is not bool:
                if type(c[key]) not in (int, float):
                    return None
                if violated(c[key]):
                    problems.append(key)
    return problems


def equal(a, b, constraints):
    if type(a) is bool or type(b) is bool:
        return type(a) is type(b) and a == b
    if type(a) in (int, float) and type(b) in (int, float):
        return a == b
    if constraints.get('format') == 'date-time' and isinstance(a, str) and isinstance(b, str):
        try:
            x = datetime.fromisoformat(a.replace('Z', '+00:00'))
            y = datetime.fromisoformat(b.replace('Z', '+00:00'))
            if x.tzinfo and y.tzinfo:
                return x == y
        except ValueError:
            pass
    return type(a) is type(b) and a == b


class StateJudge:
    def __init__(self, context, capture, emit):
        self.context = context
        self.capture = capture or {}
        self.emit = emit
        self.bindings = context.get('write_read_bindings', {})
        self.read_ops = {b['read_operation'] for b in self.bindings.values() if b['status'] == 'structural_candidate'}
        self.snapshots = OrderedDict()
        self.pending = None
        self.evictions = 0
        self.current_epoch = None
        self.unmapped_mutations = 0

    def scope(self, row):
        return (row.get('origin'), row['path'], row.get('actor'),
                type(row.get('epoch')).__name__, row.get('epoch'), row.get('case_id'))

    def precondition(self, row):
        if self.capture.get('_contradicted_serial'):
            return 'CAPTURE_INTERVALS_OVERLAP_OR_ARE_OUT_OF_ORDER'
        if not (self.capture.get('complete') is True and self.capture.get('exclusive') is True and
                self.capture.get('ordering') == 'serial'):
            return 'COMPLETE_ISOLATED_SERIAL_CAPTURE_NOT_DECLARED'
        if not row.get('actor'):
            return 'CAPTURE_ACTOR_NOT_ESTABLISHED'
        if row.get('epoch') is None:
            return 'CAPTURE_RESET_EPOCH_NOT_ESTABLISHED'
        if row['query_present']:
            return 'QUERY_SEMANTICS_NOT_INTERPRETED'
        return None

    def verdict(self, prop, row, op, value, reason, witnesses=(), fields=None, binding=None, details=None):
        pointers = [op['provenance']]
        if prop == 'S3':
            schema = op.get('request_schema') or {}
            if schema.get('provenance'):
                pointers.append(schema['provenance'])
            for f in fields or []:
                if f in schema.get('fields', {}):
                    pointers.append(schema['fields'][f]['provenance'])
        if binding:
            pointers += binding.get('provenance', [])
            for f in fields or []:
                if f in binding.get('fields', {}):
                    pointers += [binding['fields'][f]['write_schema']['provenance'],
                                 binding['fields'][f]['read_schema']['provenance']]
        source = [row['source'], *(w['source'] for w in witnesses)]
        source = list({digest(canonical(s)): s for s in source}.values())
        v = {'property': prop, 'value': value, 'reason': reason,
             'operation': op['key'], 'entity': None, 'field': None,
             'status': row['status'], 'input_class': row['input_class'],
             'evidence': source, 'knowledge': [{'contract_sha256': self.context['contract_sha256'], 'pointer': p}
                                              for p in sorted(set(pointers))],
             'scope': 'bounded_raw_http_state' if prop != 'S3' else 'supported_json_scalar_constraints',
             'root_cause_proven': False, 'fields': fields or [], 'details': details or {}}
        if prop == 'S1' and not (details or {}).get('lifecycle'):
            v['assumptions'] = ['SAME_NAMED_WRITABLE_READABLE_FIELD_IS_PERSISTED']
        if prop == 'S5':
            v['atomicity_guarantee'] = (details or {}).get('semantic_guarantee') or 'not_established_from_contract'
        self.emit(v)

    def constraint_input(self, row, op):
        schema = op.get('request_schema') or {}
        if schema.get('status') != 'declared' or not schema.get('fields'):
            return {'reason': 'REQUEST_SCHEMA_NOT_INTERPRETABLE'}
        if not row.get('input_available') or not isinstance(row.get('input'), dict):
            return {'reason': 'REQUEST_JSON_OBJECT_NOT_RETAINED'}
        invalid, checked, unsupported = {}, [], []
        fields = schema['fields']
        for name, field in sorted(fields.items()):
            if name not in row['input']:
                if name in schema.get('required', []):
                    invalid[name] = ['required']
                continue
            problems = scalar_valid(row['input'][name], field)
            if problems is None:
                unsupported.append(name)
            else:
                checked.append(name)
                if problems:
                    invalid[name] = problems
        if not checked and not invalid:
            return {'reason': 'NO_SUPPORTED_SENT_SCALAR_CONSTRAINTS', 'unsupported_fields': unsupported}
        return {'invalid': invalid, 'checked_fields': checked, 'unsupported_fields': unsupported}

    def constraints(self, row, op, check, after=None):
        if 'reason' in check:
            self.verdict('S3', row, op, 'not_evaluable', check['reason'])
            return
        invalid = check['invalid']
        if not invalid:
            self.verdict('S3', row, op, 'consistent', 'INPUT_WITHIN_EVALUATED_CONSTRAINT_SUBSET',
                         fields=check['checked_fields'], details=check)
            return
        witnesses = [after] if after else []
        status = row['status'] or 0
        if 400 <= status < 500:
            value, reason = 'consistent', 'INVALID_INPUT_REJECTED'
        elif 200 <= status < 300:
            value, reason = 'policy_observation', 'INVALID_INPUT_ACCEPTED_STORAGE_UNVERIFIED'
            if after and after['status'] == 200 and after.get('response_available') and isinstance(after.get('response'), dict):
                stored_invalid = {}
                for name in invalid:
                    if name not in after['response']:
                        continue
                    field = op['request_schema']['fields'][name]
                    problems = scalar_valid(after['response'][name], field)
                    if problems:
                        stored_invalid[name] = problems
                if stored_invalid:
                    check = dict(check, stored_invalid=stored_invalid)
                    value, reason = 'violation', 'DECLARED_CONSTRAINT_VIOLATION_OBSERVED_IN_READBACK'
                else:
                    reason = 'INVALID_INPUT_ACCEPTED_STORAGE_NOT_SHOWN_INVALID'
        else:
            value, reason = 'not_evaluable', 'INVALID_INPUT_NO_DEFINITIVE_REJECTION_OR_STORAGE'
        self.verdict('S3', row, op, value, reason, witnesses, sorted(invalid), details=check)

    def finish_pending(self, reason, after=None):
        p, self.pending = self.pending, None
        if not p:
            return
        row, op, binding = p['row'], p['op'], p['binding']
        witnesses = ([p['before']] if p['before'] else []) + ([after] if after else [])
        if p['deferred_s3']:
            self.constraints(row, op, p['constraints'], after if reason is None else None)
        if reason:
            self.verdict(p['property'], row, op, 'not_evaluable', reason, witnesses, binding=binding)
            return
        if after['status'] != 200 or not after.get('response_available') or not isinstance(after.get('response'), dict):
            self.verdict(p['property'], row, op, 'not_evaluable', 'READBACK_JSON_OBJECT_UNAVAILABLE', witnesses, binding=binding)
            return
        if len(canonical(after['response'])) > MAX_STATE_BODY_BYTES:
            self.verdict(p['property'], row, op, 'not_evaluable', 'READBACK_STATE_BODY_BUDGET', witnesses, binding=binding)
            return
        sent = row['input']
        fields = [f for f in binding['fields'] if f in sent]
        eligible = [f for f in fields if scalar_valid(sent[f], binding['fields'][f]['write_schema']) is not None]
        if not eligible:
            self.verdict(p['property'], row, op, 'not_evaluable', 'NO_SUPPORTED_COMPARABLE_SENT_FIELDS', witnesses, binding=binding)
            return
        current = project_read(after['response'], binding)
        if p['property'] == 'S1':
            facts = roundtrip(sent, current, eligible, {f: binding['fields'][f]['read_schema']['constraints'].get('format') for f in eligible})
            changes, optional_missing, unsupported = {}, [], []
            for f in eligible:
                meta = binding['fields'][f]
                if f not in current:
                    if meta['required_in_read']:
                        changes[f] = 'dropped_required_field'
                    else:
                        optional_missing.append(f)
                elif scalar_valid(current[f], meta['read_schema']) is None:
                    unsupported.append(f)
                elif not equal(sent[f], current[f], meta['read_schema']['constraints']):
                    changes[f] = 'changed'
            if changes:
                value, why = 'violation', 'ACCEPTED_WRITE_READBACK_MISMATCH_CANDIDATE'
            elif optional_missing:
                value, why = 'policy_observation', 'OPTIONAL_READ_FIELD_NOT_RETURNED'
            elif unsupported:
                value, why = 'not_evaluable', 'READBACK_VALUE_NOT_COMPARABLE'
            else:
                value, why = 'consistent', 'SENT_FIELDS_MATCH_READBACK'
            self.verdict('S1', row, op, value, why, witnesses, eligible, binding,
                         {'changes': changes, 'optional_missing': optional_missing, 'unsupported_fields': unsupported,
                          'readback_consistency_is_candidate_not_product_intent_proof': True,
                          'historical_provider': 'RT-1', 'change_subtypes': facts.get('change_subtypes', {})})
            return
        before = project_read(p['before']['response'], binding) if p['before'] else None
        if not isinstance(before, dict):
            self.verdict('S5', row, op, 'not_evaluable', 'PREIMAGE_NOT_RETAINED', witnesses, binding=binding)
            return
        for f in eligible:
            if f not in before or f not in current:
                self.verdict('S5', row, op, 'not_evaluable', 'BEFORE_AFTER_FIELD_MISSING', witnesses, eligible, binding)
                return
        facts = failed_update(row['status'], {f:before[f] for f in eligible},
                              {f:sent[f] for f in eligible}, {f:current[f] for f in eligible})
        states = facts.get('field_states', {})
        changed = list(states)
        if not changed:
            self.verdict('S5', row, op, 'not_evaluable', 'NO_OBSERVABLE_REQUESTED_CHANGE', witnesses, eligible, binding)
            return
        outcomes = set(states.values())
        outcome = ('unchanged' if outcomes == {'kept'} else 'committed_despite_error' if outcomes == {'applied'} else
                   'partial' if outcomes == {'applied', 'kept'} else 'other_state_change')
        policy = self.context.get('semantic_policies', {}).get('failed_write_no_effect')
        value = 'consistent' if outcome == 'unchanged' else ('violation' if policy else 'policy_observation')
        self.verdict('S5', row, op, value, 'FAILED_WRITE_' + outcome.upper(), witnesses, changed, binding,
                     {'outcome': outcome, 'field_states': states, 'historical_provider': 'ATOM-1-2',
                      'semantic_guarantee': policy, 'scope': 'requested_comparable_fields_only',
                      'full_resource_atomicity_proven': False})

    def consume(self, row, op):
        epoch = (type(row.get('epoch')).__name__, row.get('epoch'))
        if self.current_epoch is not None and epoch != self.current_epoch:
            self.finish_pending('RESET_EPOCH_CHANGED')
            self.snapshots.clear()
        self.current_epoch = epoch
        if row['method'] not in SAFE:
            # Any mutation may have cross-resource effects. Do not silently carry a prefix through it.
            self.finish_pending('INTERVENING_MUTATION')
            before = self.snapshots.get(self.scope(row))
            self.snapshots.clear()
            if not op:
                self.unmapped_mutations += 1
            if row['method'] not in ('POST', 'PUT', 'PATCH') or not op:
                return
            check = self.constraint_input(row, op)
            binding = self.bindings.get(op['key'], {})
            status = row['status'] or 0
            prop = 'S1' if 200 <= status < 400 else 'S5'
            reason = self.precondition(row)
            if binding.get('status') != 'structural_candidate':
                reason = reason or 'CONTRACT_READ_WRITE_BINDING_UNAVAILABLE'
            if not row.get('input_available') or not isinstance(row.get('input'), dict):
                reason = reason or 'REQUEST_JSON_OBJECT_NOT_RETAINED'
            if row.get('input_available') and len(canonical(row['input'])) > MAX_STATE_BODY_BYTES:
                reason = reason or 'WRITE_STATE_BODY_BUDGET'
            if status == 202:
                reason = reason or 'ASYNCHRONOUS_WRITE_NOT_INTERPRETED'
            if 300 <= status < 400:
                reason = reason or 'REDIRECTED_WRITE_NOT_INTERPRETED'
            if not status:
                reason = reason or 'WRITE_ANSWER_MISSING'
            if row['method'] == 'POST':
                self.constraints(row, op, check)
                return
            deferred_s3 = bool(not reason and check.get('invalid') and 200 <= status < 300)
            if not deferred_s3:
                self.constraints(row, op, check)
            if reason:
                self.verdict(prop, row, op, 'not_evaluable', reason, binding=binding)
                return
            self.pending = {'row': row, 'op': op, 'binding': binding, 'property': prop, 'before': before,
                            'constraints': check, 'deferred_s3': deferred_s3}
            return
        if row['method'] != 'GET' or not op:
            return
        self.snapshots.pop(self.scope(row), None)
        if self.pending and self.scope(row) == self.scope(self.pending['row']) and op['key'] == self.pending['binding']['read_operation']:
            self.finish_pending(self.precondition(row), row)
        if (op['key'] in self.read_ops and not self.precondition(row) and row['status'] == 200 and
                row.get('response_available') and isinstance(row.get('response'), dict) and
                len(canonical(row['response'])) <= MAX_STATE_BODY_BYTES):
            key = self.scope(row)
            self.snapshots[key] = row
            self.snapshots.move_to_end(key)
            if len(self.snapshots) > MAX_SNAPSHOTS:
                self.snapshots.popitem(last=False)
                self.evictions += 1

    def finish(self):
        self.finish_pending('READBACK_NOT_RETAINED_IN_SAME_SCOPE')
        return {'snapshot_evictions': self.evictions, 'snapshot_limit': MAX_SNAPSHOTS,
                'max_state_body_bytes': MAX_STATE_BODY_BYTES,
                'scope': 'same_uri_origin_actor_reset_epoch_case_no_intervening_mutation',
                'capture_assumptions_verified_by_judge': False,
                'unmapped_mutation_records': self.unmapped_mutations}
