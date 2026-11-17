"""E6: extended logic-mutant sweep for the single-event Library model.

Each of the logic mutations in sut_mutants_e6.py (bug-mapping chapters 2-3, one per process)
is run as its own arm behind the v006 observer, in two workloads:

  guided   the frozen 542-scenario catalog plus every v013 addition, rejection steps included,
           through the patched StrictGuidedRun (one fresh runtime per scenario)
  sampled  K unguided scenarios sampled once from the healthy model with `provengo sample`
           and replayed identically against every arm with `provengo run -s`

Two kill channels per arm, reported separately and never pooled into one score:
  native    the model's own expected-response-code checks (a Provengo run that fails, or a
            guided scenario whose native_pass is false) on a case that passed the healthy control
  observer  the first clean semantic verdict per case (STATE_MISMATCH, VALID_LOAN_REJECTED,
            EXISTING_BOOK_READ, READBACK_UNAVAILABLE) on a case with no control verdict

    .venv/bin/python library/ess-experiment/campaign-v013/mutant_sweep_e6.py \\
        --repo . --jar ~/provengo/Provengo-2026-01-10.uber.jar --modes guided,sampled --size 6

Outputs: results.json and E6_RESULTS.md in library/ess-experiment/runs/e6-mutants-<ts>-<pid>/.
"""
import argparse
import importlib.util
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for folder in ('campaign-v004', 'campaign-v006', 'campaign-v009', 'campaign-v011'):
    sys.path.insert(0, str(HERE.parent / folder))
sys.path.insert(0, str(HERE))
import pilot_v006 as runtime  # noqa: E402
core = runtime.core
from guided_suite_v013 import build_adapter, rows, reachability, transport_counts, default_sets  # noqa: E402
from prepare_model_v013 import prepare, sha, write  # noqa: E402
from sample_coverage_v013 import compact_file  # noqa: E402

OBSERVER = HERE.parent / 'campaign-v006/observed_server_v006.py'


def load_mutants():
    spec = importlib.util.spec_from_file_location('sut_mutants_e6', HERE / 'sut_mutants_e6.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.MUTANTS)


class ObserverService:
    """The v006 observer in front of the given SUT file, with ISSTA_BUGS set to `bugs`."""

    def __init__(self, sut, folder, bugs):
        self.sut, self.folder, self.bugs = sut, folder, bugs

    def __enter__(self):
        for port in (23243, 23244):
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    raise RuntimeError(f'Port {port} is occupied; no existing process will be stopped')
        self.output = open(self.folder / 'server.log', 'w', encoding='utf-8')
        self.token = secrets.token_hex(32)
        self.proc = subprocess.Popen([sys.executable, str(OBSERVER), '--sut', str(self.sut), '--bugs', self.bugs,
                                      '--log', str(self.folder / 'http.jsonl')],
                                     stdout=self.output, stderr=subprocess.STDOUT, env=dict(os.environ, ISSTA_SERVICE_TOKEN=self.token))
        try:
            for _ in range(100):
                if self.proc.poll() is not None:
                    raise RuntimeError('Observer failed to start: inspect server.log')
                try:
                    health = core.call('http://127.0.0.1:23243/__campaign__/health')
                    if health.get('service_token') != self.token:
                        raise RuntimeError('Unexpected listening process')
                    return self
                except OSError:
                    time.sleep(.1)
            raise RuntimeError('Observer startup timed out')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        try:
            try:
                core.call('http://127.0.0.1:23243/__campaign__/shutdown', {'token': self.token})
            except OSError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                self.proc.wait(timeout=10)
        finally:
            self.output.close()


def first_clean_verdicts(http):
    """case -> rule names of the first untainted verdict in that case."""
    verdicts = {}
    for r in http:
        if r['role'] != 'verdict' or r.get('prefix_tainted'):
            continue
        verdicts.setdefault(str(r['case']), sorted({v['rule'] for v in r['violations']}))
    return verdicts


def guided_arm(root, harness, selection, count, folder, bugs, sut, case_timeout, arm_timeout):
    folder.mkdir()
    with ObserverService(sut, folder, bugs):
        outcome = runtime.run(harness + [root / 'model', folder / 'native.jsonl', case_timeout] + selection, folder, 'java-suite', arm_timeout)
    native = rows(folder / 'native.jsonl')
    http = rows(folder / 'http.jsonl')
    if len(native) != count or outcome['exit_code']:
        raise RuntimeError('Incomplete guided arm ' + bugs + '; evidence preserved')
    if any(r['role'] == 'observer_error' for r in http):
        raise RuntimeError('Observer error in guided arm ' + bugs)
    return {'cases': [str(r['case']) for r in native],
            'native_failed': [str(r['case']) for r in native if not r['native_pass']],
            'verdicts': first_clean_verdicts(http), 'transport': transport_counts(http),
            'reachability': reachability(native)['counts'], 'wall_seconds': outcome['wall_seconds']}


def sampled_arm(root, java, jar, samples, size, folder, bugs, sut, case_timeout):
    folder.mkdir()
    exits = {}
    started = time.perf_counter()
    with ObserverService(sut, folder, bugs):
        for i in range(1, size + 1):
            core.call('http://127.0.0.1:23243/__campaign__/case', {'case': i})
            result = runtime.run([java, '-Xmx2g', '-jar', jar, 'run', '-s', samples, '--run-id', str(i), root / 'model'],
                                 folder, 'case-%03d' % i, case_timeout)
            exits[str(i)] = result['exit_code'] if not result['watchdog_timeout'] else 'timeout'
    http = rows(folder / 'http.jsonl')
    if any(r['role'] == 'observer_error' for r in http):
        raise RuntimeError('Observer error in sampled arm ' + bugs)
    return {'cases': sorted(exits, key=int), 'exit_codes': exits,
            'native_failed': [c for c, code in exits.items() if code != 0],
            'verdicts': first_clean_verdicts(http), 'transport': transport_counts(http),
            'wall_seconds': time.perf_counter() - started}


def kills(control, arm):
    eligible = [c for c in control['cases'] if c not in control['native_failed'] and c not in control['verdicts']]
    native = [c for c in arm['native_failed'] if c in eligible]
    observer = {c: rules for c, rules in arm['verdicts'].items() if c in eligible}
    return {'eligible_cases': len(eligible), 'native_kills': native, 'observer_kills': observer,
            'killed': bool(native or observer)}


def report(results, mutants):
    modes = [m for m in ('guided', 'sampled') if m in results]
    lines = ['# E6 logic-mutant sweep (v013 single-event model, contract profile)', '']
    for mode in modes:
        control = results[mode]['control']
        lines.append('%s control: %d cases, native failures %s, observer verdict cases %s, %.0f s' % (
            mode, len(control['cases']), control['native_failed'] or 'none', sorted(control['verdicts']) or 'none', control['wall_seconds']))
    lines += ['', '| Mutant | Ref | Mutation | Expected channel | ' + ' | '.join('%s native / observer' % m for m in modes) + ' | Verdict |',
              '| --- | --- | --- | --- | ' + ' | '.join('---' for _ in modes) + ' | --- |']
    killed = 0
    for mid, (ref, description, channel) in mutants.items():
        cells = []
        any_kill = False
        for mode in modes:
            arm = results[mode].get(mid)
            if not arm:
                cells.append('not run'); continue
            k = arm['kills']
            rules = sorted({r for rs in k['observer_kills'].values() for r in rs})
            cells.append('%d / %d%s' % (len(k['native_kills']), len(k['observer_kills']), (' (' + ', '.join(rules) + ')') if rules else ''))
            any_kill = any_kill or k['killed']
        killed += any_kill
        lines.append('| %s | %s | %s | %s | %s | %s |' % (mid, ref, description, channel, ' | '.join(cells), 'KILLED' if any_kill else 'SURVIVED'))
    lines += ['', '%d of %d mutants killed by at least one channel in at least one workload.' % (killed, len(mutants)),
              'Cells are counts of control-eligible cases: native = the model\'s own expected-code check failed; observer = first clean semantic verdict.']
    return '\n'.join(lines) + '\n'


def main(args):
    repo = args.repo.resolve()
    jar = args.jar.resolve()
    mutants = load_mutants()
    selected = list(mutants) if args.mutants == 'all' else [m.strip() for m in args.mutants.split(',')]
    unknown = [m for m in selected if m not in mutants]
    if unknown:
        raise RuntimeError('Unknown mutants: ' + ', '.join(unknown))
    root = (args.output_root or repo / 'library/ess-experiment/runs').resolve() / ('e6-mutants-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    root.mkdir(parents=True)
    modes = args.modes.split(',')
    results = {'mutants': {m: {'reference': mutants[m][0], 'description': mutants[m][1], 'expected_channel': mutants[m][2]} for m in selected}}
    timing = {}
    started = time.perf_counter()
    try:
        profile = prepare(repo, root, profile='contract', stories='full', users=args.users, books=args.books, max_length=args.max_length)
        sut = root / 'sut_mutants_e6.py'
        shutil.copy2(HERE / 'sut_mutants_e6.py', sut)
        write(root / 'environment.json', {'version': 'v013-E6', 'repo': str(repo), 'provengo_jar': str(jar), 'jar_sha256': sha(jar),
                                          'python': sys.version, 'model_profile': profile, 'modes': modes, 'mutants': selected,
                                          'sut': 'sut_mutants_e6.py behind the v006 observer', 'sample_size': args.size, 'max_length': args.max_length})
        if 'guided' in modes:
            sets = args.sets or default_sets('contract')
            harness, selection, count, timing['compilation_seconds'] = build_adapter(root, HERE.parent / 'src/StrictGuidedRun.java', jar, args.java, sets, None)
            results['guided'] = {'scenario_sets': sets, 'scenario_count': count}
            print('GUIDED control', flush=True)
            control = guided_arm(root, harness, selection, count, root / 'guided-control', 'none', sut, args.case_timeout, args.arm_timeout)
            results['guided']['control'] = control
            write(root / 'results.json', results)
            for m in selected:
                print('GUIDED ' + m, flush=True)
                arm = guided_arm(root, harness, selection, count, root / ('guided-' + m), m, sut, args.case_timeout, args.arm_timeout)
                arm['kills'] = kills(control, arm)
                results['guided'][m] = arm
                write(root / 'results.json', results)
                print('  killed=%s native=%s observer=%s' % (arm['kills']['killed'], arm['kills']['native_kills'], sorted(arm['kills']['observer_kills'])), flush=True)
            timing['guided_seconds'] = sum(a['wall_seconds'] for k, a in results['guided'].items() if isinstance(a, dict) and 'wall_seconds' in a)
        if 'sampled' in modes:
            sampling = root / 'sampling'; sampling.mkdir()
            samples = root / 'samples.json'
            outcome = runtime.run([args.java, '-Xmx2g', '-jar', jar, 'sample', '--overwrite', '--size', str(args.size), '--max-length', str(args.max_length),
                                   '-o', samples, root / 'model'], sampling, 'sample', args.sample_timeout)
            if outcome['exit_code'] or not samples.exists():
                raise RuntimeError('Sampling failed; inspect sampling/sample.log')
            compact = compact_file(samples)
            if len(compact) != args.size:
                raise RuntimeError('Sampled %d scenarios, expected %d' % (len(compact), args.size))
            write(root / 'samples-compact.json', compact)
            timing['sampling_seconds'] = outcome['wall_seconds']
            results['sampled'] = {'size': args.size, 'events_per_sample': [len(s) for s in compact]}
            print('SAMPLED control', flush=True)
            control = sampled_arm(root, args.java, jar, samples, args.size, root / 'sampled-control', 'none', sut, args.case_timeout)
            results['sampled']['control'] = control
            write(root / 'results.json', results)
            if len(control['native_failed']) == args.size:
                raise RuntimeError('Every sampled case failed on the healthy control; do not score')
            for m in selected:
                print('SAMPLED ' + m, flush=True)
                arm = sampled_arm(root, args.java, jar, samples, args.size, root / ('sampled-' + m), m, sut, args.case_timeout)
                arm['kills'] = kills(control, arm)
                results['sampled'][m] = arm
                write(root / 'results.json', results)
                print('  killed=%s native=%s observer=%s' % (arm['kills']['killed'], arm['kills']['native_kills'], sorted(arm['kills']['observer_kills'])), flush=True)
            timing['sampled_seconds'] = sum(a['wall_seconds'] for k, a in results['sampled'].items() if isinstance(a, dict) and 'wall_seconds' in a)
        (root / 'E6_RESULTS.md').write_text(report(results, {m: mutants[m] for m in selected}), encoding='utf-8')
        print((root / 'E6_RESULTS.md').read_text(encoding='utf-8'))
        write(root / 'completed.json', {'complete': True, 'modes': modes, 'mutants': selected})
        print('E6_COMPLETE', flush=True)
    finally:
        timing['total_seconds'] = time.perf_counter() - started
        write(root / 'timings.json', timing)
        archive = root.with_name(root.name + '-review.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob('*'):
                if p.is_file() and not {'products', '__pycache__', 'classes'}.intersection(p.relative_to(root).parts) and p.name != 'samples.json':
                    z.write(p, p.relative_to(root))
        print('E6_DIR ' + str(root), flush=True)
        print('E6_REVIEW_ZIP ' + str(archive), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--java', default='java')
    parser.add_argument('--modes', default='guided,sampled')
    parser.add_argument('--mutants', default='all', help='comma-separated mutant ids, or all')
    parser.add_argument('--sets', help='guided scenario sets (default: the contract profile default)')
    parser.add_argument('--users', type=int, default=5)
    parser.add_argument('--books', type=int, default=5)
    parser.add_argument('--size', type=int, default=6, help='sampled scenarios per arm')
    parser.add_argument('--max-length', type=int, default=200)
    parser.add_argument('--case-timeout', type=int, default=300)
    parser.add_argument('--arm-timeout', type=int, default=7200)
    parser.add_argument('--sample-timeout', type=int, default=900)
    parser.add_argument('--output-root', type=Path)
    main(parser.parse_args())
