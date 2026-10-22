"""Offline g015 native-tool gateway. Never execute saved tests or call a SUT.

Keep native claims, retained HTTP exchanges and server-log evidence separate.
Summaries are recomputed, not copied from run-meta counters.
"""
import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from engine import analyze


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decoded(value):
    if isinstance(value, dict) and '$base64' in value:
        value = base64.b64decode(value['$base64'], validate=True).decode('utf-8', 'replace')
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def error_family(message):
    # Descriptive log signatures, not known-bug IDs or root-cause conclusions.
    if 'no multipart boundary param in Content-Type' in message:
        return 'multipart_boundary_missing'
    if 'UNIQUE constraint failed: team_unit.team_id, team_unit.type' in message:
        return 'team_unit_unique_constraint'
    if 'team already exists' in message:
        return 'team_already_exists'
    if 'GetRepoInitFile[' in message and 'file does not exist' in message:
        return 'repository_init_template_missing'
    if 'GetLicense[' in message and 'file does not exist' in message:
        return 'repository_license_template_missing'
    if 'Organization does not have owner team' in message:
        return 'organization_owner_team_missing'
    return 'other_server_error_log'


def access_line(line):
    match = re.search(r'router: completed ([A-Z]+) (\S+) for .*?, (\d{3})\b', line)
    return (match[1], match[2], int(match[3])) if match else None


def repository_route(target):
    """Classify nested repository routes; a status alone proves no prerequisites."""
    path = urlsplit(target).path
    path = re.sub(r'^/api/v1(?=/)', '', path)
    match = re.fullmatch(r'/repos/([^/]+)/([^/]+)/(.*)', path)
    if not match:
        return None
    tail = match[3]
    family = '/repos/{owner}/{repo}/' + tail.split('/')[0]
    issue_update = re.fullmatch(r'issues/[^/]+', tail) is not None
    return family, issue_update


def multipart_context(request, status):
    headers = request.get('headers', {})
    value = next((v for k, v in headers.items() if k.lower() == 'content-type'), '')
    if isinstance(value, list):
        value = value[0] if value else ''
    missing = (isinstance(value, str) and value.split(';', 1)[0].strip().lower() == 'multipart/form-data'
               and not re.search(r';\s*boundary\s*=\s*(?:"[^"]+"|[^;\s"]+)', value, re.I))
    return dict(content_type=value, multipart_missing_boundary=bool(missing),
                malformed_multipart_500=bool(missing and status == 500))


def source(path, record):
    return dict(file=str(path), sha256=sha(path), record=record)


def observation(run, tool, version, src, **values):
    return dict(id=run + ':' + str(src['record']), product='gitea',
                product_version=version, run_id=run, tool=tool, source=src,
                facts={}, fact_basis='recomputed', **values)


def scan_logs(path):
    errors = Counter()
    methods = Counter()
    statuses = Counter()
    rows = []
    digest = sha(path)
    route_counts = defaultdict(Counter)
    nested_statuses = Counter()
    issue_updates = Counter()
    route_witnesses = defaultdict(list)
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if '[E]' in line:
            family = error_family(line)
            errors[family] += 1
        access = access_line(line)
        if access:
            method, target, status = access
            statuses[str(status)] += 1
            route = repository_route(target)
            if route:
                family, is_issue = route
                status_class = str(status // 100) + 'xx'
                route_counts[method + ' ' + family][status_class] += 1
                nested_statuses[status_class] += 1
                if method == 'PATCH' and is_issue:
                    issue_updates[status_class] += 1
                key = method + ' ' + family + ':' + status_class
                if len(route_witnesses[key]) < 3:
                    route_witnesses[key].append(dict(path=urlsplit(target).path, status=status,
                        source=dict(file=str(path), sha256=digest, record=number)))
            if status >= 500:
                methods[method + ' ' + urlsplit(target).path] += 1
                rows.append(dict(method=method, path=urlsplit(target).path, status=status,
                                 source=dict(file=str(path), sha256=digest, record=number)))
    return dict(completed_requests=sum(statuses.values()), statuses=dict(statuses),
                http_5xx=sum(v for k, v in statuses.items() if 500 <= int(k) < 600),
                error_log_families=dict(errors), server_5xx_paths=dict(methods),
                repository_reach=dict(nested_status_classes=dict(nested_statuses),
                    successful_nested_responses=nested_statuses['2xx'],
                    issue_patch_status_classes=dict(issue_updates),
                    by_method_family={k: dict(v) for k, v in sorted(route_counts.items())},
                    witnesses=dict(route_witnesses),
                    assessment='no_successful_nested_repository_response_observed' if nested_statuses and not nested_statuses['2xx'] else
                               'nested_repository_success_observed' if nested_statuses['2xx'] else 'no_nested_repository_requests',
                    rejection_cause='not_inferred_from_access_status_only')), rows


def schemathesis(folder, version):
    observations = []
    checked = Counter()
    native_groups = defaultdict(lambda: dict(occurrences=0, witnesses=[]))
    statuses = Counter()
    phases = Counter()
    seen = set()
    for path in sorted(folder.glob('report-round*/*.ndjson')):
        digest = sha(path)
        with path.open(encoding='utf-8-sig') as stream:
            for line_number, line in enumerate(stream, 1):
                event = json.loads(line)
                finished = event.get('EngineFinished')
                if finished:
                    phases[finished.get('stop_reason', 'unknown')] += 1
                recorder = event.get('ScenarioFinished', {}).get('recorder', {})
                checks = recorder.get('checks', {})
                label = recorder.get('label')
                for case_id, exchange in recorder.get('interactions', {}).items():
                    # A case may appear in more than one recorder snapshot. A distinct
                    # timestamp is a distinct physical attempt, even with the same body.
                    identity = (str(path), case_id, exchange.get('timestamp'))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    req = exchange.get('request', {})
                    res = exchange.get('response')
                    status = res.get('status_code') if isinstance(res, dict) else None
                    context = multipart_context(req, status)
                    statuses[str(status)] += 1
                    failures = [c for c in checks.get(case_id, []) if c.get('status') == 'failure']
                    src = dict(file=str(path), sha256=digest, record=str(line_number) + ':' + case_id)
                    for check in failures:
                        info = check.get('failure_info', {}).get('failure', {})
                        key = (check['name'], info.get('code'), label, status, context['malformed_multipart_500'])
                        group = native_groups[key]
                        group['occurrences'] += 1
                        if len(group['witnesses']) < 3:
                            group['witnesses'].append(dict(source=src, failure=info,
                                actual_path=urlsplit(req.get('uri', '')).path,
                                request_content_type=context['content_type']))
                        checked[check['name']] += 1
                    if failures or type(status) is int and status >= 500:
                        o = observation(folder.name, 'schemathesis', version, src,
                                        method=req.get('method'), path=urlsplit(req.get('uri', '')).path,
                                        status=status, request=decoded(req.get('body')),
                                        response=decoded(res.get('content')) if isinstance(res, dict) else None,
                                        operation_label=label, native_checks=failures,
                                    request_content_type=context['content_type'],
                                        evidence_tier='retained_native_http_exchange')
                        o['facts'].update(context)
                        observations.append(o)
    groups = [dict(check=k[0], native_code=k[1], operation=k[2], status=k[3], malformed_multipart_500=k[4], **v)
              for k, v in sorted(native_groups.items(), key=lambda pair: str(pair[0]))]
    return observations, dict(recorded_interactions=sum(statuses.values()),
                              recorded_statuses=dict(statuses),
                              recorded_http_5xx=sum(v for k, v in statuses.items() if k.isdigit() and 500 <= int(k) < 600),
                              failed_check_occurrences=dict(checked),
                              native_issue_groups=groups, engine_stop_reasons=dict(phases))


def evomaster(folder, version):
    path = folder / 'report.json'
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    entries = report['faults']['foundFaults']
    native = []
    for index, fault in enumerate(entries):
        o = observation(folder.name, 'evomaster', version, source(path, 'fault:' + str(index)),
                        native_fault=fault, evidence_tier='native_tool_claim')
        native.append(o)
    return native, dict(tool_version=report.get('toolVersion'),
                        declared_fault_total=report['faults']['totalNumber'],
                        fault_entries=len(entries),
                        counter_mismatch=report['faults']['totalNumber'] != len(entries),
                        categories=dict(Counter(str(c['code']) for f in entries for c in f['faultCategories'])),
                        native_faults=entries, total_tests=report.get('totalTests'),
                        rest_statistics=report.get('problemDetails', {}).get('rest'),
                        saved_python_tests_executed=False)


def run(folder, output):
    if output.exists():
        raise ValueError('Use a fresh output directory')
    parts = []
    summaries = []
    inputs = []
    for directory in sorted(folder.iterdir()):
        if not directory.is_dir() or not (directory / 'run-meta.json').is_file():
            continue
        metadata = json.loads((directory / 'run-meta.json').read_text(encoding='utf-8-sig'))
        tool, version = metadata['tool'], metadata['gitea']
        logs, actual_server_errors = scan_logs(directory / 'sut.log')
        if tool == 'schemathesis':
            observations, native = schemathesis(directory, version)
        elif tool == 'evomaster':
            observations, native = evomaster(directory, version)
            # No full EvoMaster request journal is present. Server access lines
            # prove response statuses, but cannot supply payloads or state.
            observations += [observation(directory.name, tool, version, r['source'],
                              method=r['method'], path=r['path'], status=r['status'],
                              evidence_tier='server_access_status_without_payload')
                             for r in actual_server_errors]
        else:
            raise ValueError('Unsupported native tool: ' + tool)
        summary = dict(run=directory.name, tool=tool, version=version,
                       elapsed_minutes=metadata['elapsed_minutes'], server=logs, native=native,
                       metadata_counters_agree=(logs['http_5xx'] == metadata['sut_log_500'] and
                                                logs['completed_requests'] == metadata['sut_log_completed_requests']))
        summaries.append(summary)
        run_info = dict(id=directory.name, product='gitea', version=version, tool=tool,
                        http_records=None, native_evidence=summary)
        parts.append((directory.name, dict(observations=observations, runs=[run_info])))
        for path in sorted(directory.rglob('*')):
            if path.is_file() and (path.name in ('run-meta.json', 'report.json', 'sut.log') or path.suffix == '.ndjson'):
                inputs.append(dict(path=str(path), sha256=sha(path)))
    if not parts:
        raise ValueError('No supported native runs')
    report = analyze(parts)
    report['input_inventory'] = inputs
    report['gateway_code_sha256'] = sha(Path(__file__))
    report['g015_runs'] = summaries
    report['g015_repository_reach'] = dict(
        nested_status_classes=dict(sum((Counter(r['server']['repository_reach']['nested_status_classes']) for r in summaries), Counter())),
        issue_patch_status_classes=dict(sum((Counter(r['server']['repository_reach']['issue_patch_status_classes']) for r in summaries), Counter())),
        causal_explanation='Statuses do not establish why a request was rejected; request/response evidence is required.',
        business_coverage='A lack of successful repository-scoped responses does not demonstrate evaluation of issue/reference state invariants.')
    report['external_confirmation_coverage'] = {'B-OWNERS': dict(
        status='not_evaluable_confirmation_artifact_not_supplied',
        baseline_owner_team_log_lines=sum(r['server']['error_log_families'].get('organization_owner_team_missing', 0) for r in summaries),
        required_evidence=['successful Owners-team rename request and response',
                           'same authenticated actor and initial owner-role evidence',
                           'ordered subsequent organization edit and team-delete requests and responses'],
        attribution='Independent cloud confirmation must be a separate run; a user narrative is not raw evidence.')}
    report['limitations_g015'] = [
        'Counts are observations or native issue groups, not independent bugs.',
        'Native checker assertions are retained as native claims; no full input contract was included.',
        'No automatic causal join of adjacent server error messages to requests was made.',
        'Error log families are descriptive signatures, not root-cause proof or known-bug matches.',
        'EvoMaster saved tests were not executed; server status logs and native faults remain separate.',
        'No independent before/after snapshots: atomicity and business-state coverage are not established.',
        'Known-bug nonmatches mean not demonstrated by these adapters, not proof of absence.'
    ]
    output.mkdir(parents=True)
    (output / 'analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (output / 'summary.json').write_text(json.dumps(dict(runs=summaries,
        repository_reach=report['g015_repository_reach'], external_confirmations=report['external_confirmation_coverage'],
        rule_occurrences=report['rule_occurrences'], limitations=report['limitations_g015']), ensure_ascii=False, indent=2))
    render(report, output)
    print(json.dumps(dict(output=str(output), runs=len(summaries), rules=report['rule_occurrences'])))
    return report


def render(report, output):
    text = ['# Natchan: Gitea g015 native baseline results', '',
            'Generated from raw native reports, NDJSON exchanges and server access logs. No manual finding narrative was used.', '',
            '| Run | Minutes | Server requests | Server 5xx | Retained HTTP 5xx |',
            '|---|---:|---:|---:|---:|']
    for row in report['g015_runs']:
        text.append('|{}|{}|{}|{}|{}|'.format(row['run'], row['elapsed_minutes'], row['server']['completed_requests'], row['server']['http_5xx'], row['native'].get('recorded_http_5xx', 'not available')))
    text += ['', '## Across repetitions', '',
             '| Tool | Server requests | Server 5xx |', '|---|---:|---:|']
    for tool in ('evomaster', 'schemathesis'):
        rows = [r for r in report['g015_runs'] if r['tool'] == tool]
        text.append('|{}|{}|{}|'.format(tool, sum(r['server']['completed_requests'] for r in rows), sum(r['server']['http_5xx'] for r in rows)))
    text += ['', 'All six metadata request/500 counters were independently checked against the server logs: ' +
             str(all(r['metadata_counters_agree'] for r in report['g015_runs'])) + '.', '',
             'Server-log signature counts below are error lines, not additional HTTP failures. '
             'The owner-team message does not by itself prove a failed HTTP response. '
             'Generic server-error rules can both match the same observation; do not add their counts.', '']
    text += ['', '## Repository reach (recomputed from all access-log responses)', '',
             '| Run | Nested repository 2xx | Nested repository 4xx | Nested repository 5xx | Issue PATCH 2xx | Issue PATCH 4xx |',
             '|---|---:|---:|---:|---:|---:|']
    for row in report['g015_runs']:
        reach = row['server']['repository_reach']
        c, p = reach['nested_status_classes'], reach['issue_patch_status_classes']
        text.append('|{}|{}|{}|{}|{}|{}|'.format(row['run'], c.get('2xx', 0), c.get('4xx', 0), c.get('5xx', 0), p.get('2xx', 0), p.get('4xx', 0)))
    text += ['', 'Combined nested-route status classes: ' + json.dumps(report['g015_repository_reach']['nested_status_classes']) + '.',
             'Combined issue-PATCH status classes: ' + json.dumps(report['g015_repository_reach']['issue_patch_status_classes']) + '.', '',
             report['g015_repository_reach']['business_coverage'],
             report['g015_repository_reach']['causal_explanation'], '',
             'Malformed multipart responses do not establish that an issue, label, milestone or release was reached or created.', '',
             '## Independent B-OWNERS confirmation', '',
             'Status: ' + report['external_confirmation_coverage']['B-OWNERS']['status'] + '.',
             'Baseline owner-team log lines: ' + str(report['external_confirmation_coverage']['B-OWNERS']['baseline_owner_team_log_lines']) + '.',
             'The independent cloud reproduction is not present in this input. No confirmation is attributed to these baseline runs.', '']
    for row in report['g015_runs']:
        text += ['', '## ' + row['run'], '', '### Server error-log signatures (separate from HTTP counts)', '']
        text += ['- {}: {}'.format(k, v) for k, v in row['server']['error_log_families'].items()]
        text += ['', '### Nested repository route coverage', '',
                 '| Method / route family | Response classes |', '|---|---|']
        text += ['|{}|{}|'.format(k, json.dumps(v)) for k, v in row['server']['repository_reach']['by_method_family'].items()]
        text += ['', '### Native tool output', '']
        if row['tool'] == 'evomaster':
            n = row['native']
            text += ['Declared faults: {}; fault entries: {}; mismatch: {}.'.format(n['declared_fault_total'], n['fault_entries'], n['counter_mismatch']), '',
                     'Category counts: ' + json.dumps(n['categories']), '']
            text += ['- {} / categories {} / test {}'.format(f['operationId'], [x['code'] for x in f['faultCategories']], f['testCaseId']) for f in n['native_faults']]
        else:
            text += ['| Native check | Code | Operation template | Actual path examples | Request context | HTTP | Occurrences |', '|---|---|---|---|---|---:|---:|']
            for g in row['native']['native_issue_groups']:
                examples = sorted(set(w['actual_path'] for w in g['witnesses']))
                # Escape pipes so raw URL input cannot break the report table.
                paths = '; '.join(examples).replace('|', '&#124;').replace('\n', ' ')
                context = 'Malformed multipart without boundary; business resource reach not established' if g['malformed_multipart_500'] else 'Native check; no business-state inference'
                text.append('|{}|{}|{}|{}|{}|{}|{}|'.format(g['check'], g['native_code'], g['operation'], paths, context, g['status'], g['occurrences']))
    text += ['', '## Common classifier', '', 'Rule occurrences: ' + json.dumps(report['rule_occurrences']), '',
             'These counts retain evidence tiers and are not combined with server totals or native report counts.', '', '## Limits', '']
    text += ['- ' + x for x in report['limitations_g015']]
    (output / 'report.md').write_text('\n'.join(text) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.input, args.output)
