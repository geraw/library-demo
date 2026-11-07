"""Independent S2 path candidates from public routes, write schemas and explicit role cues."""
from common import canonical, digest


def derive_pairs(operations):
    by_route = {(o['method'], o['path']): o for o in operations}
    result = {}
    for update in operations:
        is_item = update['path'].rstrip('/').endswith('}')
        role = update['declared_write_role']['value']
        if not ((update['method'] in ('PUT', 'PATCH') and is_item and role != 'create') or
                (update['method'] in ('POST', 'PUT', 'PATCH') and role == 'update')):
            continue
        stem = update['path'].rstrip('/').rsplit('/', 1)[0]
        collection = stem + ('/' if update['path'].endswith('/') else '') if is_item else None
        candidates = []
        classic = by_route.get(('POST', collection)) if collection else None
        if classic and classic['declared_write_role']['value'] != 'update':
            candidates.append((classic, 'collection_item_routes'))
        us = update.get('request_schema') or {}
        for create in operations:
            if create is update or create is classic or create['method'] not in ('POST', 'PUT'):
                continue
            cs = create.get('request_schema') or {}
            if (role == 'update' and create['declared_write_role']['value'] == 'create' and
                    cs.get('provenance') == us.get('provenance') and
                    str(cs.get('provenance', '')).startswith(('#/definitions/', '#/components/schemas/'))):
                candidates.append((create, 'declared_roles_shared_schema'))
        pairs, reasons = [], []
        if not candidates:
            reasons.append('NO_CONTRACT_CREATE_PATH_CANDIDATE')
        for create, basis in candidates:
            cs = create.get('request_schema') or {}
            fields, excluded = {}, {}
            if any(s.get('status') != 'declared' or not s.get('fields') for s in (cs, us)):
                reasons.append('CREATE_OR_UPDATE_OBJECT_SCHEMA_UNAVAILABLE')
                continue
            for name in sorted(set(cs['fields']) & set(us['fields'])):
                a, b = cs['fields'][name], us['fields'][name]
                if any(s.get('constraints', {}).get(k) for s in (a, b) for k in ('readOnly', 'writeOnly')):
                    excluded[name] = 'SERVER_MANAGED_OR_WRITE_ONLY'
                elif a.get('status') != 'declared' or b.get('status') != 'declared' or not a.get('assertion_sha256'):
                    excluded[name] = 'NONSCALAR_OR_AMBIGUOUS_SCHEMA'
                elif a['assertion_sha256'] != b.get('assertion_sha256'):
                    excluded[name] = 'DECLARED_FIELD_ASSERTIONS_DIFFER'
                else:
                    fields[name] = {'create_schema': a, 'update_schema': b}
            get = by_route.get(('GET', update['path']))
            read = (get or {}).get('responses', {}).get('200', {})
            pairs.append({'id': digest(canonical([create['key'], update['key']])),
                          'create_operation': create['key'], 'update_operation': update['key'],
                          'collection_route': create['path'], 'item_route': update['path'],
                          'relationship_basis': basis, 'fields': fields, 'excluded_fields': excluded,
                          'read_operation': (get or {}).get('key'), 'read_schema': read,
                          'creation_links': [v for v in create['links'] if v['response_status'] == '201'],
                          'create_path_parameters': [v['name'] for v in create['parameters'] if v['in'] == 'path'],
                          'provenance': [create['provenance'], update['provenance']],
                          'unavailable_reasons': [] if fields else ['NO_EQUIVALENT_DECLARED_SCALAR_FIELDS']})
        result[update['key']] = {'status': 'structural_candidate' if any(p['fields'] for p in pairs) else 'unknown',
                                 'pairs': pairs, 'unavailable_reasons': reasons}
    return result
