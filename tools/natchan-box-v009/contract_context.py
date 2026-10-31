"""Contract-only derivation. Names suggest candidates; they never establish foreign keys."""
import re
from urllib.parse import urlsplit

from common import InputError, Unsupported

METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
FIELD_KEYS = ('type', 'format', 'enum', 'minimum', 'maximum', 'exclusiveMinimum',
              'exclusiveMaximum', 'minLength', 'maxLength', 'minItems', 'maxItems',
              'pattern', 'readOnly', 'writeOnly', 'nullable', 'const', 'default')


def esc(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def at(pointer, name):
    return pointer + '/' + esc(name)


class Contract:
    def __init__(self, doc):
        if not isinstance(doc, dict):
            raise InputError('CONTRACT_OBJECT_REQUIRED')
        if not (str(doc.get('openapi', '')).startswith('3.0.') or
                str(doc.get('openapi', '')).startswith('3.1.') or doc.get('swagger') == '2.0'):
            raise Unsupported('OPENAPI_VERSION_UNSUPPORTED')
        if not isinstance(doc.get('paths'), dict):
            raise InputError('CONTRACT_PATHS_REQUIRED')
        self.doc = doc
        self.gaps = []
        self.schema_nodes = 0

    def resolve(self, obj, pointer, seen=()):
        if not isinstance(obj, dict):
            raise InputError('CONTRACT_OBJECT_INVALID')
        if '$ref' not in obj:
            return obj, pointer
        ref = obj['$ref']
        if not isinstance(ref, str):
            raise InputError('CONTRACT_REFERENCE_INVALID')
        if not ref.startswith('#/') or ref in seen or len(seen) >= 40:
            self.gaps.append({'code': 'UNRESOLVED_REFERENCE', 'pointer': pointer, 'ref': ref})
            return {}, pointer
        if set(obj) - {'$ref', 'description', 'summary'}:
            # 3.1 schema $ref siblings can add constraints. Do not silently discard them.
            self.gaps.append({'code': 'REF_SIBLING_CONSTRAINTS_UNSUPPORTED', 'pointer': pointer})
            return {}, pointer
        target = self.doc
        try:
            for part in ref[2:].split('/'):
                target = target[part.replace('~1', '/').replace('~0', '~')]
        except (KeyError, TypeError):
            raise InputError('DANGLING_LOCAL_REFERENCE')
        return self.resolve(target, ref, (*seen, ref))

    def schema(self, obj, pointer, depth=0, active=()):
        self.schema_nodes += 1
        if self.schema_nodes > 100_000:
            raise Unsupported('CONTRACT_DERIVATION_NODE_LIMIT_100000')
        if type(obj) is bool:
            return {'status': 'unknown', 'provenance': pointer, 'reason': 'BOOLEAN_SCHEMA_NOT_INTERPRETED'}
        obj, pointer = self.resolve(obj, pointer)
        if pointer in active:
            self.gaps.append({'code': 'RECURSIVE_SCHEMA', 'pointer': pointer})
            return {'status': 'unknown', 'provenance': pointer, 'reason': 'RECURSIVE_SCHEMA'}
        active = (*active, pointer)
        if depth > 20:
            self.gaps.append({'code': 'SCHEMA_DEPTH_LIMIT', 'pointer': pointer})
            return {'status': 'unknown', 'provenance': pointer}
        if not obj:
            return {'status': 'unknown', 'provenance': pointer}
        result = {'status': 'declared', 'provenance': pointer,
                  'constraints': {k: obj[k] for k in FIELD_KEYS if k in obj}}
        if any(k in obj for k in ('allOf', 'oneOf', 'anyOf', 'not', 'if', 'then', 'else')):
            result['status'] = 'ambiguous'
            result['reason'] = 'COMPOSED_SCHEMA_NOT_INTERPRETED'
        if 'required' in obj:
            if not isinstance(obj['required'], list) or not all(isinstance(x, str) for x in obj['required']):
                raise InputError('SCHEMA_REQUIRED_INVALID')
            result['required'] = obj['required']
        props = obj.get('properties', {})
        if not isinstance(props, dict):
            raise InputError('SCHEMA_PROPERTIES_INVALID')
        if props:
            result['fields'] = {k: self.schema(v, at(at(pointer, 'properties'), k), depth + 1, active)
                                for k, v in sorted(props.items())}
        if 'items' in obj:
            if isinstance(obj['items'], dict):
                result['items'] = self.schema(obj['items'], at(pointer, 'items'), depth + 1, active)
            else:
                result['status'] = 'ambiguous'
        return result

    def response_schema(self, value, pointer):
        value, pointer = self.resolve(value, pointer)
        if 'schema' in value:
            return self.schema(value['schema'], at(pointer, 'schema'))
        content = value.get('content', {})
        if not isinstance(content, dict):
            raise InputError('RESPONSE_CONTENT_INVALID')
        choices = [(k, v) for k, v in content.items()
                   if k == 'application/json' or k.endswith('+json')]
        if len(choices) == 1 and isinstance(choices[0][1], dict) and 'schema' in choices[0][1]:
            k, v = choices[0]
            return self.schema(v['schema'], at(at(at(pointer, 'content'), k), 'schema'))
        return {'status': 'unknown', 'provenance': pointer,
                'reason': 'JSON_RESPONSE_SCHEMA_NOT_UNIQUE'}


def derive(doc, contract_hash):
    c = Contract(doc)
    operations = []
    for path, raw_item in sorted(doc['paths'].items()):
        if not isinstance(path, str) or not path.startswith('/'):
            raise InputError('CONTRACT_PATH_INVALID')
        item, item_pointer = c.resolve(raw_item, at('#/paths', path))
        for method in sorted(METHODS & set(item)):
            if len(operations) >= 10_000:
                raise Unsupported('CONTRACT_OPERATION_LIMIT_10000')
            pointer = at(item_pointer, method)
            op, _ = c.resolve(item[method], pointer)
            responses = op.get('responses')
            if not isinstance(responses, dict) or not responses:
                raise InputError('OPERATION_RESPONSES_REQUIRED')
            response_schemas = {}
            links = []
            for status, value in sorted(responses.items()):
                if not isinstance(status, str) or not re.fullmatch(r'(?:[1-5][0-9]{2}|[1-5]XX|default)', status):
                    raise InputError('RESPONSE_STATUS_KEY_INVALID')
                rp = at(at(pointer, 'responses'), status)
                response, rp = c.resolve(value, rp)
                response_schemas[status] = c.response_schema(response, rp)
                raw_links = response.get('links', {})
                if not isinstance(raw_links, dict):
                    raise InputError('RESPONSE_LINKS_INVALID')
                for name, raw_link in sorted(raw_links.items()):
                    link, lp = c.resolve(raw_link, at(at(rp, 'links'), name))
                    links.append({'status': 'declared', 'provenance': lp,
                                  'operationId': link.get('operationId'),
                                  'operationRef': link.get('operationRef'),
                                  'parameters': link.get('parameters', {}),
                                  'interpretation': 'operation_link_not_foreign_key_proof'})
            if not isinstance(item.get('parameters', []), list) or not isinstance(op.get('parameters', []), list):
                raise InputError('OPERATION_PARAMETERS_INVALID')
            raw_params = item.get('parameters', []) + op.get('parameters', [])
            params = []
            request_schema = None
            for i, raw in enumerate(raw_params):
                # Distinguish path-item and operation parameter provenance.
                inherited = i < len(item.get('parameters', []))
                pp = at(at(item_pointer if inherited else pointer, 'parameters'),
                        i if inherited else i - len(item.get('parameters', [])))
                param, pp = c.resolve(raw, pp)
                if param.get('in') == 'body':
                    request_schema = c.schema(param.get('schema', {}), at(pp, 'schema'))
                else:
                    params.append({'name': param.get('name'), 'in': param.get('in'),
                                   'required': param.get('required', False), 'provenance': pp,
                                   'schema': c.schema(param.get('schema', param), at(pp, 'schema') if 'schema' in param else pp)})
            if 'requestBody' in op:
                rb, rbp = c.resolve(op['requestBody'], at(pointer, 'requestBody'))
                request_schema = c.response_schema(rb, rbp)
            read_schemas = [s for code, s in response_schemas.items() if code.startswith('2') and s.get('status') == 'declared']
            object_reads = [s for s in read_schemas if s.get('fields') or s.get('constraints', {}).get('type') == 'object']
            role = 'unknown'
            if method == 'get':
                role = 'read_one_candidate' if path.endswith('}') and object_reads else 'read_many_candidate'
            elif method in ('put', 'patch'):
                role = 'update_candidate'
            elif method == 'delete':
                role = 'delete_candidate'
            elif method == 'post':
                role = 'create_or_action_candidate'
            operations.append({'key': method.upper() + ' ' + path, 'method': method.upper(),
                               'path': path, 'operationId': op.get('operationId'),
                               'provenance': pointer, 'role': {'value': role, 'status': 'ambiguous',
                               'reason': 'HTTP_METHOD_AND_PATH_ARE_NOT_BUSINESS_SEMANTICS'},
                               'parameters': params, 'request_schema': request_schema,
                               'responses': response_schemas, 'links': links,
                               'security': op.get('security', doc.get('security', [])),
                               'entity': {'status': 'unknown', 'reason': 'ENTITY_IDENTITY_NOT_PROVEN'},
                               'placement_candidate': path.rsplit('/', 2)[0] if path.count('{') > 1 else None})
    security_pointer = '#/components/securitySchemes' if 'openapi' in doc else '#/securityDefinitions'
    security = doc.get('components', {}).get('securitySchemes', {}) if 'openapi' in doc else doc.get('securityDefinitions', {})
    if not isinstance(security, dict):
        raise InputError('SECURITY_SCHEMES_INVALID')
    schemes = {k: {'status': 'declared', 'provenance': at(security_pointer, k),
                   'definition': c.resolve(v, at(security_pointer, k))[0]}
               for k, v in sorted(security.items())}
    bases = set()
    if 'basePath' in doc:
        if not isinstance(doc['basePath'], str):
            raise InputError('BASE_PATH_INVALID')
        bases.add(doc['basePath'].rstrip('/'))
    for server in doc.get('servers', []):
        if not isinstance(server, dict) or not isinstance(server.get('url'), str):
            raise InputError('SERVER_URL_INVALID')
        if '{' not in server['url']:
            bases.add(urlsplit(server['url']).path.rstrip('/'))
    entities = {}
    for op in operations:
        if op['method'] != 'GET':
            continue
        for code, schema in op['responses'].items():
            if not code.startswith('2'):
                continue
            item_schema = schema.get('items', schema)
            if not item_schema.get('fields'):
                continue
            sp = item_schema['provenance']
            entry = entities.setdefault(sp, {'schema_pointer': sp, 'status': 'candidate',
                                            'reason': 'RESPONSE_SCHEMA_NOT_PROOF_OF_RESOURCE_IDENTITY',
                                            'read_operations': [],
                                            'identifier_fields': {'status': 'unknown', 'candidates': []}})
            entry['read_operations'].append(op['key'])
            entry['identifier_fields']['candidates'] = sorted(
                k for k in item_schema['fields'] if k.lower() in ('id', 'uuid', 'key') or k.lower().endswith('_id'))
    for entry in entities.values():
        entry['read_operations'] = sorted(set(entry['read_operations']))
    return {'schema_version': 'natchan-contract-context/1', 'derivation_version': '009-dev.1',
            'contract_sha256': contract_hash, 'knowledge_policy': 'contract-only',
            'operations': operations, 'entity_candidates': [entities[k] for k in sorted(entities)],
            'api_base_paths': sorted(bases),
            'security_schemes': schemes,
            'session_ending_operations': {'status': 'unknown', 'reason': 'NOT_INFERRED_FROM_NAMES'},
            'references': {'status': 'unknown', 'reason': 'SCHEMA_REF_IS_NOT_A_FOREIGN_KEY'},
            'gaps': sorted(c.gaps, key=lambda x: (x['pointer'], x['code']))}
