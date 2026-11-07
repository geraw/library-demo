"""Versioned preparation and measured campaigns. No tool binaries are downloaded."""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import socket
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=20) as reply:
        return json.load(reply)


def command(args, log, timeout=None):
    started = time.perf_counter()
    with open(log, 'w', encoding='utf-8') as output:
        output.write('COMMAND ' + json.dumps([str(x) for x in args]) + '\n')
        output.flush()
        try:
            proc = subprocess.run([str(x) for x in args], stdout=output, stderr=subprocess.STDOUT,
                                  timeout=timeout, cwd=log.parent)
            code, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired:
            output.write('\nHARNESS_TIMEOUT: execution incomplete\n')
            code, timed_out = 124, True
    return {'exit_code': code, 'timed_out': timed_out, 'wall_seconds': time.perf_counter() - started,
            'command': [str(x) for x in args]}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Source changed; refusing an unreviewed model edit: ' + old[:80])
    return text.replace(old, new)


def prepare(repo, root, profile="business"):
    model = root / 'model'
    shutil.copytree(repo / 'library/provengo', model,
                    ignore=shutil.ignore_patterns('products', '.git', '.github', '.vscode'))
    story_path = model / 'spec/js/lib_stories.js'
    text = story_path.read_text(encoding='utf-8')
    for name in ('USERS', 'BOOKS'):
        import re
        text, count = re.subn(r'const NUMBER_OF_' + name + r' = \d+;',
                              'const NUMBER_OF_' + name + ' = 5;', text)
        if count != 1:
            raise RuntimeError('Missing entity count: ' + name)
    # Make descriptive data stable; unique identity remains the logical numeric ID.
    text = text.replace('return "User name " + randomInt();', 'return "User name";')
    text = text.replace('return "Book title " + randomInt();', 'return "Book title";')
    story_path.write_text(text, encoding='utf-8')
    dal_path = model / 'spec/js/dal.js'
    dal = dal_path.read_text(encoding='utf-8')
    dal = 'var isstaPairLoans = {};\nvar isstaPairHolds = {};\n' + dal
    dal = replace_once(dal, 'function createLoanEntity(data) {',
        'function createLoanEntity(data) {\n' +
        '  var pairKey = data.userId + ":" + data.bookId;\n' +
        '  isstaPairLoans[pairKey] = (isstaPairLoans[pairKey] || 0) + 1;')
    dal = replace_once(dal, 'function createHoldEntity(data) {',
        'function createHoldEntity(data) {\n' +
        '  var pairKey = data.userId + ":" + data.bookId;\n' +
        '  isstaPairHolds[pairKey] = (isstaPairHolds[pairKey] || 0) + 1;')
    dal = replace_once(dal,
        "return e.type === 'user-book' && !hasLoanForUser(e.userid) && !hasLoanForBook(e.bookid);",
        "return e.type === 'user-book' && !hasLoanForBook(e.bookid) && " +
        "ctx.runQuery('Loan.All').length < 5 && (isstaPairLoans[e.userid + ':' + e.bookid] || 0) < 3;")
    dal = replace_once(dal,
        "return e.type === 'user-book' && (hasLoanForUser(e.userid) || hasLoanForBook(e.bookid));",
        "return e.type === 'user-book' && hasLoanForBook(e.bookid);")
    dal = replace_once(dal,
        "ctx.registerQuery('UserBook.CanCreateHold', function (e) {\n\treturn e.type === 'user-book';\n});",
        "ctx.registerQuery('UserBook.CanCreateHold', function (e) {\n\treturn e.type === 'user-book' && ctx.runQuery('Hold.All').length < 5 && (isstaPairHolds[e.userid + ':' + e.bookid] || 0) < 3;\n});")
    dal_path.write_text(dal, encoding='utf-8')
    if profile == 'business':
        story_path.write_text((HERE / 'business_stories_v004.js').read_text(), encoding='utf-8')
        interface = model / 'spec/js/interfaces.library.js'
        content = interface.read_text(encoding='utf-8')
        content = replace_once(content,
            'function requestOneOfDirect(method, url, variants) {',
            'function requestOneOfDirect(method, url, variants) {\n' +
            '  variants = (variants || []).filter(function(v) {\n' +
            '    return v.valid === true && v.expectedResponseCodes.every(function(c) {return c >= 200 && c < 300;});\n' +
            '  });')
        interface.write_text(content, encoding='utf-8')
    elif profile == 'investigator':
        for file in (model / 'spec/js').glob('*.js'):
            file.unlink()
        shutil.copy2(HERE / 'investigator_stories_v004.js', model / 'spec/js/investigator.js')
        shutil.rmtree(model / 'lib')
        (model / 'lib').mkdir()
    else:
        raise ValueError('Unknown profile')
    write(root / 'model_profile.json', {'profile': profile, 'version': 'v004',
          'isolation': 'reset + empty public lists + fresh JVM per case'})
    data = model / 'data/issta_endpoint.js'
    data.write_text('var host = "127.0.0.1";\nvar port = 23243;\n', encoding='utf-8')
    config = model / 'config/provengo.yml'
    with config.open('a', encoding='utf-8') as out:
        out.write('\n# ISSTA v004 workload bound, not a server-side business restriction.\nscenario.max-length: 500\n')
    shutil.copy2(repo / 'library/sut/sut_buggy_issta.py', root / 'sut_buggy_issta.py')
    contract = json.loads((repo / 'library/sut/library_openapi_issta.json').read_text(encoding='utf-8'))
    contract['servers'] = [{'url': 'http://127.0.0.1:23243'}]
    write(root / 'openapi.json', contract)
    files = [p for p in root.rglob('*') if p.is_file()]
    write(root / 'input_hashes.json', {str(p.relative_to(root)): sha(p) for p in files})
    return model


class Service:
    def __init__(self, root, folder, bugs):
        self.root, self.folder, self.bugs = root, folder, bugs
    def __enter__(self):
        for port in (23243, 23244):
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    raise RuntimeError(f'Port {port} is occupied; no existing process will be stopped')
        self.output = open(self.folder / 'server.log', 'w', encoding='utf-8')
        self.token = secrets.token_hex(32)
        environment = dict(os.environ, ISSTA_SERVICE_TOKEN=self.token)
        self.proc = subprocess.Popen([sys.executable, str(HERE / 'observed_server_v004.py'),
            '--sut', str(self.root / 'sut_buggy_issta.py'), '--bugs', self.bugs,
            '--log', str(self.folder / 'http.jsonl')], stdout=self.output, stderr=subprocess.STDOUT,
            env=environment)
        try:
            for _ in range(100):
                if self.proc.poll() is not None:
                    raise RuntimeError('Managed server failed: inspect server.log')
                try:
                    health = call('http://127.0.0.1:23243/__campaign__/health')
                    # Windows venv python.exe can be a redirector process: the HTTP
                    # worker's PID is not necessarily Popen.pid. Authenticate ownership.
                    if health.get('service_token') != self.token:
                        raise RuntimeError('Unexpected listening process')
                    health.pop('service_token', None)
                    health['launcher_pid'] = self.proc.pid
                    write(self.folder / 'server_identity.json', health)
                    return self
                except OSError:
                    time.sleep(.1)
            raise RuntimeError('Server startup timed out')
        except BaseException:
            self.__exit__(None, None, None)
            raise
    def __exit__(self, *_):
        try:
            try:
                call('http://127.0.0.1:23243/__campaign__/shutdown', {'token': self.token})
            except OSError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self.proc.terminate()
                self.proc.wait(timeout=10)
        finally:
            self.output.close()


def evaluate(folder):
    records = [json.loads(line) for line in (folder / 'http.jsonl').read_text().splitlines()]
    verdicts = [x for x in records if x['role'] == 'verdict']
    tool = [x for x in records if x['role'] == 'tool']
    summary = {'tool_http_requests': len(tool),
               'successful_creations': sum(x['method'] == 'POST' and x['status'] == 201 for x in tool),
               'successful_dependent_creations': sum(x['method'] == 'POST' and x['status'] == 201 and
                    x['path'].split('?')[0] in ('/loans', '/holds') for x in tool),
               'cases_with_http': sorted(set(str(x['case']) for x in tool)),
               'semantic_candidates': verdicts,
               'detection_status': 'CANDIDATES_REQUIRE_CONTROL_REPLAY' if verdicts else 'NO_CONFIRMED_FINDING',
               'official_sequence_local_score': 'NOT_YET_SCORED'}
    write(folder / 'evaluation.json', summary)
    return summary


def readable_case(logfile, case, output):
    lines = ["# Executed HTTP actions — case " + str(case), "",
             "| Step | Method | Path | Request | Actual status |", "| ---: | --- | --- | --- | ---: |"]
    index = 0
    with logfile.open(encoding='utf-8') as stream:
        for raw in stream:
            item = json.loads(raw)
            if item.get('case') != case or item.get('role') != 'tool':
                continue
            index += 1
            body = json.dumps(item.get('request'), ensure_ascii=True).replace('|', '\\|')
            path = item['path'].split('?')[0].replace('|', '\\|')
            lines.append(f"| {index} | {item['method']} | {path} | {body} | {item['status']} |")
    output.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def replay(java, jar, root, sample, size, name, bugs):
    folder = root / name
    folder.mkdir()
    outcomes = []
    started = time.perf_counter()
    with Service(root, folder, bugs):
        for i in range(1, size + 1):
            source, source_id = sample[i - 1] if isinstance(sample, list) else (sample, i)
            call('http://127.0.0.1:23243/__campaign__/case', {'case': i})
            print(f'{name}: test {i}/{size}', flush=True)
            result = command([java, '-Xmx2g', '-jar', jar, 'run', '-s', source, '--run-id', str(source_id),
                              root / 'model'], folder / f'test-{i:03d}.log', timeout=300)
            result['case'] = i
            result['source_file'] = str(source)
            result['source_run_id'] = source_id
            outcomes.append(result)
            write(folder / 'runs.json', outcomes)
            readable_case(folder / 'http.jsonl', i, folder / f'test-{i:03d}-readable.md')
            if result.get('timed_out'):
                raise RuntimeError(f'Case {i} timed out; earlier outcomes and HTTP actions are preserved')
    write(folder / 'runs.json', outcomes)
    summary = evaluate(folder)
    summary['wall_seconds'] = time.perf_counter() - started
    summary['native_nonzero_count'] = sum(x['exit_code'] != 0 for x in outcomes)
    write(folder / 'summary.json', summary)
    return summary


def batched_sample(java, jar, root, model, size, length, batch_size):
    """Keep native files intact. Global cases refer to file plus 1-based local ID."""
    folder = root / 'sample-batches'
    folder.mkdir()
    selected, seen, batches, manifest = [], set(), [], []
    elapsed = 0.0
    for batch_number in range(1, size * 2 + 1):
        count = min(batch_size, size - len(selected))
        sample_file = folder / f'batch-{batch_number:03d}.json'
        print(f'Sampling batch {batch_number}: {len(selected)}/{size} retained cases', flush=True)
        outcome = command([java, '-Xmx2g', '-jar', jar, 'sample', '--overwrite',
                           '--size', str(count), length, '500', '-o', sample_file, model],
                          folder / f'batch-{batch_number:03d}.log', timeout=240)
        elapsed += outcome['wall_seconds']
        batches.append(outcome)
        status = {'wall_seconds': elapsed, 'batches': batches,
                  'retained_count': len(selected), 'batch_size': batch_size,
                  'heap_argument': '-Xmx2g', 'complete': False}
        write(root / 'sampling.json', status)
        if outcome['exit_code'] or not sample_file.exists():
            raise RuntimeError(f'Sampling batch {batch_number} failed; inspect sample-batches logs')
        data = json.loads(sample_file.read_text(encoding='utf-8-sig'))
        seqs = data if isinstance(data, list) else next((data[k] for k in ('scenarios', 'runs', 'samples')
                    if isinstance(data, dict) and isinstance(data.get(k), list)), None)
        if seqs is None or len(seqs) != count:
            raise RuntimeError('Unrecognized batch container/count; native file retained for inspection')
        for local_id, scenario in enumerate(seqs, 1):
            signature = hashlib.sha256(json.dumps(scenario, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
            if signature in seen:
                continue
            seen.add(signature)
            selected.append((sample_file, local_id))
            manifest.append({'case': len(selected), 'source_file': str(sample_file.relative_to(root)),
                             'source_sha256': sha(sample_file), 'source_run_id': local_id,
                             'serialized_scenario_sha256': signature})
        write(root / 'sample_manifest.json', manifest)
        status['retained_count'] = len(selected)
        status['complete'] = len(selected) == size
        write(root / 'sampling.json', status)
        if status['complete']:
            return selected, {'wall_seconds': elapsed, 'batches': batches, 'exit_code': 0}
    raise RuntimeError('Insufficient distinct serialized scenarios; no replay or budget published')


def provengo(args):
    root = args.repo / 'library/ess-experiment/runs' / ('issta-' + args.profile + '-v004-' + time.strftime('%Y%m%d-%H%M%S'))
    root.mkdir(parents=True)
    model = prepare(args.repo, root, args.profile)
    write(root / 'environment.json', {'python': sys.version, 'executable': sys.executable,
          'provengo_jar': str(args.jar), 'jar_sha256': sha(args.jar), 'size_requested': args.size,
          'git_head': subprocess.check_output(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'], text=True).strip()})
    for sub in ('sample', 'run'):
        command([args.java, '-jar', args.jar, sub, '-h'], root / (sub + '-help.log'))
    help_text = (root / 'sample-help.log').read_text()
    length = '--max-length' if '--max-length' in help_text else '--max-depth' if '--max-depth' in help_text else None
    if not length:
        raise RuntimeError('No recognized sample length option; inspect sample-help.log')
    # Smoke is setup, explicitly excluded from the official budget.
    smoke = root / 'smoke.json'
    result = command([args.java, '-Xmx2g', '-jar', args.jar, 'sample', '--overwrite', '--size', '1',
                      length, '100', '-o', smoke, model], root / 'smoke-sample.log', timeout=180)
    if result['exit_code']:
        raise RuntimeError('Smoke sampling failed')
    control = replay(args.java, args.jar, root, smoke, 1, 'smoke-control', 'none')
    if control['native_nonzero_count'] or control['semantic_candidates'] or not control['tool_http_requests']:
        raise RuntimeError('Smoke control failed. No official campaign started; inspect smoke-control')
    sample, result = batched_sample(args.java, args.jar, root, model, args.size, length, args.batch_size)
    base = replay(args.java, args.jar, root, sample, args.size, 'control', 'none')
    if base['native_nonzero_count'] or base['semantic_candidates'] or len(base['cases_with_http']) != args.size:
        raise RuntimeError('Control suite failed. Budget and mutation comparison withheld; inspect control')
    if args.profile == 'business' and not base['successful_dependent_creations']:
        raise RuntimeError('No successful dependent creation in control. Binding validation incomplete')
    if not args.include_mutant:
        write(root / 'pilot_summary.json', {'profile': args.profile, 'sample_size': args.size,
              'control': base, 'sampling_seconds': result['wall_seconds'],
              'status': 'CONTROL_PILOT_COMPLETE', 'mutant_run': False,
              'comparison_budget_published': False})
        archive = shutil.make_archive(str(root) + '-review', 'zip', root)
        print('CONTROL_PILOT_COMPLETE ' + str(root), flush=True)
        print('REVIEW_ZIP ' + archive, flush=True)
        return
    mutant = replay(args.java, args.jar, root, sample, args.size, 'mutant-all', '1,2,3,4,5')
    if len(mutant['cases_with_http']) != args.size:
        raise RuntimeError('Incomplete HTTP execution: no comparison budget published')
    # Budget uses generation + one mutant-suite execution; control/verification is separate.
    budget = result['wall_seconds'] + mutant['wall_seconds']
    write(root / 'budget.json', {'sampling_seconds': result['wall_seconds'],
          'mutant_execution_seconds': mutant['wall_seconds'], 'control_seconds': base['wall_seconds'],
          'baseline_search_budget_seconds': math.ceil(budget),
          'includes_per_case_JVM_startup_and_oracle_overhead': True,
          'excludes_smoke_control_preparation_and_ground_truth_checks': True})
    archive = shutil.make_archive(str(root) + '-review', 'zip', root)
    print('CAMPAIGN_READY_FOR_REVIEW ' + str(root), flush=True)
    print('REVIEW_ZIP ' + archive, flush=True)


def evomaster(args):
    root = args.campaign.resolve()
    budget = json.loads((root / 'budget.json').read_text())['baseline_search_budget_seconds']
    folder = root / ('evomaster-' + time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    command([args.java, '-jar', args.jar, '--help'], folder / 'help.log', timeout=60)
    help_text = (folder / 'help.log').read_text()
    # Version adaptation is based on the installed binary, not assumed defaults.
    schema_option = '--schema' if re.search(r'--schema\b', help_text) else '--bbSwaggerUrl' if '--bbSwaggerUrl' in help_text else None
    base_option = '--base' if re.search(r'--base\b', help_text) else '--bbTargetUrl' if '--bbTargetUrl' in help_text else None
    if not schema_option or not base_option or '--maxTime' not in help_text:
        raise RuntimeError('Unsupported EvoMaster options. Inspect help.log; no search was started')
    invocation = [args.java, '-jar', args.jar, '--blackBox', 'true', schema_option, root / 'openapi.json',
                  base_option, 'http://127.0.0.1:23243', '--maxTime', str(budget) + 's',
                  '--seed', '1', '--outputFolder', folder / 'generated-tests']
    if '--outputFormat' in help_text and 'PYTHON_UNITTEST' in help_text:
        invocation += ['--outputFormat', 'PYTHON_UNITTEST']
    write(folder / 'provenance.json', {'jar_sha256': sha(args.jar), 'budget_seconds': budget,
          'contract_sha256': sha(root / 'openapi.json'), 'official_score': 'UNDETERMINED',
          'reason': 'Native search is campaign-global until generated tests are replayed with individual resets'})
    with Service(root, folder, '1,2,3,4,5'):
        call('http://127.0.0.1:23243/__campaign__/case', {'case': 'campaign-global-diagnostic'})
        result = command(invocation, folder / 'search.log', timeout=budget + 300)
    write(folder / 'execution.json', result)
    evaluate(folder)
    print('EVOMASTER_SEARCH_COMPLETE_REPLAY_REQUIRED ' + str(folder))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='mode', required=True)
    build = subs.add_parser('prepare')
    build.add_argument('--repo', type=Path, required=True)
    p = subs.add_parser('provengo')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--batch-size', type=int, choices=range(1, 6), default=5)
    p.add_argument('--size', type=int, choices=(10, 100, 200), default=10)
    p.add_argument('--profile', choices=('business', 'investigator'), default='business')
    p.add_argument('--include-mutant', action='store_true')
    p.add_argument('--jar', type=Path, required=True)
    p.add_argument('--java', default='java')
    e = subs.add_parser('evomaster')
    e.add_argument('--campaign', type=Path, required=True)
    e.add_argument('--jar', type=Path, required=True)
    e.add_argument('--java', default='java')
    args = parser.parse_args()
    if args.mode == 'prepare':
        destination = args.repo.resolve() / 'library/ess-experiment' / ('prepared-models-v004-' + time.strftime('%Y%m%d-%H%M%S'))
        for profile in ('business', 'investigator'):
            folder = destination / profile
            folder.mkdir(parents=True)
            prepare(args.repo.resolve(), folder, profile)
            print('PREPARED_' + profile.upper() + ' ' + str(folder / 'model'))
        sys.exit(0)
    args.jar = args.jar.resolve()
    if args.mode == 'provengo':
        args.repo = args.repo.resolve()
        provengo(args)
    else:
        evomaster(args)
