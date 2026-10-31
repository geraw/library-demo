"""Independent status and bounded state judgement; no producer verdict inputs."""
from collections import Counter
import json
import re
from urllib.parse import urlsplit

from common import canonical, digest

CLASSES = {
    'S1': 'read_back_consistency', 'S2': 'path_consistency',
    'S3': 'constraint_conformance', 'S4': 'reference_integrity',
    'S5': 'failure_atomicity', 'S6': 'placement_view_consistency',
    'S7': 'error_answers_in_context',
}
VALUES = ('violation', 'consistent', 'not_evaluable', 'policy_observation')


def matcher(context):
    result = []
    for op in context['operations']:
        expression = re.escape(op['path'])
        expression = re.sub(r'\\\{[^{}]+\\\}', '[^/]+', expression)
        result.append((op, re.compile('^' + expression + '$')))
    return result


def operation(row, index, bases):
    candidates = {}
    paths = {row['path']}
    for base in bases:
        if base and (row['path'] == base or row['path'].startswith(base + '/')):
            paths.add(row['path'][len(base):] or '/')
    for op, rx in index:
        if row['method'] == op['method'] and any(rx.fullmatch(p) for p in paths):
            candidates[op['key']] = op
    if len(candidates) == 1:
        return next(iter(candidates.values())), None
    return None, 'OPERATION_MATCH_AMBIGUOUS' if candidates else 'OPERATION_NOT_IN_CONTRACT'


def declared(status, responses):
    return (str(status) in responses or str(status)[0] + 'XX' in responses or 'default' in responses)


def classify(row, op, gap):
    if row['status'] is None:
        return 'not_evaluable', 'SERVER_ANSWER_MISSING'
    if not op:
        return 'not_evaluable', gap
    if row['status'] >= 500:
        return 'violation', 'SERVER_5XX_CANDIDATE'
    if not declared(row['status'], op['responses']):
        return 'violation', 'UNDECLARED_STATUS_CANDIDATE'
    return 'consistent', 'STATUS_DECLARED_ONLY'


def analyze(rows, context, verdict_file, logs=None, http_id_counts=None, capture=None):
    from state_semantics import StateJudge
    from create_update import PathJudge
    supported = {'S1', 'S2', 'S3', 'S5', 'S7'}
    index = matcher(context)
    counts = {k: Counter() for k in supported}
    reasons = {k: Counter() for k in supported}
    groups = {}
    total, joined, server_errors = 0, 0, 0

    def emit(verdict):
        prop, value = verdict['property'], verdict['value']
        counts[prop][value] += 1
        if value == 'not_evaluable':
            reasons[prop][verdict['reason']] += 1
        verdict['id'] = digest(canonical(verdict))
        verdict_file.write(json.dumps(verdict, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n')
        if value not in ('violation', 'policy_observation'):
            return
        group_type = ('server_5xx' if prop == 'S7' and verdict['reason'] == 'SERVER_5XX_CANDIDATE' else
                      'undeclared_status' if prop == 'S7' else
                      'policy_observation' if value == 'policy_observation' else 'semantic_candidate')
        key = (prop, value, verdict['operation'], tuple(verdict.get('fields', [])),
               verdict['reason'], verdict['input_class'], verdict['status'], verdict.get('server_signature_sha256'))
        if key not in groups:
            groups[key] = {'id': digest(canonical(list(key))), 'property': prop, 'value': value,
                           'group_type': group_type,
                           'operation': verdict['operation'], 'fields': verdict.get('fields', []),
                           'operations': verdict.get('operations', [verdict['operation']]),
                           'reason': verdict['reason'], 'input_class': verdict['input_class'],
                           'status': verdict['status'], 'server_signature_sha256': key[-1],
                           'occurrences': 0, 'representative_verdict_ids': [],
                           'grouping_basis': 'symptom_signature', 'root_cause_proven': False}
        group = groups[key]
        group['occurrences'] += 1
        if len(group['representative_verdict_ids']) < 3:
            group['representative_verdict_ids'].append(verdict['id'])

    state = StateJudge(context, capture, emit)
    paths = PathJudge(context, state, emit)
    for row in rows:
        total += 1
        server_errors += (row['status'] or 0) >= 500
        op, gap = operation(row, index, context['api_base_paths'])
        value, reason = classify(row, op, gap)
        verdict = {'property': 'S7', 'value': value, 'reason': reason,
                   'operation': op['key'] if op else None,
                   'entity': None, 'field': None, 'status': row['status'],
                   'input_class': row['input_class'], 'evidence': [row['source']],
                   'knowledge': [{'contract_sha256': context['contract_sha256'],
                                  'pointer': op['provenance'] + '/responses'}] if op else [],
                   'scope': 'http_status_only', 'root_cause_proven': False}
        log = (logs or {}).get(row.get('request_id'))
        if log and (http_id_counts or {}).get(row.get('request_id')) == 1 and row['status'] is not None and row['status'] >= 500:
            if ((not log['method'] or log['method'] == row['method']) and
                (not log['path'] or log['path'] == row['path']) and
                (log['status'] is None or log['status'] == row['status'])):
                verdict['server_signature_sha256'] = log['signature_sha256']
                verdict['evidence'].append(log['source'])
                verdict['log_join_basis'] = 'unique_request_id'
                joined += 1
        emit(verdict)
        paths.consume(row, op, state.snapshots.get(state.scope(row)))
        state.consume(row, op)
    state_audit = state.finish()
    path_audit = paths.finish()
    coverage = {k: {'name': name, 'implemented': k in supported,
                    'opportunities': sum(counts[k].values()) if k in supported else None,
                    'counts': {v: counts[k][v] for v in VALUES} if k in supported else {v: None for v in VALUES},
                    'abstention_reasons': dict(sorted(reasons[k].items())) if k in supported else None,
                    'reason': 'BOUNDED_SUBSET_SEE_REPORT' if k in supported else 'PROPERTY_NOT_IMPLEMENTED_IN_DEV_4'}
                for k, name in CLASSES.items()}
    partitions = {kind: {'groups': sum(g['group_type'] == kind for g in groups.values()),
                         'occurrences': sum(g['occurrences'] for g in groups.values() if g['group_type'] == kind)}
                  for kind in ('server_5xx', 'undeclared_status', 'semantic_candidate', 'policy_observation')}
    return {'exchanges': total, 'groups': sorted(groups.values(), key=lambda g: g['id']),
            'finding_partitions': partitions,
            'classes': coverage, 'unique_server_log_joins': joined, 'state_audit': state_audit,
            'path_consistency_audit': path_audit,
            'server_5xx': server_errors, 'unjoined_server_5xx': server_errors - joined,
            'distinct_bugs': None, 'producer_verdicts_used': False}
