"""Whitelisted raw exchanges only. No oracle, action, logical-name or verdict inputs."""
from pathlib import Path
from urllib.parse import urlsplit

from common import InputError, Unsupported, digest, loads, read

MAX_BYTES = 512 * 1024 * 1024
MAX_HAR_BYTES = 64 * 1024 * 1024  # bounded JSON document reader; explicit refusal above it
MAX_LINE_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 100_000
RAW_KEYS = {'method', 'url', 'path', 'status', 'input', 'response', 'actor',
            'epoch', 'case_id', 'request_id', 't_utc', 'request_headers', 'response_headers'}


def headers(value):
    if isinstance(value, list):
        result = {}
        for h in value:
            if not isinstance(h, dict) or not isinstance(h.get('name'), str) or not isinstance(h.get('value'), str):
                raise InputError('INVALID_HTTP_HEADERS')
            if h['name'].lower() == 'x-request-id' and h['name'].lower() in result:
                raise InputError('AMBIGUOUS_REQUEST_ID_HEADER')
            result[h['name'].lower()] = h['value']
        return result
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise InputError('INVALID_HTTP_HEADERS')
    result = {}
    for k, v in value.items():
        if k.lower() == 'x-request-id' and k.lower() in result:
            raise InputError('AMBIGUOUS_REQUEST_ID_HEADER')
        result[k.lower()] = v
    return result


def shape(body):
    # Values/field names are not needed for the first S7 classifier and are not emitted.
    if body is None:
        return 'unavailable_or_null'
    if isinstance(body, dict):
        return 'object'
    if isinstance(body, list):
        return 'array'
    if isinstance(body, bool):
        return 'boolean'
    if isinstance(body, (int, float)):
        return 'number'
    if isinstance(body, str):
        return 'string'
    raise InputError('INVALID_HTTP_BODY_TYPE')


def normalize(raw, source):
    if not isinstance(raw, dict):
        raise InputError('HTTP_RECORD_OBJECT_REQUIRED')
    r = {k: v for k, v in raw.items() if k in RAW_KEYS}
    method, uri, status = r.get('method'), r.get('url', r.get('path')), r.get('status')
    if not isinstance(method, str) or not method.isalpha() or method != method.upper():
        raise InputError('HTTP_METHOD_INVALID')
    if not isinstance(uri, str) or not uri or any(ch in uri for ch in '\r\n\x00'):
        raise InputError('HTTP_URL_INVALID')
    try:
        parsed = urlsplit(uri)
    except ValueError as e:
        raise InputError('HTTP_URL_INVALID') from e
    if not parsed.path.startswith('/') or (parsed.scheme and parsed.scheme not in ('http', 'https')):
        raise InputError('HTTP_URL_INVALID')
    if status is not None and (type(status) is not int or (status != 0 and not 100 <= status <= 599)):
        raise InputError('HTTP_STATUS_INVALID')
    req_h = headers(r.get('request_headers', {}))
    res_h = headers(r.get('response_headers', {}))
    identifiers = [v for v in (r.get('request_id'), req_h.get('x-request-id'), res_h.get('x-request-id')) if v]
    if any(not isinstance(v, str) for v in identifiers):
        raise InputError('REQUEST_ID_INVALID')
    if len(set(identifiers)) > 1:
        raise InputError('REQUEST_ID_CONFLICT')
    request_id = identifiers[0] if identifiers else None
    if request_id is not None and not isinstance(request_id, str):
        raise InputError('REQUEST_ID_INVALID')
    if request_id and any(marker in request_id.upper() for marker in ('REDACTED', '<TOKEN>', '***')):
        request_id = None
    # Keep only fields actually used by the independent first milestone.
    # Request ID is internal correlation data, never copied into the share output.
    return {'method': method, 'path': parsed.path, 'query_present': bool(parsed.query),
            'status': status or None, 'input_class': shape(r.get('input')),
            'request_id': request_id, 'source': source}


def har_entry(entry, source):
    if not isinstance(entry, dict) or not isinstance(entry.get('request'), dict) or not isinstance(entry.get('response'), dict):
        raise InputError('HAR_EXCHANGE_INVALID')
    req, res = entry['request'], entry['response']
    post = req.get('postData', {})
    if not isinstance(post, dict):
        raise InputError('HAR_POSTDATA_INVALID')
    body = post.get('text')
    if isinstance(body, str):
        try:
            body = loads(body)
        except InputError:
            pass  # form, multipart and plain text remain strings
    # The first S7 milestone does not consume answer bodies, but preserves raw source references.
    return normalize({'method': req.get('method'), 'url': req.get('url'), 'status': res.get('status'),
                      'input': body, 'request_headers': headers(req.get('headers', [])),
                      'response_headers': headers(res.get('headers', []))}, source)


def exchanges(path, fmt, source_hash, stats):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise Unsupported('TRAFFIC_SIZE_LIMIT_512_MIB')
    stats.update(seen=0, ignored_non_http=0)
    if fmt == 'har':
        if path.stat().st_size > MAX_HAR_BYTES:
            raise Unsupported('HAR_DOCUMENT_LIMIT_64_MIB_USE_JSONL')
        doc = loads(read(path, MAX_HAR_BYTES))
        if not isinstance(doc, dict) or not isinstance(doc.get('log'), dict) or not isinstance(doc['log'].get('entries'), list):
            raise InputError('HAR_LOG_ENTRIES_REQUIRED')
        if doc['log'].get('version') != '1.2':
            raise Unsupported('HAR_VERSION_UNSUPPORTED')
        if len(doc['log']['entries']) > MAX_RECORDS:
            raise Unsupported('TRAFFIC_RECORD_LIMIT_100000')
        for i, entry in enumerate(doc['log']['entries']):
            stats['seen'] += 1
            yield har_entry(entry, {'sha256': source_hash, 'record': i, 'locator': '/log/entries/' + str(i)})
        return
    if fmt not in ('http-jsonl', 'journal-jsonl'):
        raise Unsupported('TRAFFIC_FORMAT_UNSUPPORTED')
    with path.open('rb') as stream:
        line_number = 0
        while True:
            raw = stream.readline(MAX_LINE_BYTES + 1)
            if not raw:
                break
            line_number += 1
            if len(raw) > MAX_LINE_BYTES:
                raise Unsupported('JSONL_LINE_LIMIT_16_MIB')
            if not raw.strip():
                continue
            obj = loads(raw)
            if not isinstance(obj, dict):
                raise InputError('HTTP_RECORD_OBJECT_REQUIRED')
            if fmt == 'journal-jsonl' and obj.get('category') != 'research':
                # Deliberately never inspect producer check/measurement contents.
                stats['ignored_non_http'] += 1
                continue
            stats['seen'] += 1
            if stats['seen'] > MAX_RECORDS:
                raise Unsupported('TRAFFIC_RECORD_LIMIT_100000')
            yield normalize(obj, {'sha256': source_hash, 'line_1based': line_number})


def log_signatures(path, source_hash):
    """Unique structured request-ID joins only. Ambiguity never becomes a cause claim."""
    result = {}
    seen = set()
    count = 0
    for line_number, raw in enumerate(read(path, 32 * 1024 * 1024).splitlines(), 1):
        if not raw.strip():
            continue
        count += 1
        try:
            row = loads(raw)
        except InputError:
            continue
        if not isinstance(row, dict) or not isinstance(row.get('request_id'), str):
            continue
        rid = row['request_id']
        if rid in seen:
            result[rid] = None
            continue
        seen.add(rid)
        message = row.get('message', row.get('error'))
        if not isinstance(message, str):
            continue
        if row.get('method') is not None and not isinstance(row['method'], str):
            continue
        if row.get('path') is not None and not isinstance(row['path'], str):
            continue
        try:
            log_path = urlsplit(row['path']).path if row.get('path') else None
        except ValueError:
            continue
        if row.get('status') is not None and (type(row['status']) is not int or not 100 <= row['status'] <= 599):
            continue
        # Mechanical signature hashing; no unredacted log message is emitted.
        import re
        normalized = re.sub(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b', '<id>', message)
        normalized = re.sub(r'\b\d+\b', '<n>', normalized)
        result[rid] = {'signature_sha256': digest(normalized.encode('utf-8')),
                       'source': {'sha256': source_hash, 'line_1based': line_number},
                       'method': row.get('method'), 'path': log_path, 'status': row.get('status')}
    return result, count
