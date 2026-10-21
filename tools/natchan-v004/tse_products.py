"""Product semantics independent of the producing test tool."""
import re


def resolve(schema, document):
    visited = set()
    while isinstance(schema, dict) and '$ref' in schema:
        ref = schema['$ref']
        if not ref.startswith('#/') or ref in visited:
            return {}
        visited.add(ref)
        schema = document
        for key in ref[2:].split('/'):
            schema = schema.get(key.replace('~1', '/').replace('~0', '~'), {})
    return schema if isinstance(schema, dict) else {}


def route_match(template, path):
    return re.fullmatch(re.sub(r'\{[^}]+\}', '[^/]+', template), path.split('?')[0]) is not None


def vikunja_context(row, contract):
    path = row.get('path', '')
    method = row.get('method', '').lower()
    entity = None
    for name in ['labels', 'projects', 'tasks', 'teams', 'shares']:
        if re.search('/' + name + '(?:/[^/]+)?$', path):
            entity = name
    action = 'read' if method == 'get' else 'delete' if method == 'delete' else 'unknown'
    if method == 'put':
        action = 'create'
    elif method in ('post', 'patch'):
        action = 'update'
    route = next((v for k, v in contract.get('paths', {}).items() if route_match(k, path)), {})
    operation = route.get(method, {})
    # Retained Vikunja label reproducers send POST to an item whose Swagger
    # update is PUT. Use its schema only for field projection, never to infer
    # method conformance or an expected status.
    schema_operation = operation or (route.get('put', {}) if method == 'post' and entity == 'labels' else {})
    schema = next((resolve(p.get('schema', {}), contract) for p in schema_operation.get('parameters', []) if p.get('in') == 'body'), {})
    return {'entity': entity, 'operation': action,
            'properties': schema.get('properties', {}), 'documented_statuses': list(operation.get('responses', {}))}


def gitea_context(row, ir):
    path = row.get('path', '')
    method = row.get('method', '').lower()
    for ent in ir.get('entities', []):
        for action, template, verb in [('create', ent.get('path'), ent.get('create_method')),
                                       ('update', ent.get('detail'), ent.get('update_method')),
                                       ('read', ent.get('detail'), 'get')]:
            if template and verb == method and route_match(template, path):
                schema = ent.get(action + '_schema', {}) if action != 'read' else ent.get('read_schema', {})
                # The archived IR can contain either a resolved schema or properties directly.
                properties = schema.get('properties', schema) if isinstance(schema, dict) else {}
                return {'entity': ent['name'].lower(), 'operation': action, 'properties': properties,
                        'documented_statuses': list(ent.get(action, {}).get('responses', {}))}
    return {'entity': None, 'operation': 'unknown', 'properties': {}, 'documented_statuses': []}
