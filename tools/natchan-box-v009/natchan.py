"""v009 development CLI: derive, freeze, analyze. Offline, contract-only and tool-neutral."""
import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
import sys

# Also works under python -I; never put the v008 runtime on this import path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (InputError, Unsupported, ROOT, VERSION, canonical, digest,
                    engine_hashes, keys, loads, read, write)
from contract_context import derive
from traffic import exchanges, log_signatures
from judge import analyze, CLASSES, VALUES


def hash_file(path):
    h = hashlib.sha256()
    try:
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
    except OSError as e:
        raise InputError('INPUT_UNREADABLE') from e
    return h.hexdigest()


def contract(path):
    if path.suffix.lower() not in ('.json',):
        raise Unsupported('CONTRACT_JSON_REQUIRED_YAML_NOT_YET_SUPPORTED')
    raw = read(path)
    try:
        context = derive(loads(raw), digest(raw))
        if len(canonical(context)) > 32 * 1024 * 1024:
            raise Unsupported('DERIVED_KNOWLEDGE_LIMIT_32_MIB')
        return context
    except (TypeError, KeyError, AttributeError, RecursionError) as e:
        raise InputError('CONTRACT_STRUCTURE_INVALID') from e


def load_context(contract_path, knowledge_path):
    expected = contract(contract_path)
    actual = loads(read(knowledge_path))
    if actual != expected:
        raise InputError('KNOWLEDGE_NOT_CURRENT_CONTRACT_DERIVATION')
    return actual


def make_freeze(contract_path, knowledge_path):
    context = load_context(contract_path, knowledge_path)
    return {'schema_version': 'natchan-contract-freeze/1', 'analyzer_version': VERSION,
            'engine': engine_hashes(), 'contract_sha256': context['contract_sha256'],
            'knowledge_sha256': digest(read(knowledge_path)),
            'knowledge_policy': 'contract-only',
            'registration': 'Commit/register this file before evaluation evidence exists; chronology is not verified by this file.'}


def local_path(parent, value):
    if not isinstance(value, str) or not value:
        raise InputError('INPUT_PATH_REQUIRED')
    return (parent / value).resolve()


def request_inputs(request_path):
    doc = loads(read(request_path))
    keys(doc, {'schema_version', 'run', 'contract', 'knowledge', 'freeze', 'evidence'},
         {'schema_version', 'run', 'contract', 'knowledge', 'freeze', 'evidence'})
    if doc['schema_version'] != 'natchan-semantic-request/1':
        raise Unsupported('REQUEST_SCHEMA_UNSUPPORTED_USE_V008_FOR_LEGACY_REQUESTS')
    keys(doc['run'], {'id', 'product', 'product_version', 'tool', 'repetition', 'start_state'}, {'id', 'product', 'tool', 'start_state'})
    for key in ('id', 'product', 'tool'):
        if not isinstance(doc['run'][key], str) or not doc['run'][key]:
            raise InputError('RUN_METADATA_INVALID')
    for key in ('product', 'tool'):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,127}', doc['run'][key]):
            raise InputError('RUN_METADATA_LABEL_INVALID')
    if doc['run'].get('product_version') is not None and not isinstance(doc['run']['product_version'], str):
        raise InputError('PRODUCT_VERSION_INVALID')
    if doc['run'].get('repetition') is not None and type(doc['run']['repetition']) is not int:
        raise InputError('REPETITION_INVALID')
    if doc['run']['start_state'] not in ('fresh_snapshot', 'accumulated', 'unknown'):
        raise InputError('START_STATE_INVALID')
    keys(doc['evidence'], {'format', 'traffic', 'server_log', 'capture'}, {'format'})
    capture = doc['evidence'].get('capture', {})
    keys(capture, {'complete', 'exclusive', 'ordering'})
    for key in ('complete', 'exclusive'):
        if key in capture and type(capture[key]) is not bool:
            raise InputError('CAPTURE_ASSUMPTION_INVALID')
    if 'ordering' in capture and capture['ordering'] not in ('serial', 'concurrent', 'unknown'):
        raise InputError('CAPTURE_ORDERING_INVALID')
    fmt = doc['evidence']['format']
    if fmt not in ('har', 'http-jsonl', 'journal-jsonl', 'observer-tool-jsonl', 'none'):
        raise Unsupported('TRAFFIC_FORMAT_UNSUPPORTED')
    if fmt != 'none' and 'traffic' not in doc['evidence']:
        raise InputError('TRAFFIC_PATH_REQUIRED')
    if fmt == 'none' and 'traffic' in doc['evidence']:
        raise InputError('NONE_FORMAT_CANNOT_HAVE_TRAFFIC')
    parent = request_path.resolve().parent
    paths = {key: local_path(parent, doc[key]) for key in ('contract', 'knowledge', 'freeze')}
    for key in ('traffic', 'server_log'):
        if key in doc['evidence']:
            paths[key] = local_path(parent, doc['evidence'][key])
    paths['request'] = request_path.resolve()
    return doc, paths


def execute(doc, paths, output):
    inputs = {key: hash_file(path) for key, path in paths.items()}
    context = load_context(paths['contract'], paths['knowledge'])
    frozen = loads(read(paths['freeze']))
    if frozen != make_freeze(paths['contract'], paths['knowledge']):
        raise InputError('EVALUATION_FREEZE_DRIFT')
    logs, log_lines = {}, None
    if 'server_log' in paths:
        logs, log_lines = log_signatures(paths['server_log'], inputs['server_log'])
    stats = {'seen': 0, 'ignored_non_http': 0}
    # A bounded first pass proves request IDs unique before any correlation is used.
    ids = Counter()
    fmt = doc['evidence']['format']
    interval_conflict, latest_end, intervals = False, None, 0
    if fmt != 'none':
        for row in exchanges(paths['traffic'], fmt, inputs['traffic'], {}):
            if logs and row['request_id']:
                ids[row['request_id']] += 1
            if row['started'] is not None and latest_end is not None and row['started'] < latest_end:
                interval_conflict = True
            if row['ended'] is not None:
                latest_end = max(latest_end, row['ended']) if latest_end is not None else row['ended']
            if row['started'] is not None and row['ended'] is not None:
                intervals += 1
    capture = dict(doc['evidence'].get('capture', {}), _contradicted_serial=interval_conflict)
    with (output / 'verdicts.jsonl').open('w', encoding='utf-8', newline='\n') as f:
        if fmt == 'none':
            report = {'exchanges': None, 'groups': [], 'distinct_bugs': None,
                      'unique_server_log_joins': 0, 'producer_verdicts_used': False,
                      'classes': {k: {'name': name, 'implemented': k in ('S1', 'S3', 'S5', 'S7'), 'opportunities': None,
                                      'counts': {v: None for v in VALUES}, 'abstention_reasons': None,
                                      'reason': 'HTTP_TRAFFIC_MISSING'} for k, name in CLASSES.items()}}
        else:
            report = analyze(exchanges(paths['traffic'], fmt, inputs['traffic'], stats), context, f, logs, ids, capture)
    # Never accept a moving input as the input frozen in this report.
    if any(hash_file(path) != inputs[key] for key, path in paths.items()):
        raise InputError('INPUT_CHANGED_DURING_ANALYSIS')
    if engine_hashes() != frozen['engine']:
        raise InputError('ENGINE_CHANGED_DURING_ANALYSIS')
    write(output / 'findings.json', {'schema_version': 'natchan-symptom-groups/1', 'groups': report.pop('groups'),
                                     'distinct_bugs': None, 'counting_unit': 'symptom_groups_not_bugs'})
    write(output / 'coverage.json', {'schema_version': 'natchan-semantic-coverage/1', **report,
                                     'ingestion': stats, 'server_log_lines': log_lines,
                                     'server_log_available': 'server_log' in paths,
                                     'log_correlation_scope': 'unique_structured_request_ids_only'})
    write(output / 'provenance.json', {'schema_version': 'natchan-semantic-provenance/1',
                                      'inputs': inputs, 'engine': engine_hashes(),
                                      'run': {k: v for k, v in doc['run'].items() if k != 'id'},
                                      'run_id_sha256': digest(doc['run']['id'].encode('utf-8')),
                                      'capture_metadata': capture, 'http_intervals_retained': intervals,
                                      'metadata_basis': 'caller_declaration_not_observed_server_version',
                                      'knowledge_policy': 'contract-only', 'producer_verdicts_used': False,
                                      'new_sut_requests': 0, 'chronological_freeze_verified': False})
    # No raw bodies, log messages, local paths, actor names or run labels are copied out.
    lines = ['# Natchan v009 development report', '',
             'Status: PARTIAL. This is a contract-only development milestone, not a v008 replacement.', '',
             'Implemented subsets: S1 same-URI scalar read-back, S3 scalar request constraints,',
             'S5 observed changes after errors, S7 HTTP status checks and unique request-ID log signatures.',
             'S2/S4/S6: not implemented; their counts are null.',
             'S1 requires declared complete, isolated, serial capture plus recorded actor/reset epoch.',
             'S5 changed state is a policy observation; contract atomicity is not inferred.', '',
             'Captured exchanges: ' + str(report['exchanges']),
             'Verdicts marked consistent mean only that the HTTP status is declared.',
             'Symptom groups and log signatures are not proven root causes or distinct bugs.',
             'Contract role/entity/reference ambiguities are retained in the knowledge artifact.',
             'No producer verdicts or known-bug catalogs are used. No SUT requests are sent.', '']
    lines.extend(['## Per-property checks', '', '| Class | Opportunities | Violations | Consistent | Not evaluable | Policy observations |', '|---|---:|---:|---:|---:|---:|'])
    for prop, meta in report['classes'].items():
        vals = [meta['opportunities'], *(meta['counts'][v] for v in VALUES)]
        lines.append('| ' + prop + ' | ' + ' | '.join('null' if n is None else str(n) for n in vals) + ' |')
    lines.extend(['', 'Group details: findings.json. Exact witnesses: verdicts.jsonl.',
                  'Unjoined 5xx: ' + str(report.get('unjoined_server_5xx')), ''])
    (output / 'report.md').write_bytes(('\n'.join(lines)).encode('utf-8'))
    return report


def run(request_path, output):
    request_path, output = Path(request_path), Path(output)
    if output.exists():
        raise InputError('OUTPUT_MUST_BE_NEW_DIRECTORY')
    # An output parent must not contain input files; validation precedes file creation.
    doc, paths = request_inputs(request_path)
    if any(p == output.resolve() or output.resolve() in p.parents for p in paths.values()):
        raise InputError('INPUT_INSIDE_OUTPUT')
    output.mkdir(parents=True)
    try:
        report = execute(doc, paths, output)
        code, reason = 0, None
    except InputError as e:
        code, reason, report = e.code, str(e), None
    except (OSError, UnicodeError) as e:
        code, reason, report = 2, 'INPUT_OR_OUTPUT_IO_ERROR', None
    except Exception:
        code, reason, report = 4, 'UNEXPECTED_ENGINE_ERROR', None
    if code:
        # Never leave partial findings that a pipeline could mistake for a completed judgement.
        for p in output.iterdir():
            if p.is_file():
                p.unlink()
    write(output / 'diagnostics.json', {'code': reason, 'exit_code': code})
    artifacts = {p.name: hash_file(p) for p in sorted(output.iterdir()) if p.is_file()}
    result = {'schema_version': 'natchan-semantic-result/1', 'analyzer_version': VERSION,
              'status': 'PARTIAL' if code == 0 else 'FAILED', 'exit_code': code,
              'artifacts': artifacts, 'new_sut_requests': 0}
    if report is not None:
        result['exchanges'] = report['exchanges']
    write(output / 'result.json', result)  # final commit marker
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('derive', 'freeze'):
        q = sub.add_parser(command)
        q.add_argument('--contract', type=Path, required=True)
        q.add_argument('--output', type=Path, required=True)
        if command == 'freeze':
            q.add_argument('--knowledge', type=Path, required=True)
    q = sub.add_parser('analyze')
    q.add_argument('--request', type=Path, required=True)
    q.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == 'analyze':
            return run(args.request, args.output)['exit_code']
        if args.output.exists():
            raise InputError('OUTPUT_MUST_BE_NEW_FILE')
        obj = contract(args.contract) if args.command == 'derive' else make_freeze(args.contract, args.knowledge)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as f:
            f.write(canonical(obj))
        return 0
    except InputError as e:
        print(json.dumps({'exit_code': e.code, 'reason': str(e)}), file=sys.stderr)
        return e.code
    except (OSError, UnicodeError):
        print('{"exit_code":2,"reason":"INPUT_OR_OUTPUT_IO_ERROR"}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
