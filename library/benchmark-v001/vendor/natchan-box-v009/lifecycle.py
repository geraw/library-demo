"""Tool-neutral lifecycle candidates derived from contract routes and scalar schemas.
No product names, mutant identifiers, source code or producer verdicts are inputs.
Structural bindings establish candidates, not undocumented business guarantees.
"""
import re
from urllib.parse import urlsplit, quote

SAFE = {'GET', 'HEAD', 'OPTIONS'}
MAX_ENTITIES = 10000

def derive_lifecycle(context):
    operations = context['operations']
    result = []
    for read in operations:
        match = re.fullmatch(r'(.*)/\{([^/{}]+)\}', read['path'].rstrip('/'))
        if read['method'] != 'GET' or not match:
            continue
        collection, parameter = match.groups()
        schema = read['responses'].get('200', {})
        fields = schema.get('fields', {})
        candidates = [name for name, value in fields.items()
                      if value.get('constraints', {}).get('type') in ('integer', 'string')
                      and name.lower().replace('_', '') in
                      {parameter.lower().replace('_', ''), 'id', 'uuid'}]
        identity = candidates[0] if len(candidates) == 1 else None
        create = [o for o in operations if o['method'] == 'POST' and o['path'].rstrip('/') == collection
                  and o['declared_write_role']['value'] == 'create']
        delete = [o for o in operations if o['method'] == 'DELETE' and o['path'] == read['path']]
        result.append({'read': read['key'], 'item': read['path'], 'collection': collection,
                       'parameter': parameter, 'identity': identity,
                       'integer_identity': bool(identity and fields[identity].get('constraints', {}).get('type') == 'integer' and any(p['in']=='path' and p['name']==parameter and p['schema'].get('constraints',{}).get('type')=='integer' for p in read['parameters'])),
                       'create': create[0]['key'] if len(create) == 1 else None,
                       'delete': delete[0]['key'] if len(delete) == 1 else None,
                       'provenance': [read['provenance'], *[o['provenance'] for o in create + delete]],
                       'binding_basis': 'structural_route_and_unique_scalar_identity_candidate'})
    return result

class LifecycleJudge:
    def __init__(self, context, capture, state):
        self.context, self.capture, self.state = context, capture or {}, state
        self.bindings = derive_lifecycle(context)
        self.records = {}
        self.scope = None
        self.audit = {'bindings': self.bindings, 'tracked_creations': 0,
                      'tracked_deletions': 0, 'invalidations': 0, 'budget_evictions': 0, 'conditional_interference': 0}

    def emit(self, row, op, value, reason, witnesses=(), binding=None, details=None):
        policy_key = 'creation_visible' if reason.startswith('CREATED_') else 'deletion_removes'
        policy = self.context.get('semantic_policies', {}).get(policy_key)
        uncertain_query=any(r.get('query_present') for r in (row,*witnesses))
        interference=(details or {}).get('intervening_mutations',0)
        if value=='violation' and (uncertain_query or not policy or interference):value='policy_observation'
        self.state.verdict('S1', row, op, value, reason, witnesses,
                           binding={'provenance': (binding or {}).get('provenance', []) + ([policy['pointer']] if policy else [])},
                           details={'lifecycle': True, 'semantic_status': 'contract_violation' if policy and value == 'violation' else 'conditional_lifecycle_candidate',
                                    'semantic_guarantee': policy,
                                    'query_semantics_established':not uncertain_query,
                                    'query_names':sorted({k for r in (row,*witnesses) for k,v in r.get('query_pairs',[])}),
                                    'assumptions': ['synchronous_resource_lifecycle',
                                                    'stable_identity_and_visibility',
                                                    'no_unobserved_side_effects' if interference else 'no_intervening_mutation'],
                                    **(details or {})})

    @staticmethod
    def identity_path(path, binding):
        # Only a declared integer path parameter AND integer response identity
        # permit numeric canonicalization. String IDs remain byte-distinct.
        if binding.get('integer_identity'):
            prefix, sep, value = path.rpartition('/')
            if sep and re.fullmatch(r'[+-]?[0-9]{1,256}', value):
                return prefix + '/' + str(int(value))
        return path

    def consume(self, row, op):
        scope = (row.get('origin'), row.get('actor'), type(row.get('epoch')).__name__, row.get('epoch'), row.get('case_id'))
        if scope != self.scope:
            self.records.clear()
            self.scope = scope
        matching = [b for b in self.bindings if op and op['key'] in (b['read'], b['create'], b['delete'])]
        mutation = row['method'] not in SAFE
        # An unrelated filtered read does not erase resource history. Global
        # capture/actor/epoch guards still apply to every exchange.
        gap = self.state.precondition(dict(row, query_present=False))
        if gap or row['status'] is None:
            self.records.clear()
            if op and matching and mutation:
                self.emit(row, op, 'not_evaluable', gap or 'SERVER_ANSWER_MISSING')
            return
        declared_query = {p['name'] for p in (op or {}).get('parameters', []) if p['in']=='query'}
        if matching and row.get('query_present') and declared_query:
            self.records.clear()
            return
        if mutation:
            status = row['status']
            # Unknown successful actions, asynchronous effects and server failures
            # are hard barriers. Their possible write set cannot be bounded.
            if status >= 500 or status == 202 or (200 <= status < 300 and not op):
                self.audit['invalidations'] += len(self.records)
                self.records.clear()
            else:
                for key, previous in list(self.records.items()):
                    target = self.identity_path(row['path'], previous['binding'])
                    if 200 <= status < 300 and target == key:
                        self.records.pop(key)
                        self.audit['invalidations'] += 1
                    elif 200 <= status < 300 and row['path'].rstrip('/') == previous['binding']['collection'] and not any(op and op['key']==b['create'] for b in matching):
                        self.records.pop(key)
                        self.audit['invalidations'] += 1
                    else:
                        # Retain an explicit hypothesis, NOT a proved frame rule.
                        # Rejected writes and other-resource writes may have side
                        # effects; a later contradiction is only an observation.
                        previous['intervening_mutations'] = previous.get('intervening_mutations', 0) + 1
                        sources = previous.setdefault('interference_sources', [])
                        if len(sources) < 4: sources.append(row['source'])
                        self.audit['conditional_interference'] += 1
        if not op:
            return
        for b in matching:
            path = self.identity_path(row['path'], b)
            if op['key'] == b['create']:
                if row['status'] != 201:
                    continue
                target = None
                location = row.get('location')
                if location:
                    loc = urlsplit(location)
                    if not loc.query and not loc.fragment and (not loc.netloc or loc.netloc.lower() == row['origin']):
                        candidate = loc.path if loc.path.startswith('/') else path.rstrip('/') + '/' + loc.path
                        if candidate.startswith(path.rstrip('/') + '/') and len(candidate.split('/')) == len(path.rstrip('/').split('/')) + 1:
                            target = candidate
                if target is None and b['identity'] and row.get('response_available') and isinstance(row.get('response'), dict):
                    identity = row['response'].get(b['identity'])
                    declared = op['responses'].get('201', {}).get('fields', {}).get(b['identity'], {})
                    if ((declared.get('constraints', {}).get('type') == 'integer' and type(identity) is int) or (declared.get('constraints', {}).get('type') == 'string' and isinstance(identity,str))) and str(identity) and len(str(identity)) <= 256:
                        target = path.rstrip('/') + '/' + quote(str(identity), safe='') + ('/' if b['item'].endswith('/') else '')
                if target:
                    target = self.identity_path(target, b)
                    self.records[target] = {'state':'created', 'row':row, 'binding':b}
                    self.audit['tracked_creations'] += 1
                else:
                    # An unbound successful creation could recreate a deleted ID.
                    self.records = {k:v for k,v in self.records.items() if v['binding']['read'] != b['read']}
                    self.emit(row, op, 'not_evaluable', 'CREATE_RESOURCE_IDENTITY_UNAVAILABLE', binding=b)
            elif op['key'] == b['delete']:
                if row['status'] in (200, 204):
                    self.records[path] = {'state':'deleted', 'row':row, 'binding':b}
                    self.audit['tracked_deletions'] += 1
            elif op['key'] == b['read'] and path in self.records:
                previous = self.records[path]
                status = row['status']
                if previous['state'] == 'created' and status in (200, 404, 410):
                    self.emit(row, op, 'violation' if status in (404,410) else 'consistent',
                              'CREATED_RESOURCE_NOT_READABLE' if status in (404,410) else 'CREATED_RESOURCE_READABLE',
                              [previous['row']], b, details={'intervening_mutations':previous.get('intervening_mutations',0), 'interference_sources':previous.get('interference_sources',[])})
                elif previous['state'] == 'deleted' and status in (200,404,410):
                    self.emit(row, op, 'violation' if status == 200 else 'consistent',
                              'DELETED_RESOURCE_STILL_READABLE' if status == 200 else 'DELETED_RESOURCE_NOT_READABLE',
                              [previous['row']], b, details={'intervening_mutations':previous.get('intervening_mutations',0), 'interference_sources':previous.get('interference_sources',[])})
                else:
                    self.emit(row, op, 'not_evaluable', 'LIFECYCLE_READ_STATUS_INCONCLUSIVE', [previous['row']], b, details={'intervening_mutations':previous.get('intervening_mutations',0), 'interference_sources':previous.get('interference_sources',[])})
            while len(self.records) > MAX_ENTITIES:
                self.records.pop(next(iter(self.records)))
                self.audit['budget_evictions'] += 1

    def finish(self):
        return self.audit
