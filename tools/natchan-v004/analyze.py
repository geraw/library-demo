"""Natchan v004: retained TSE evidence -> facts -> catalog signatures -> parity report."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'natchan-v003'))
from classifier import classify, same, field_same
from tse_gateways import digest, load_gateway, load_transcript, load_original_oracles, parsed
from tse_products import gitea_context, vikunja_context


def successful(status):
    return type(status) is int and 200 <= status < 300


def observation(run, i, row, context):
    return {'id': run['id'] + ':' + str(i), 'product': run['product'], 'product_version': run['version'],
            'run_id': run['id'], 'tool': run['tool'], 'seed': run.get('seed'),
            'source': dict(run['source'], record=i), 'status': row.get('status'),
            'method': row.get('method'), 'path': row.get('path'), 'entity': context['entity'],
            'action':row.get('action'),
            'operation': context['operation'], 'request': row.get('input', row.get('body')),
            'response': parsed(row.get('response')), 'facts': {}, 'fact_basis': 'recomputed',
            'witnesses': [], 'limitations': [], 'producer': 'natchan-v004'}


def compare_fields(obs, request, after, fields, evidence):
    """Compare retained values, never verdict strings. Caller must establish identity/order."""
    for field in fields:
        if field not in request or field not in after:
            continue  # Missing fields in shortened transcripts are unknown, not dropped.
        if not field_same(obs, field, request[field], after[field]):
            obs['facts']['silent_change'] = True
            obs['facts'].setdefault('changed_fields', []).append(field)
            sent, stored = request[field], after[field]
            if isinstance(sent, str) and isinstance(stored, str):
                changes = obs['facts'].setdefault('field_changes', {}).setdefault(field, {})
                changes.update(sent_length=len(sent),stored_length=len(stored))
                if stored and sent.startswith(stored) and len(stored) < len(sent):
                    obs['facts']['truncation_observed'] = True
                    changes['strict_prefix'] = True
                elif any(stored.endswith(marker) and len(stored) > len(marker) and
                         len(stored) < len(sent) and sent.startswith(stored[:-len(marker)])
                         for marker in ('...', '\u2026')):
                    obs['facts']['truncation_observed'] = True
                    changes['prefix_with_ellipsis'] = True
                if changes.get('strict_prefix') or changes.get('prefix_with_ellipsis'):
                    changes['truncated'] = True
                if stored == sent.strip() or stored == sent.lstrip('#'):
                    obs['facts']['normalization_candidate'] = True
                    changes['normalization_candidate'] = True
            obs['witnesses'].append(dict(evidence, field=field, sent=sent, stored=stored))


def contextual_facts(obs):
    obs['facts'].update({k: obs[k] for k in ['entity', 'operation']})
    response = obs.get('response')
    if isinstance(response, dict) and 'code' in response:
        obs['facts']['response_code'] = response['code']


def log_links(records, text):
    """Bounded unique method/path/time joins. Ambiguous joins remain unresolved."""
    lines = text.splitlines()
    completions = []
    pattern = r'^(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d).*completed (\w+) /api/v1(\S+) .*?, (\d{3}) '
    for i, line in enumerate(lines):
        m = re.search(pattern, line)
        if not m or int(m[4]) < 500:
            continue
        prior = []
        for j in range(i - 1, max(-1, i - 5), -1):
            if 'completed ' in lines[j]:
                break
            if '[E]' in lines[j]:
                prior.append((j, lines[j]))
        completions.append((i, datetime.strptime(m[1], '%Y/%m/%d %H:%M:%S').replace(tzinfo=timezone.utc),
                            m[2], m[3], int(m[4]), prior))
    result = {}
    for n, row in enumerate(records):
        if row.get('category') != 'research' or type(row.get('status')) is not int or row['status'] < 500:
            continue
        try:
            timestamp = datetime.fromisoformat(row['t_utc'])
        except (KeyError, ValueError):
            continue
        eligible = [c for c in completions if c[2:5] == (row.get('method'), row.get('path'), row['status']) and abs((c[1]-timestamp).total_seconds()) <= 2]
        if len(eligible) == 1 and len(eligible[0][5]) == 1:
            c = eligible[0]
            # A completion must also be unique in the opposite direction.
            reverse = [r for r in records if r.get('category') == 'research' and
                       (r.get('method'), r.get('path'), r.get('status')) == c[2:5] and
                       r.get('t_utc') and abs((datetime.fromisoformat(r['t_utc'])-c[1]).total_seconds()) <= 2]
            if len(reverse) == 1:
                result[n] = {'message': c[5][0][1], 'error_line': c[5][0][0]+1,
                             'completion_line': c[0]+1, 'basis': 'unique_method_path_status_time_2s_and_adjacent_error'}
    return result


def gitea_observations(run, data):
    records, ir = data['records'], data['ir']
    links = log_links(records, data['sut_log'])
    observations, native_oracles = [], []
    for i, row in enumerate(records):
        if row.get('category') != 'research':
            native_oracles.append(dict(source=dict(run['source'], record=i), category=row.get('category'), payload=row,
                                       verification='recorded_original_oracle; not independently verified snapshots'))
            continue
        context = gitea_context(row, ir)
        obs = observation(run, i, row, context)
        contextual_facts(obs)
        obs['field_formats'] = {k:v.get('format') for k,v in context['properties'].items() if isinstance(v,dict)}
        if isinstance(context['properties'].get('title'),dict):
            obs['facts']['title_maxlength_absent'] = 'maxLength' not in context['properties']['title']
        if i in links:
            obs['correlated_log'] = links[i]
            obs['server_message'] = links[i]['message']
            message = links[i]['message']
            family = ('missing_assignee' if re.search(r'user does not exist|user redirect does not exist', message, re.I) else
                      'missing_milestone' if re.search(r'milestone does not exist', message, re.I) else
                      'missing_git_object' if re.search(r'object does not exist', message, re.I) else
                      'invalid_tag' if 'release tag name is not valid' in message else
                      'git_argument_nul' if 'invalid argument' in message and 'git' in message else
                      'parse_integer' if 'strconv.ParseInt' in message else 'other')
            obs['facts']['correlated_error_family'] = family
            obs['witnesses'].append({'member': 'sut.log', **links[i]})
        observations.append(obs)
    # RT-1 retains sent/stored values even when its hidden readback is not a model HTTP event.
    # Recompute the value comparison; preserve its provenance as a producer readback measurement.
    for i, row in enumerate(records):
        if row.get('category') != 'roundtrip-check' or row.get('readback_status') != 200:
            continue
        candidates = [o for o in observations if o['path'] == row.get('path') and
                      records[o['source']['record']].get('logical_id') == row.get('logical_id') and
                      records[o['source']['record']].get('action') == row.get('action') and
                      abs(o['source']['record']-i) <= 2 and successful(o['status'])]
        if len(candidates) != 1:
            continue
        obs = candidates[0]
        for field, values in row.get('mismatches', {}).items():
            if not isinstance(values, dict) or not {'sent', 'stored'} <= values.keys():
                continue
            # Request must agree with measurement; no trust in the producer's mismatch label.
            request = obs.get('request')
            if not isinstance(request, dict) or field not in request or not same(request[field], values['sent']):
                continue
            compare_fields(obs, request, {field: values['stored']}, [field],
                           {'record': i, 'basis': 'recorded_readback_values'})
            if (field == 'title' and obs['entity'] in ('issue','milestone') and
                    isinstance(values['sent'],str) and values['stored'] == values['sent'].strip() and values['stored'] != values['sent']):
                obs['facts']['familiar_normalization'] = True
            if (field == 'color' and obs['entity'] == 'label' and isinstance(values['sent'],str) and
                    values['sent'].startswith('#') and values['stored'] == values['sent'][1:]):
                obs['facts']['familiar_normalization'] = True
            if obs['entity'] == 'milestone' and field == 'due_on':
                obs['field_formats'] = {field: 'date-time'}
                # Re-evaluate time equivalence; earlier generic comparison is not an instant comparison.
                if field_same(obs, field, values['sent'], values['stored']):
                    obs['facts']['changed_fields'] = [f for f in obs['facts'].get('changed_fields', []) if f != field]
                    obs['facts']['silent_change'] = bool(obs['facts']['changed_fields'])
                elif isinstance(values['stored'],str) and 'T23:59:59' in values['stored']:
                    obs['facts']['due_time_replaced_by_end_of_day'] = True
            obs.setdefault('measurement_sources', []).append(dict(run['source'], record=i))
    # Sequence witness: accepted stored ref followed by a failed rename on that same release.
    for obs in observations:
        if obs['entity'] != 'release' or obs.get('status') != 500 or obs['facts'].get('correlated_error_family') != 'missing_git_object':
            continue
        request = obs.get('request') or {}
        pos = obs['source']['record']
        preceding = [o for o in observations if o['source']['record'] < pos and o['path'] == obs['path']]
        before = next((o for o in reversed(preceding) if o['method'] == 'GET' and successful(o['status']) and isinstance(o['response'], dict)), None)
        if not before:
            continue
        value = before['response'].get('target_commitish')
        if not value or request.get('target_commitish') != value or request.get('tag_name') == before['response'].get('tag_name'):
            continue
        writers = [o for o in preceding if o['operation'] == 'update' and successful(o['status']) and
                   isinstance(o.get('request'), dict) and o['request'].get('target_commitish') == value]
        if writers:
            writer = writers[-1]
            intervening = [o for o in preceding if writer['source']['record'] < o['source']['record'] and o['operation'] in ('create','update','delete')]
            if not intervening:
                obs['facts']['stored_reference_then_failed_rename'] = True
                obs['witnesses'].extend([{'accepted_write': writer['source']}, {'stored_preimage': before['source']}])
    return observations, native_oracles


def vikunja_observations(run, data, contract):
    rows = data['records']
    observations = []
    for i, row in enumerate(rows):
        context = vikunja_context(row, contract)
        obs = observation(run, i, row, context)
        contextual_facts(obs)
        request = obs.get('request')
        response = obs.get('response')
        path = row.get('path', '')
        target = path
        if obs['operation'] == 'create' and isinstance(response, dict) and response.get('id') is not None and obs['entity']:
            target = '/' + obs['entity'] + '/' + str(response['id'])
            if obs['entity'] == 'shares':
                target = path + '/' + str(response['id'])
        before = next(((j, r) for j, r in reversed(list(enumerate(rows[:i]))) if r.get('method') == 'GET' and r.get('path') == target and successful(r.get('status'))), None)
        after = None
        for j in range(i+1, len(rows)):
            r = rows[j]
            if r.get('method') != 'GET':
                break  # Conservative: any intervening write blocks readback association.
            if r.get('path') == target and successful(r.get('status')) and isinstance(r.get('response'), dict):
                after = (j, r)
                break
        if after and isinstance(request, dict) and successful(obs['status']):
            # Resolve schema-writable fields. Absent fields are not assumed observable.
            fields = [k for k in request if k in context['properties'] and not context['properties'][k].get('readOnly')]
            obs['field_formats'] = {k: v.get('format') for k,v in context['properties'].items() if isinstance(v,dict)}
            compare_fields(obs, request, after[1]['response'], fields,
                           {'record': after[0], 'basis': 'ordered_same_resource_single_client_readback'})
            obs['facts']['readback_verified'] = True
            for field in fields:
                value = request[field]
                stored = after[1]['response'].get(field)
                if same(value, stored):
                    if field == 'title' and value == '':
                        obs['facts']['empty_title_stored'] = True
                    if field == 'title' and isinstance(value, str) and re.search(r'[\x00-\x1f]', value):
                        obs['facts']['control_title_stored'] = True
                    if field == 'index' and type(value) is int and value < 0:
                        obs['facts']['negative_index_stored'] = True
            if 'hex_color' in request and isinstance(request['hex_color'], str) and len(request['hex_color']) == 7 and not request['hex_color'].startswith('#'):
                stored = after[1]['response'].get('hex_color')
                obs['facts']['color_seventh_character_lost'] = stored == request['hex_color'][:6]
            if request.get('title') == '' and obs['entity'] == 'tasks' and obs['operation'] == 'update' and after[1]['response'].get('title'):
                obs['facts']['empty_task_title_ignored'] = True
            if 'background_blur_hash' in request and obs['operation'] == 'update' and after[1]['response'].get('background_blur_hash') != request['background_blur_hash']:
                obs['facts']['blur_hash_ignored_on_update'] = True
        # A no-op update reusing a just-read accepted cover id fails; a clearing update repairs it.
        if obs['entity'] == 'tasks' and obs['operation'] == 'update' and obs['status'] == 400 and isinstance(request, dict) and request.get('cover_image_attachment_id', 0) > 0:
            if before and before[0] == i-1 and same(before[1].get('response'), request) and isinstance(response, dict) and response.get('code') == 4020:
                creators = [(j,r) for j,r in enumerate(rows[:before[0]]) if r.get('method') == 'PUT' and successful(r.get('status')) and isinstance(r.get('response'),dict) and r['response'].get('id') == request.get('id') and re.fullmatch('/projects/[^/]+/tasks', r.get('path',''))]
                if creators and creators[-1][0] == i-2:
                    obs['facts']['accepted_cover_then_noop_rejected'] = True
                    obs['witnesses'].extend([{'accepted_create_record':i-2}, {'preimage_record':i-1}])
        password = request.get('password') if isinstance(request,dict) else None
        if obs['entity'] == 'shares' and obs['operation'] == 'create' and isinstance(password,str):
            marker = re.fullmatch(r'<(\d+) chars>', password)
            if marker:
                # A redacted character count is only a lower bound on UTF-8 bytes.
                obs['facts']['password_byte_lower_bound'] = int(marker[1])
                obs['limitations'].append('Password redacted; character count is a UTF-8 byte lower bound')
            else:
                obs['facts']['password_byte_lower_bound'] = len(password.encode('utf-8'))
            obs['facts']['share_password_context'] = True
        if obs['operation'] == 'delete' and obs['entity'] == 'shares' and successful(obs['status']):
            # Prior absence is required; a successful DELETE alone says nothing about existence.
            absent = next(((j,r) for j,r in reversed(list(enumerate(rows[:i]))) if r.get('path') == path), None)
            if absent and absent[1].get('method') == 'GET' and absent[1].get('status') == 404:
                obs['facts']['delete_absent_share_success'] = True
        if path == '/register' and isinstance(request,dict) and isinstance(password,str) and isinstance(response,dict):
            obs['facts']['password_echoed'] = password in json.dumps(response,ensure_ascii=False)
        observations.append(obs)
    return observations, []


def analyze_manifest(manifest, evidence_root):
    observations, native_oracles, runs = [], [], []
    for spec in manifest['runs']:
        path = evidence_root / spec['path']
        loaders = {'research-gateway-jsonl/1':load_gateway,'http-transcript/1':load_transcript,
                   'original-oracle-jsonl/1':load_original_oracles}
        if spec['format'] not in loaders:
            raise ValueError('Unsupported tool evidence gateway')
        data = loaders[spec['format']](path)
        if spec.get('sha256') and digest(path.read_bytes()) != spec['sha256']:
            raise ValueError('Input hash mismatch: '+str(path))
        run = dict(spec, source=data['source'], tool=data['tool'])
        if spec['format'] == 'original-oracle-jsonl/1':
            obs = []
            oracles = [dict(source=dict(run['source'],record=i),category=r.get('category'),payload=r,
                            verification='recorded_original_oracle; original HTTP trace unavailable')
                       for i,r in enumerate(data['records'])]
        elif spec['product'] == 'gitea':
            obs, oracles = gitea_observations(run, data)
        elif spec['product'] == 'vikunja':
            contract_path = evidence_root / spec['contract']
            if spec.get('contract_sha256') and digest(contract_path.read_bytes()) != spec['contract_sha256']:
                raise ValueError('Contract hash mismatch')
            contract = json.loads(contract_path.read_text(encoding='utf-8-sig'))
            obs, oracles = vikunja_observations(run,data,contract)
        else:
            raise ValueError('Unsupported product gateway')
        observations.extend(obs)
        native_oracles.extend(oracles)
        runs.append({'id':run['id'],'product':run['product'],'version':run['version'],'tool':run['tool'],
                     'source_sha256':digest(path.read_bytes()),
                     'http_records':len(obs) if spec['format'] != 'original-oracle-jsonl/1' else None,
                     'http_5xx':sum(type(o['status']) is int and 500 <= o['status'] < 600 for o in obs) if spec['format'] != 'original-oracle-jsonl/1' else None,
                     'original_oracle_records':len(oracles),'native_run_status':data.get('native',{}).get('status'),
                     'native_exit':data.get('native',{}).get('native_exit'),
                     'native_log_sha256':data.get('native_log_sha256')})
    report = classify(observations, ROOT/'catalogs')
    report['schema_version'] = 'natchan-tse-analysis/1'
    report['runs'] = runs
    report['original_oracles'] = native_oracles
    report['policy'].update({'original_oracles_separate':True,'new_sut_calls':False,
                            'missing_evidence_not_zero':True,'unique_root_causes_not_inferred_from_group_count':True})
    counts = Counter(row['catalog_id'] for row in report['assessments'] if row.get('kind') == 'known_bug')
    report['known_signature_occurrences'] = dict(sorted(counts.items()))
    report['original_oracle_summary'] = summarize_oracles(native_oracles)
    return report


def summarize_oracles(oracles):
    summary = {}
    for item in oracles:
        run_id = Path(item['source']['file']).parent.name + '/' + Path(item['source']['file']).stem
        group = summary.setdefault(run_id, {'categories': {}, 'atomicity_from_recorded_field_states': {},
                                          'atomicity_verdict_disagreements': 0})
        row = item['payload']
        category = item['category'] or 'unknown'
        category_counts = group['categories'].setdefault(category, {})
        verdict = str(row.get('verdict', 'not_recorded'))
        category_counts[verdict] = category_counts.get(verdict, 0) + 1
        if category == 'atomicity-check' and row.get('kind') == 'update' and row.get('fields'):
            states = set(row['fields'].values())
            computed = ('partial' if states == {'kept','applied'} else 'rolled_back' if states == {'kept'} else
                        'committed_despite_error' if states == {'applied'} else 'other')
            counts = group['atomicity_from_recorded_field_states']
            counts[computed] = counts.get(computed, 0) + 1
            group['atomicity_verdict_disagreements'] += computed != row.get('verdict')
    return summary


def markdown(report):
    lines = ['# Natchan retained TSE evidence analysis','','No new HTTP requests. Signature matches are not newly discovered unique bugs.', '',
             '| Run | Tool | HTTP records | HTTP 5xx | Native status |','|---|---|---:|---:|---|']
    for r in report['runs']:
        lines.append(f"| {r['id']} | {r['tool']} | {r['http_records']} | {r['http_5xx']} | {r['native_run_status'] or 'not a native tool run'} |")
    lines += ['','## Known evidence signatures','','| ID | Occurrences |','|---|---:|']
    lines.extend(f'| {k} | {v} |' for k,v in report['known_signature_occurrences'].items())
    lines += ['','Original gateway verdicts are retained separately. Hidden snapshots cannot be independently reconstructed.',
              'Vikunja direct reproducers are not attributed to Provengo. Missing full evidence is not a negative result.','']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--manifest',type=Path)
    inputs.add_argument('--input',type=Path,help='Existing natchan-observations/1 or Library natchan-analysis/1')
    parser.add_argument('--evidence-root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():
        parser.error('Output already exists')
    if args.manifest:
        if not args.evidence_root:
            parser.error('--evidence-root is required with --manifest')
        manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        if manifest.get('schema_version') != 'natchan-tse-manifest/1':
            parser.error('Unsupported manifest version')
        report = analyze_manifest(manifest,args.evidence_root)
        report['manifest_sha256'] = digest(args.manifest.read_bytes())
        text = markdown(report)
    else:
        document = json.loads(args.input.read_text(encoding='utf-8-sig'))
        if document.get('schema_version') == 'natchan-analysis/1':
            from library_adapter import observations_from_analysis
            observations = observations_from_analysis(document)
        elif document.get('schema_version') == 'natchan-observations/1':
            observations = document['observations']
        else:
            parser.error('An explicit tool/product gateway is required for this input')
        report = classify(observations,ROOT/'catalogs')
        report['input_sha256'] = digest(args.input.read_bytes())
        from classifier import markdown as classification_markdown
        text = classification_markdown(report)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    args.output.with_suffix('.md').write_text(text,encoding='utf-8')
    print('NATCHAN_V004_COMPLETE '+str(args.output.resolve()))


if __name__ == '__main__':
    main()
