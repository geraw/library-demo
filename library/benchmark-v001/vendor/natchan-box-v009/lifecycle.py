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
                      'tracked_deletions': 0, 'invalidations': 0, 'budget_evictions': 0}

    def emit(self, row, op, value, reason, witnesses=(), binding=None, details=None):
        policy_key = 'creation_visible' if reason.startswith('CREATED_') else 'deletion_removes'
        policy = self.context.get('semantic_policies', {}).get(policy_key)
        uncertain_query=any(r.get('query_present') for r in (row,*witnesses))
        if value=='violation' and (uncertain_query or not policy):value='policy_observation'
        self.state.verdict('S1', row, op, value, reason, witnesses,
                           binding={'provenance': (binding or {}).get('provenance', []) + ([policy['pointer']] if policy else [])},
                           details={'lifecycle': True, 'semantic_status': 'contract_violation' if policy and value == 'violation' else 'conditional_lifecycle_candidate',
                                    'semantic_guarantee': policy,
                                    'query_semantics_established':not uncertain_query,
                                    'query_names':sorted({k for r in (row,*witnesses) for k,v in r.get('query_pairs',[])}),
                                    'assumptions': ['synchronous_resource_lifecycle',
                                                    'stable_identity_and_visibility',
                                                    'no_intervening_mutation'],
                                    **(details or {})})

    def consume(self, row, op):
        scope = (row.get('origin'), row.get('actor'), type(row.get('epoch')).__name__, row.get('epoch'), row.get('case_id'))
        if scope != self.scope:
            self.records.clear()
            self.scope = scope
        gap = self.state.precondition(row)
        declared_query={p['name'] for p in (op or {}).get('parameters',[]) if p['in']=='query'}
        # Unknown query semantics permit an observation, never a proved lifecycle violation.
        if gap=='QUERY_SEMANTICS_NOT_INTERPRETED' and op and not declared_query:
            gap=self.state.precondition(dict(row,query_present=False))
        if gap:
            self.records.clear()
            if op and any(op['key'] in (b['create'],b['delete']) for b in self.bindings):
                self.emit(row, op, 'not_evaluable', gap)
            return
        if row['method'] not in SAFE:
            self.audit['invalidations'] += len(self.records)
            self.records.clear()
        if not op:
            if row['method'] not in SAFE:
                self.records.clear()
            return
        path = row['path']
        # Use an exact contract operation match supplied by judge.operation.
        matching = [b for b in self.bindings if op['key'] in (b['read'], b['create'], b['delete'])]
        if row['method'] not in SAFE and not matching:
            self.audit['invalidations'] += len(self.records)
            self.records.clear()
            return
        if row.get('query_present') and declared_query:
            if row['method'] not in SAFE:
                self.records.clear()
            return
        for b in matching:
            if op['key'] == b['create']:
                # Re-creation can invalidate any previous deletion identity.
                self.records = {k:v for k,v in self.records.items() if v['binding']['read'] != b['read'] or v['state'] != 'deleted'}
                if row['status'] != 201:
                    self.records = {k:v for k,v in self.records.items() if v['binding']['read'] != b['read']}
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
                    self.records[target] = {'state':'created', 'row':row, 'binding':b}
                    self.audit['tracked_creations'] += 1
                else:
                    self.emit(row, op, 'not_evaluable', 'CREATE_RESOURCE_IDENTITY_UNAVAILABLE', binding=b)
            elif op['key'] == b['delete']:
                if row['status'] in (200, 204):
                    self.records[path] = {'state':'deleted', 'row':row, 'binding':b}
                    self.audit['tracked_deletions'] += 1
                else:
                    self.records.pop(path, None)
            elif op['key'] == b['read'] and path in self.records:
                previous = self.records[path]
                status = row['status']
                if previous['state'] == 'created' and status in (200, 404, 410):
                    self.emit(row, op, 'violation' if status in (404,410) else 'consistent',
                              'CREATED_RESOURCE_NOT_READABLE' if status in (404,410) else 'CREATED_RESOURCE_READABLE',
                              [previous['row']], b)
                elif previous['state'] == 'deleted' and status in (200,404,410):
                    self.emit(row, op, 'violation' if status == 200 else 'consistent',
                              'DELETED_RESOURCE_STILL_READABLE' if status == 200 else 'DELETED_RESOURCE_NOT_READABLE',
                              [previous['row']], b)
                else:
                    self.emit(row, op, 'not_evaluable', 'LIFECYCLE_READ_STATUS_INCONCLUSIVE', [previous['row']], b)
            while len(self.records) > MAX_ENTITIES:
                self.records.pop(next(iter(self.records)))
                self.audit['budget_evictions'] += 1

    def finish(self):
        return self.audit
