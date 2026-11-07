"""Reused historical measurements; callers must establish capture and schema scope."""
from historical_providers import evaluate, equal


def roundtrip(sent, readback, fields, formats):
    return evaluate({'family': 'RT-1', 'source': 'raw-http-adapter', 'status': 200,
                     'sent': sent, 'readback': readback, 'readable_fields': fields,
                     'field_formats': formats, 'context': qualified_context()})['facts']


def qualified_context():
    # Only used after the caller checked these conditions on raw exchanges.
    return dict.fromkeys(('same_run', 'ordered', 'complete', 'same_resource',
                          'same_actor', 'no_intervening_write'), True)


def failed_update(status, before, request, after):
    if status >= 500:
        return evaluate({'family': 'ATOM-1-2', 'source': 'raw-http-adapter', 'status': status,
                         'operation': 'update', 'before': before, 'after': after,
                         'request': request, 'context': qualified_context()})['facts']
    # Historical provider excludes 4xx. Extend the same comparisons without
    # fabricating a 500 or feeding a producer verdict to that provider.
    states = {}
    for key, desired in request.items():
        if key not in before or equal(desired, before[key]):
            continue
        states[key] = ('unknown' if key not in after else
                       'applied' if equal(after[key], desired) else
                       'kept' if equal(after[key], before[key]) else 'other')
    values = set(states.values())
    outcome = ('partial' if values == {'applied', 'kept'} else
               'committed_despite_error' if values == {'applied'} else
               'rolled_back' if values == {'kept'} else 'unknown')
    return {'atomicity': outcome, 'field_states': states, 'server_error': False}


def project_read(body, binding):
    """Project declared object identities; retain missing/unknown as missing."""
    result = dict(body)
    for field, meta in binding.get('fields', {}).items():
        projection = meta.get('read_projection')
        if projection:
            value = body.get(field)
            if isinstance(value, dict) and projection in value:
                result[field] = value[projection]
            elif value is None and field in body:
                result[field] = None  # observable absence; not an invented zero ID
            else:
                result.pop(field, None)
    return result
