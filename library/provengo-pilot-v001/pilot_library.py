"""Replay a single frozen Provengo sample set on eight isolated Library arms."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import parse_qsl, urlsplit

ARMS = ('original', 'baseline', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6')
ORIGINAL_SHA = 'b0fdf6c75517393664d7453211edf953178c2538fc5b9ec5a68da336b2c9ca8e'


def canonical(rows):
    """Bind server-generated identifiers to creation order per resource type."""
    ids = defaultdict(dict)
    result = []
    def ident(kind, value):
        if isinstance(value, bool) or not str(value).isdigit():
            return value
        bound = ids[kind].get(int(value))
        return bound if bound is not None else value

    def payload(value, entity):
        if isinstance(value, list):
            return [payload(item, entity) for item in value]
        if not isinstance(value, dict):
            return value
        kinds = {'id': entity, 'bookId': 'books', 'userId': 'users'}
        mapped = {key: ident(kinds[key], item) if key in kinds else item
                  for key, item in value.items()}
        error = mapped.get('error')
        if isinstance(error, str):
            def normalize_error(match):
                kind, number = match.groups()
                return kind + ' ' + str(ident(kind.lower() + 's', number))
            mapped['error'] = re.sub(r'\b(Book|User) (\d+)\b', normalize_error, error)
        return mapped

    for row in rows:
        url = urlsplit(row['url'])
        parts = url.path.strip('/').split('/')
        entity = parts[0]
        method, status = row['method'], row['status']
        body, response = row['input'], row['response']
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except ValueError:
                pass
        if method == 'POST' and status == 201 and isinstance(response, dict) and type(response.get('id')) is int:
            ids[entity].setdefault(response['id'], f'{entity}#{len(ids[entity]) + 1}')
        kinds = ['users', 'books'] if entity == 'loans' else [entity]
        path = [entity, *(ident(kinds[index], item) if index < len(kinds) else item
                          for index, item in enumerate(parts[1:]))]
        query = []
        for key, value in parse_qsl(url.query, keep_blank_values=True):
            kind = {'userId': 'users', 'bookId': 'books', 'q': entity}.get(key)
            query.append((key, ident(kind, value) if kind else value))
        request = [method, path, sorted(query), payload(body, entity)]
        result.append([request, status, payload(response, entity)])
    return result


def compare_controls(left, right):
    differences = []
    for case in sorted(left, key=int):
        if left[case]['status'] != right[case]['status'] or left[case]['trace'] != right[case]['trace']:
            differences.append(case)
    return differences



def relocate_sample(source, target, port):
    """Stream a transport-only URL replacement, keeping all event data otherwise intact."""
    old = b'"url":"http://127.0.0.1:23443/'
    new = f'"url":"http://127.0.0.1:{port}/'.encode()
    source_hash = hashlib.sha256()
    runtime_hash = hashlib.sha256()
    pending = b''
    replacements = 0
    with source.open('rb') as reader, target.open('xb') as writer:
        while True:
            chunk = reader.read(1024 * 1024)
            source_hash.update(chunk)
            pending += chunk
            if chunk:
                split = max(0, len(pending) - len(old) + 1)
                # Keep any token beginning before the boundary whole.
                start = pending.find(old, max(0, split - len(old) + 1))
                if start >= 0 and start + len(old) > split:
                    split = start
                ready, pending = pending[:split], pending[split:]
            else:
                ready, pending = pending, b''
            replacements += ready.count(old)
            relocated = ready.replace(old, new)
            writer.write(relocated)
            runtime_hash.update(relocated)
            if not chunk:
                break
    if replacements == 0:
        target.unlink()
        raise ValueError('No sampled endpoint found for port relocation')
    return source_hash.hexdigest(), runtime_hash.hexdigest(), replacements


def execute(args):
    sys.path.insert(0, str(args.benchmark))
    import campaign_v001 as bench
    from oracle_v001 import evaluate, read_trace
    from storage_v001 import discard_database

    selected_cases = sorted({int(value) for value in args.cases.split(',')}) if args.cases else None
    if selected_cases is not None and (not selected_cases or min(selected_cases) < 1):
        raise ValueError('Case numbers must be positive')
    if hashlib.sha256(args.original.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != ORIGINAL_SHA:
        raise ValueError('Original SUT SHA-256 differs from the frozen source. Use the original used to build these mutants.')
    cfg = bench.tool_config(args.config)
    root = args.output or args.benchmark / 'runs' / ('library-pilot-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    root.mkdir(parents=True, exist_ok=False)
    print('RUN_DIRECTORY', root, flush=True)
    write = bench.write
    frozen = root / 'frozen-sut'
    frozen.mkdir()
    original = Path(shutil.copy2(args.original, frozen / 'original.py'))
    mutants = Path(shutil.copy2(args.mutants, frozen / 'mutants.py'))
    write(root / 'pilot.json', {'arms': ('original', 'baseline') if args.controls_only else ARMS, 'sample_size': args.sample_size,
                               'max_length': args.max_length, 'seed': args.seed,
                               'sut_sha256': {p.name: bench.sha(p) for p in (original, mutants)},
                               'B6': 'BLOCKED_BY_SERIAL_GATEWAY'})
    summary = {}
    arms = ('original', 'baseline') if args.controls_only else ARMS
    try:
        model, _ = bench.prepare(root, cfg, args.port, args.seed)
        interfaces = model / 'spec/js/interfaces.library.js'
        content = interfaces.read_text(encoding='utf-8')
        if content.count('204') != 8:
            raise ValueError('Expected the v001 model with eight successful DELETE status references')
        interfaces.write_text(content.replace('204', '200'), encoding='utf-8')
        contract_path = root / 'openapi.json'
        contract = json.loads(contract_path.read_text(encoding='utf-8'))
        for item in contract['paths'].values():
            if 'delete' in item:
                responses = item['delete']['responses']
                responses.pop('204')
                responses['200'] = {'description': 'Deleted', 'content': {'application/json': {
                    'schema': {'type': 'object', 'required': ['message'], 'properties': {'message': {'type': 'string'}}}}}}
        write(contract_path, contract)
        meta = bench.preflight(root, cfg, ['provengo-sample10'])['provengo']
        sample_dir = root / 'samples'
        sample_dir.mkdir()
        samples = []
        java = cfg.get('java', 'java')
        java_command = [java, '-Xmx2g', '-jar', meta['jar']]
        if args.reuse_run:
            source = args.reuse_run
            prior = json.loads((source / 'native-tools.json').read_text(encoding='utf-8-sig'))
            if prior['provengo']['sha256'] != meta['sha256']:
                raise ValueError('The Provengo binary differs from the sampled binary')
            old_manifest = json.loads((source / 'samples/manifest.json').read_text(encoding='utf-8-sig'))
            if len({item['case'] for item in old_manifest}) != len(old_manifest):
                raise ValueError('Duplicate sample numbers in the manifest')
            if len(old_manifest) != args.sample_size:
                raise ValueError('The sample count differs from --sample-size')
            available = {item['case'] for item in old_manifest}
            if selected_cases is not None and not set(selected_cases).issubset(available):
                raise ValueError('Selected sample is missing')
            for item in old_manifest:
                if selected_cases is not None and item['case'] not in selected_cases:
                    continue
                file = source / 'samples' / f"sample-{item['case']:03d}.json"
                if bench.sha(file) != item['sha256']:
                    raise ValueError(f"Source sample changed: {file}")
                samples.append(dict(item, file=str(file)))
            for name in ('config', 'data', 'lib', 'spec'):
                shutil.rmtree(model / name)
                shutil.copytree(source / 'model' / name, model / name)
            endpoint = model / 'data/00_endpoint.js'
            endpoint.write_text(endpoint.read_text(encoding='utf-8').replace(
                'var port=23443;', f'var port={args.port};'), encoding='utf-8')
            old_contract = json.loads((source / 'openapi.json').read_text(encoding='utf-8-sig'))
            old_contract['servers'] = contract['servers']
            if old_contract != contract:
                raise ValueError('Contract differs beyond server address')
            source_pilot = json.loads((source / 'pilot.json').read_text())
            for file in (original, mutants):
                if bench.sha(file) != source_pilot['sut_sha256'][file.name]:
                    raise ValueError(f'Frozen SUT differs: {file.name}')
            write(root / 'reused-samples.json', samples)
        else:
            for case in range(1, args.sample_size + 1):
                name = f'sample-{case:03d}'
                file = sample_dir / (name + '.json')
                seed = args.seed + case - 1 if meta['seed_flag'] else None
                command = java_command + ['sample', '--overwrite', '--size', '1', meta['length_flag'],
                                          str(args.max_length), '-o', file, model]
                if seed is not None:
                    command += [meta['seed_flag'], str(seed)]
                print(f'SAMPLE {case}/{args.sample_size}', flush=True)
                bench.require(bench.launch(command, sample_dir, name, args.sample_timeout), sample_dir, name)
                data = json.loads(file.read_text(encoding='utf-8-sig'))
                scenarios = data if isinstance(data, list) else next(
                    (data[key] for key in ('scenarios', 'runs', 'samples') if isinstance(data.get(key), list)), [])
                if len(scenarios) != 1:
                    raise ValueError(f'{name} must contain exactly one scenario')
                samples.append({'case': case, 'file': str(file), 'sha256': bench.sha(file), 'seed': seed})
                write(sample_dir / 'manifest.json', samples)
        if selected_cases is not None and not args.reuse_run:
            raise ValueError('--cases requires --reuse-run')

        class Service:
            def __init__(self,folder,contract,port,sut,env):
                self.folder,self.contract,self.port,self.sut,self.env=folder,contract,port,sut,env
            def __enter__(self):
                with socket.socket() as sock:
                    if sock.connect_ex(('127.0.0.1',self.port))==0:raise RuntimeError('Port '+str(self.port)+' is occupied; no existing server was stopped')
                self.token=secrets.token_hex(32);self.base='http://127.0.0.1:'+str(self.port)
                server_env=dict(self.env,BENCH_SERVICE_TOKEN=self.token)
                self.log=(self.folder/'server.log').open('w',encoding='utf-8')
                self.proc=subprocess.Popen([sys.executable,str(args.benchmark/'server_v001.py'),'--sut',str(self.sut),'--trace',str(self.folder/'http.jsonl'),'--contract',str(self.contract),'--port',str(self.port)],env=server_env,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
                try:
                    for _ in range(150):
                        if self.proc.poll() is not None:raise RuntimeError('Managed server failed; inspect server.log')
                        try:
                            info=bench.call(self.base+'/__bench__/health')
                            if info.get('token')!=self.token:raise RuntimeError('Listener identity mismatch')
                            return self
                        except OSError:time.sleep(.1)
                    raise RuntimeError('Managed server did not become ready')
                except BaseException:self.__exit__(None,None,None);raise
            def boundary(self,case):return bench.call(self.base+'/__bench__/case',self.token,{'case':str(case)})
            def __exit__(self,*_):bench.terminate(self.proc);self.log.close()

        control = {}
        baseline = {}
        for arm in arms:
            folder = root / arm
            folder.mkdir()
            print(f'START {arm}', flush=True)
            env = dict(os.environ, LIBRARY_MUTANT='baseline' if arm == 'original' else arm)
            outcomes = []
            with Service(folder, contract_path, args.port, original if arm == 'original' else mutants, env) as service:
                for sample in samples:
                    case = sample['case']
                    if bench.sha(sample['file']) != sample['sha256']:
                        raise ValueError(f'Frozen sample changed: {case}')
                    runtime_file = Path(sample['file'])
                    if args.port != 23443:
                        runtime_file = sample_dir / f'replay-{case:03d}.json'
                        source_hash, runtime_hash, replacements = relocate_sample(
                            Path(sample['file']), runtime_file, args.port)
                        if source_hash != sample['sha256']:
                            raise ValueError('Source sample changed during transport relocation')
                        write(folder / f'case-{case:02d}-transport.json', {
                            'source_sha256': source_hash, 'runtime_sha256': runtime_hash,
                            'url_replacements': replacements, 'port': args.port})
                    service.boundary(case)
                    name = 'case-' + str(case).zfill(2)
                    outcomes.append(bench.launch(java_command + ['run', '-s', runtime_file, '--run-id', '1', model],
                                                 folder, name, args.case_timeout, env, expected=(0, 1)))
                    write(folder / 'case-progress.json', outcomes)
                    discard_database(model, folder, case)
                    if runtime_file != Path(sample['file']):
                        runtime_file.unlink()
                    if not outcomes[-1]['expected_exit']:
                        raise RuntimeError(f'{arm} case {case} did not complete; stopping this worker immediately')
            rows = read_trace(folder / 'http.jsonl')
            by_case = defaultdict(list)
            for row in rows:
                if row['role'] == 'tool':
                    by_case[row['case_id']].append(row)
            cases = {}
            for sample, outcome in zip(samples, outcomes):
                case = sample["case"]
                key = str(case)
                case_rows = by_case[key]
                trace = canonical(case_rows)
                status = ('INCOMPLETE' if not outcome['expected_exit'] or not case_rows
                          else 'PASS' if outcome['exit_code'] == 0 else 'NATIVE_FAIL')
                cases[key] = {'status': status, 'http_requests': len(case_rows), 'trace': trace}
            if arm in ('original', 'baseline') and any(value['status'] != 'PASS' for value in cases.values()):
                write(folder / 'control-failure.json', {key: value['status'] for key, value in cases.items()})
                raise RuntimeError(f'{arm} has a native failure; inspect its log before scoring mutants')
            oracle_rows = [dict(row, status=204) if row.get('method') == 'DELETE' and row['status'] == 200
                           else row for row in rows]
            oracle = evaluate(oracle_rows)
            write(folder / 'oracle.json', oracle)
            if arm == 'original':
                control = cases
            if arm == 'baseline':
                baseline = cases
                differences = compare_controls(control, baseline)
                incomplete = [key for key in baseline if 'INCOMPLETE' in (control[key]['status'], baseline[key]['status'])]
                write(root / 'controls.json', {'different_cases': differences, 'incomplete_cases': incomplete,
                                               'native_failed_cases': [key for key in baseline if baseline[key]['status'] != 'PASS']})
                if any(value['status'] != 'PASS' for value in baseline.values()):
                    raise RuntimeError('A control has a native failure; inspect its log before scoring mutants')
            if arm == 'B3':
                witnesses = []
                for key, result in cases.items():
                    if baseline[key]['status'] != 'PASS' or result['status'] == 'INCOMPLETE':
                        continue
                    for index, (left, right) in enumerate(zip(baseline[key]['trace'], result['trace']), 1):
                        if left == right:
                            continue
                        if left[0] == right[0] and left[0][:2] == ['POST', ['loans']] and (left[1], right[1]) == (201, 400):
                            witnesses.append({'case': key, 'request_index': index, 'baseline_status': 201, 'mutant_status': 400})
                        break
                write(folder / 'B3-paired-witnesses.json', witnesses)
            summary[arm] = {'http_requests': oracle['http_requests'],
                            'cases': {key: {k: v for k, v in value.items() if k != 'trace'} for key, value in cases.items()},
                            'passive_bug_ids': oracle['confirmed_bug_ids'],
                            'http_5xx': len(oracle['server_errors']),
                            'native_failures_on_passing_baseline': [
                                key for key, value in cases.items() if value['status'] == 'NATIVE_FAIL'
                                and baseline.get(key, {}).get('status') == 'PASS'],
                            'B6': 'BLOCKED_BY_SERIAL_GATEWAY' if arm == 'B6' else None}
            write(root / 'summary.json', summary)
            if arm == 'baseline' and (differences or incomplete):
                raise RuntimeError('Control equivalence gate failed. Inspect controls.json before scoring mutants.')
        incomplete_arms = [arm for arm, report in summary.items()
                           if any(case['status'] == 'INCOMPLETE' for case in report['cases'].values())]
        if incomplete_arms:
            raise RuntimeError('Incomplete replay cases in: ' + ', '.join(incomplete_arms))
        write(root / 'completed.json', {'replays': len(arms) * len(samples), 'B6': 'BLOCKED_BY_SERIAL_GATEWAY'})
    except Exception as exc:
        write(root / 'failure.json', {'error': str(exc)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('benchmark', 'original', 'mutants', 'config', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=name != 'output')
    for name, default in [('sample-size', 100), ('max-length', 2000), ('seed', 1), ('port', 23443),
                          ('sample-timeout', 300), ('case-timeout', 7200)]:
        parser.add_argument('--' + name, type=int, default=default)
    parser.add_argument('--reuse-run', type=lambda value: Path(value).resolve())
    parser.add_argument('--cases')
    parser.add_argument('--controls-only', action='store_true')
    args = parser.parse_args()
    if min(args.sample_size, args.max_length, args.sample_timeout, args.case_timeout) < 1 or not 1024 <= args.port <= 65535:
        parser.error('Invalid campaign parameters')
    execute(args)

