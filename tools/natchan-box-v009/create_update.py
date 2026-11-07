"""S2 from immutable raw observations. Status differences are not field-causal bug claims."""
from datetime import datetime, timezone
from decimal import Decimal
import re
from urllib.parse import quote, unquote, urljoin, urlsplit

from common import canonical, digest
from state_semantics import SAFE, MAX_STATE_BODY_BYTES

MAX_ARMS = 512
MAX_FINGERPRINTS = 16384


def fingerprint(value, schema):
    c = schema.get('constraints', {})
    if value is None or isinstance(value, (dict, list)):
        return None  # null PATCH semantics and complex values are not interpreted
    if type(value) is bool:
        key = ['boolean', value]
    elif type(value) in (int, float):
        n = Decimal(str(value))
        sign, digits, exponent = n.as_tuple()
        digits = list(digits)
        while len(digits) > 1 and digits[-1] == 0:
            digits.pop()
            exponent += 1
        exact = ('-' if sign else '') + ''.join(str(d) for d in digits) + 'e' + str(exponent)
        key = ['number', '0' if n == 0 else exact]
    elif isinstance(value, str):
        if c.get('format') == 'date-time':
            try:
                d = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if d.tzinfo:
                    value = d.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        key = ['string', value]
    else:
        return None
    return digest(canonical(key))


def lite(row):
    return {k: row.get(k) for k in ('method', 'path', 'status', 'input_class', 'source', 'origin',
                                   'scheme', 'actor', 'epoch', 'case_id')}


def principal(row):
    return (row.get('scheme'), row.get('origin'), row.get('actor'),
            type(row.get('epoch')).__name__, row.get('epoch'), row.get('case_id'))


def response_class(status):
    if status == 202:
        return None
    if status is not None and 200 <= status < 300:
        return 'accepted'
    if status in (400, 422):
        return 'validation_rejected'
    if status is not None and 500 <= status < 600:
        return 'server_error'
    return None


def route_values(template, captured, bases):
    tokens = re.split(r'\{([^{}]+)\}', template)
    names = tokens[1::2]
    pattern = '^' + ''.join('([^/]+)' if i % 2 else re.escape(t) for i, t in enumerate(tokens)) + '$'
    candidates = [(captured, '')]
    candidates += [(captured[len(b):] or '/', b) for b in bases if b and captured.startswith(b + '/')]
    found = []
    for path, base in candidates:
        m = re.fullmatch(pattern, path)
        if m:
            found.append((dict(zip(names, m.groups())), base))
    return found[0] if len(found) == 1 else (None, None)


def pointer(value, expression):
    if not expression.startswith('$response.body#/'):
        return None
    try:
        for token in expression[len('$response.body#/'):].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', token):
                    return None
                value = value[int(token)]
            else:
                value = value[token]
        return value
    except (KeyError, TypeError, ValueError, IndexError):
        return None


class PathJudge:
    def __init__(self, context, state, emit):
        self.context, self.state, self.emit = context, state, emit
        self.pairs = {k: v for k, v in context.get('create_update_bindings', {}).items()}
        self.creates = {}
        self.operations = {o['key']: o for o in context['operations']}
        for family in self.pairs.values():
            for pair in family['pairs']:
                if pair['fields']:
                    self.creates.setdefault(pair['create_operation'], []).append(pair)
                if pair['read_operation'] and pair['read_schema'].get('status') == 'declared':
                    state.read_ops.add(pair['read_operation'])
        self.arms = []
        self.pending_create, self.pending_update = [], []
        self.epoch = None
        self.generation = 0
        self.fingerprints = 0
        self.truncated = False
        self.truncations = 0
        self.stats = {'attempted_updates': 0, 'status_comparisons': 0, 'readback_comparisons': 0,
                      'ambiguous_matches': 0, 'creation_arms_seen': 0}

    def collection(self, row, pair, creation=False):
        if pair['relationship_basis'] != 'collection_item_routes':
            return None
        if creation:
            return row['path']
        return row['path'].rstrip('/').rsplit('/', 1)[0] + ('/' if pair['collection_route'].endswith('/') else '')

    def identity(self, row, pair):
        if row['status'] != 201 or not pair['read_operation']:
            return None, None
        possibilities = []
        location = row.get('location')
        if location and not any(ord(c) <= 32 or ord(c) == 127 for c in location):
            try:
                base = ((row['scheme'] + '://' + row['origin']) if row.get('scheme') and row.get('origin') else '') + row['path']
                u = urlsplit(urljoin(base, location))
                if not u.query and not u.fragment and ((not u.scheme and not u.netloc) or
                        (u.netloc.lower() == row.get('origin') and u.scheme == row.get('scheme'))):
                    possibilities.append((u.path, 'recorded_201_location'))
            except ValueError:
                pass  # malformed Location cannot supply identity; status evidence is still usable
        values, base = route_values(pair['collection_route'], row['path'], self.context['api_base_paths'])
        get = self.operations[pair['read_operation']]
        for link in pair['creation_links']:
            if link.get('server') is not None or bool(link.get('operationId')) == bool(link.get('operationRef')):
                continue
            if link.get('operationId'):
                if (link['operationId'] != get.get('operationId') or
                        sum(o.get('operationId') == link['operationId'] for o in self.operations.values()) != 1):
                    continue
            elif link.get('operationRef') != get['provenance']:
                continue
            if values is None or not isinstance(link.get('parameters'), dict):
                continue
            try:
                params = {k: unquote(v, errors='strict') for k, v in values.items()}
            except UnicodeError:
                continue
            names = re.findall(r'\{([^{}]+)\}', pair['item_route'])
            valid = True
            for name, expr in link['parameters'].items():
                name = name[len('path.'):] if name.startswith('path.') else name
                if name not in names:
                    valid = False
                    break
                if isinstance(expr, str) and expr.startswith('$response.body#/'):
                    params[name] = pointer(row.get('response'), expr)
                elif isinstance(expr, str) and expr.startswith('$request.path.'):
                    params[name] = params.get(expr[len('$request.path.'):])
                elif isinstance(expr, (str, int)) and not (isinstance(expr, str) and expr.startswith('$')):
                    params[name] = expr
                else:
                    valid = False
                    break
            if not valid or any(type(params.get(n)) not in (str, int) or len(str(params[n])) > 256 for n in names):
                continue
            try:
                path = re.sub(r'\{([^{}]+)\}', lambda m: quote(str(params[m[1]]), safe=''), pair['item_route'])
            except UnicodeError:
                continue
            possibilities.append(((base or '') + path, 'explicit_public_operation_link'))
        valid = []
        for uri, basis in possibilities:
            params, _ = route_values(pair['item_route'], uri, self.context['api_base_paths'])
            if params is not None:
                valid.append((uri, basis))
        if len({uri for uri, _ in valid}) != 1:
            return None, None
        return valid[0]

    def verdict(self, row, pair, field, value, reason, arm=None, before=None, after=None, details=None):
        sources = [row['source']]
        if arm:
            sources.append(arm['row']['source'])
            if arm.get('read_source'):
                sources.append(arm['read_source'])
        sources += [r['source'] for r in (before, after) if r]
        sources = list({digest(canonical(s)): s for s in sources}.values())
        points = list(pair.get('provenance', []))
        if field and field in pair.get('fields', {}):
            points += [pair['fields'][field][k]['provenance'] for k in ('create_schema', 'update_schema')]
        get = self.operations.get(pair.get('read_operation'))
        if get:
            points.append(get['provenance'])
        self.emit({'property': 'S2', 'value': value, 'reason': reason, 'operation': row.get('operation'),
                   'operations': [pair.get('create_operation'), row.get('operation')],
                   'entity': None, 'field': field, 'fields': [field] if field else [],
                   'status': row['status'], 'input_class': row['input_class'], 'evidence': sources,
                   'knowledge': [{'contract_sha256': self.context['contract_sha256'], 'pointer': p} for p in sorted(set(points))],
                   'scope': 'create_update_comparison', 'root_cause_proven': False,
                   'assumptions': ['DECLARED_EQUIVALENT_SCALAR_FIELD_HAS_EQUIVALENT_WRITE_MEANING'],
                   'details': dict(details or {}, field_causality_proven=False, producer_verdict_used=False)})

    def flush(self, reason):
        for pending in self.pending_update:
            self.verdict(pending['row'], pending['pair'], pending['field'], 'not_evaluable', reason,
                         pending['arm'], pending['before'])
        self.pending_update.clear()
        for arm in self.pending_create:
            arm['read_unavailable_reason'] = reason
        self.pending_create.clear()

    def read_values(self, row, pair):
        if row['status'] != 200 or not row.get('response_available') or not isinstance(row.get('response'), dict):
            return None
        if len(canonical(row['response'])) > MAX_STATE_BODY_BYTES:
            return None
        result = {}
        for f in pair['fields']:
            schema = pair['read_schema'].get('fields', {}).get(f)
            if schema and schema.get('status') == 'declared':
                result[f] = fingerprint(row['response'][f], schema) if f in row['response'] else None
        return result

    def consume(self, row, op, before):
        epoch = (type(row.get('epoch')).__name__, row.get('epoch'))
        if self.epoch is not None and self.epoch != epoch:
            self.flush('S2_RESET_EPOCH_CHANGED')
            self.arms.clear()
            self.fingerprints, self.truncated = 0, False
        self.epoch = epoch
        if row['method'] not in SAFE:
            self.flush('S2_INTERVENING_MUTATION_BEFORE_READBACK')
            self.generation += 1
            if not op:
                return
            if op['key'] in self.creates and not self.state.precondition(row) and isinstance(row.get('input'), dict):
                if row.get('input_available') and len(canonical(row['input'])) <= MAX_STATE_BODY_BYTES:
                    for pair in self.creates[op['key']]:
                        values = {f: fingerprint(row['input'][f], m['create_schema']) for f, m in pair['fields'].items() if f in row['input']}
                        values = {f: v for f, v in values.items() if v is not None}
                        if not values:
                            continue
                        self.stats['creation_arms_seen'] += 1
                        if self.truncated:
                            continue
                        if len(self.arms) >= MAX_ARMS or self.fingerprints + len(values) > MAX_FINGERPRINTS:
                            self.truncated = True
                            self.truncations += 1
                            self.arms.clear()
                            self.pending_create.clear()
                            continue
                        uri, basis = self.identity(row, pair)
                        arm = {'pair_id': pair['id'], 'row': lite(row), 'values': values,
                               'collection': self.collection(row, pair, True), 'generation': self.generation,
                               'uri': uri, 'identity_basis': basis, 'read_values': None,
                               'pair': pair, 'read_source': None}
                        self.arms.append(arm)
                        self.fingerprints += len(values)
                        if uri:
                            self.pending_create.append(arm)
            family = self.pairs.get(op['key'])
            if not family:
                return
            self.stats['attempted_updates'] += 1
            row = dict(lite(row), operation=op['key'], query_present=row['query_present'],
                       input=row.get('input'), input_available=row.get('input_available'))
            empty = {'provenance': [op['provenance']], 'fields': {}}
            reason = self.state.precondition(row)
            if reason or family['status'] != 'structural_candidate' or self.truncated:
                self.verdict(row, empty, None, 'not_evaluable', reason or
                             ('S2_HISTORY_BUDGET_EXCEEDED' if self.truncated else 'S2_CONTRACT_BINDING_UNAVAILABLE'))
                return
            if not row.get('input_available') or not isinstance(row['input'], dict) or len(canonical(row['input'])) > MAX_STATE_BODY_BYTES:
                self.verdict(row, empty, None, 'not_evaluable', 'S2_REQUEST_OBJECT_UNAVAILABLE_OR_OVER_BUDGET')
                return
            had_field = False
            for pair in family['pairs']:
                for field, meta in pair['fields'].items():
                    if field not in row['input']:
                        continue
                    had_field = True
                    fp = fingerprint(row['input'][field], meta['update_schema'])
                    if fp is None:
                        self.verdict(row, pair, field, 'not_evaluable', 'S2_NULL_OR_COMPLEX_VALUE_NOT_INTERPRETED')
                        continue
                    options = [a for a in self.arms if a['pair_id'] == pair['id'] and
                               principal(a['row']) == principal(row) and a['values'].get(field) == fp and
                               (pair['relationship_basis'] != 'collection_item_routes' or
                                a['collection'] == self.collection(row, pair))]
                    same = [a for a in options if a['uri'] == row['path']]
                    if same:
                        options = same  # explicit resource identity, not a similarity score
                    if len(options) != 1:
                        if options:
                            self.stats['ambiguous_matches'] += 1
                        self.verdict(row, pair, field, 'not_evaluable',
                                     'S2_AMBIGUOUS_CREATE_MATCH' if options else 'S2_MATCHING_CREATE_NOT_RETAINED')
                        continue
                    arm = options[0]
                    if (not before or principal(before) != principal(row) or not isinstance(before.get('response'), dict)
                            or not pair['read_schema'].get('fields') or not any(k in before['response'] for k in pair['read_schema']['fields'])):
                        self.verdict(row, pair, field, 'not_evaluable', 'S2_UPDATE_RESOURCE_PREIMAGE_NOT_ESTABLISHED', arm)
                        continue
                    a, b = response_class(arm['row']['status']), response_class(row['status'])
                    details = {'create_status': arm['row']['status'], 'update_status': row['status'],
                               'create_class': a, 'update_class': b, 'check_kind': 'status_class',
                               'non_target_preconditions_proven': False}
                    if pair['relationship_basis'] != 'collection_item_routes' and arm['uri'] != row['path']:
                        self.verdict(row, pair, field, 'not_evaluable', 'S2_CROSS_ROUTE_PARENT_CONTEXT_UNPROVEN', arm, before, details=details)
                    elif a is None or b is None:
                        self.verdict(row, pair, field, 'not_evaluable', 'S2_RESPONSE_CLASS_NOT_COMPARABLE', arm, before, details=details)
                    elif a != b:
                        self.stats['status_comparisons'] += 1
                        self.verdict(row, pair, field, 'policy_observation', 'S2_CREATE_UPDATE_STATUS_CLASS_DIVERGENCE', arm, before, details=details)
                    elif a != 'accepted':
                        self.stats['status_comparisons'] += 1
                        self.verdict(row, pair, field, 'consistent', 'S2_SAME_RESPONSE_CLASS_ONLY', arm, before, details=details)
                    else:
                        same_inputs = all(k in pair['fields'] and fingerprint(v, pair['fields'][k]['update_schema']) == arm['values'].get(k)
                                          for k, v in row['input'].items())
                        self.pending_update.append({'row': lite(row) | {'operation': op['key']}, 'pair': pair,
                                                    'field': field, 'arm': arm, 'before': lite(before),
                                                    'before_value': fingerprint(before['response'].get(field), pair['read_schema'].get('fields', {}).get(field, {})),
                                                    'controlled': same_inputs and arm['generation'] == self.generation - 1 and arm['uri'] == row['path']})
            if not had_field:
                self.verdict(row, empty, None, 'not_evaluable', 'S2_NO_EQUIVALENT_SENT_SCALAR_FIELDS')
            return
        if row['method'] != 'GET' or not op:
            return
        for arm in list(self.pending_create):
            if (arm['uri'] == row['path'] and principal(arm['row']) == principal(row) and
                    arm['pair']['read_operation'] == op['key']):
                self.pending_create.remove(arm)
                if not self.state.precondition(row):
                    arm['read_values'] = self.read_values(row, arm['pair'])
                    arm['read_source'] = row['source']
        for p in list(self.pending_update):
            if (p['row']['path'] != row['path'] or principal(p['row']) != principal(row) or
                    p['pair']['read_operation'] != op['key']):
                continue
            self.pending_update.remove(p)
            current = self.read_values(row, p['pair']) if not self.state.precondition(row) else None
            old, field = p['arm']['read_values'], p['field']
            if current is None or old is None or old.get(field) is None or current.get(field) is None:
                self.verdict(p['row'], p['pair'], field, 'not_evaluable', 'S2_CREATE_OR_UPDATE_READBACK_NOT_COMPARABLE', p['arm'], p['before'], row)
                continue
            self.stats['readback_comparisons'] += 1
            changed = old[field] != current[field]
            controlled = p['controlled'] and p['before_value'] == old[field]
            value = ('violation' if controlled else 'policy_observation') if changed else 'consistent'
            self.verdict(p['row'], p['pair'], field, value,
                         'S2_CREATE_UPDATE_STORED_VALUE_DIVERGENCE' if changed else 'S2_CREATE_UPDATE_READBACK_MATCH',
                         p['arm'], p['before'], row,
                         {'check_kind': 'readback', 'same_created_resource': p['arm']['uri'] == row['path'],
                          'identity_basis': p['arm']['identity_basis'], 'controlled_scalar_comparison': controlled,
                          'non_target_preconditions_proven': False, 'different_stored_value': changed})

    def finish(self):
        self.flush('S2_READBACK_NOT_RETAINED_IN_SAME_SCOPE')
        return dict(self.stats, history_truncations=self.truncations, history_limit=MAX_ARMS,
                    fingerprint_limit=MAX_FINGERPRINTS, counting_unit='per_update_field_and_contract_pair',
                    status_difference_is_not_a_proven_product_bug=True)
