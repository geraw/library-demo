"""Versioned preparation and measured campaigns. No tool binaries are downloaded."""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import socket
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
        proc = subprocess.run([str(x) for x in args], stdout=output, stderr=subprocess.STDOUT,
                              timeout=timeout, cwd=log.parent)
    return {'exit_code': proc.returncode, 'wall_seconds': time.perf_counter() - started,
            'command': [str(x) for x in args]}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Source changed; refusing an unreviewed model edit: ' + old[:80])
    return text.replace(old, new)


def prepare(repo, root):
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
    data = model / 'data/issta_endpoint.js'
    data.write_text('var host = "127.0.0.1";\nvar port = 23243;\n', encoding='utf-8')
    config = model / 'config/provengo.yml'
    with config.open('a', encoding='utf-8') as out:
        out.write('\n# ISSTA v001 workload bound, not a server-side business restriction.\nscenario.max-length: 500\n')
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
        self.proc = subprocess.Popen([sys.executable, str(HERE / 'observed_server_v001.py'),
            '--sut', str(self.root / 'sut_buggy_issta.py'), '--bugs', self.bugs,
            '--log', str(self.folder / 'http.jsonl')], stdout=self.output, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if self.proc.poll() is not None:
                    raise RuntimeError('Managed server failed: inspect server.log')
                try:
                    health = call('http://127.0.0.1:23243/__campaign__/health')
                    if health['pid'] != self.proc.pid:
                        raise RuntimeError('Unexpected listening process')
                    write(self.folder / 'server_identity.json', health)
                    return self
                except OSError:
                    time.sleep(.1)
            raise RuntimeError('Server startup timed out')
        except BaseException:
            self.__exit__(None, None, None)
            raise
    def __exit__(self, *_):
        self.proc.terminate()
        self.proc.wait(timeout=15)
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


def replay(java, jar, root, sample, size, name, bugs):
    folder = root / name
    folder.mkdir()
    outcomes = []
    started = time.perf_counter()
    with Service(root, folder, bugs):
        for i in range(1, size + 1):
            call('http://127.0.0.1:23243/__campaign__/case', {'case': i})
            print(f'{name}: test {i}/{size}', flush=True)
            result = command([java, '-jar', jar, 'run', '-s', sample, '--run-id', str(i),
                              root / 'model'], folder / f'test-{i:03d}.log', timeout=180)
            result['case'] = i
            outcomes.append(result)
    write(folder / 'runs.json', outcomes)
    summary = evaluate(folder)
    summary['wall_seconds'] = time.perf_counter() - started
    summary['native_nonzero_count'] = sum(x['exit_code'] != 0 for x in outcomes)
    write(folder / 'summary.json', summary)
    return summary


def provengo(args):
    root = args.repo / 'library/ess-experiment/runs' / ('issta-v001-' + time.strftime('%Y%m%d-%H%M%S'))
    root.mkdir(parents=True)
    model = prepare(args.repo, root)
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
    result = command([args.java, '-jar', args.jar, 'sample', '--overwrite', '--size', '1',
                      length, '100', '-o', smoke, model], root / 'smoke-sample.log', timeout=180)
    if result['exit_code']:
        raise RuntimeError('Smoke sampling failed')
    control = replay(args.java, args.jar, root, smoke, 1, 'smoke-control', 'none')
    if control['native_nonzero_count'] or control['semantic_candidates'] or not control['tool_http_requests']:
        raise RuntimeError('Smoke control failed. No official campaign started; inspect smoke-control')
    sample = root / 'samples.json'
    result = command([args.java, '-jar', args.jar, 'sample', '--overwrite', '--size', str(args.size),
                      length, '500', '-o', sample, model], root / 'sample.log', timeout=600)
    write(root / 'sampling.json', result)
    if result['exit_code'] or not sample.exists():
        raise RuntimeError('Official sampling failed')
    # Sample containers differ across releases. Require exact count rather than silently
    # treating an unrecognized format as a complete suite.
    data = json.loads(sample.read_text(encoding='utf-8-sig'))
    seqs = data if isinstance(data, list) else next((data[k] for k in ('scenarios', 'runs', 'samples') if isinstance(data.get(k), list)), None)
    if seqs is None or len(seqs) != args.size:
        raise RuntimeError('Unexpected sample container/count. Preserve samples.json and inspect before replay')
    write(root / 'sample_identity.json', {'sha256': sha(sample), 'actual_count': len(seqs)})
    base = replay(args.java, args.jar, root, sample, args.size, 'control', 'none')
    if base['native_nonzero_count'] or base['semantic_candidates'] or len(base['cases_with_http']) != args.size:
        raise RuntimeError('Control suite failed. Budget and mutation comparison withheld; inspect control')
    if not base['successful_dependent_creations']:
        raise RuntimeError('No successful dependent creation in control. Binding validation incomplete')
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
    p = subs.add_parser('provengo')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--size', type=int, choices=(100, 200), default=100)
    p.add_argument('--jar', type=Path, required=True)
    p.add_argument('--java', default='java')
    e = subs.add_parser('evomaster')
    e.add_argument('--campaign', type=Path, required=True)
    e.add_argument('--jar', type=Path, required=True)
    e.add_argument('--java', default='java')
    args = parser.parse_args()
    args.jar = args.jar.resolve()
    if args.mode == 'provengo':
        args.repo = args.repo.resolve()
        provengo(args)
    else:
        evomaster(args)
