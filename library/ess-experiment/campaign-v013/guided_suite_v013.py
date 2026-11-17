"""v013: guided reachability suite for the single-event Library model.

Runs the frozen 542-scenario catalog plus the v013 additions (read steps and ISSTA triggers)
through the patched StrictGuidedRun against the experiment fixture, one fresh runtime per
scenario, behind the v006 observer. Works on Linux and Windows: no PowerShell is involved.

    .venv/bin/python library/ess-experiment/campaign-v013/guided_suite_v013.py \\
        --repo . --jar ~/provengo/Provengo-2026-01-10.uber.jar \\
        --profile contract --stories full --arms none,1,2,3,4,5

Arms are ISSTA_BUGS values ("none" = healthy control, "1-2-3-5" = several bugs at once).
Outputs land in library/ess-experiment/runs/guided-v013-<timestamp>-<pid>/ with a review ZIP.

Reachability (control arm) is the model-coverage measurement: a scenario that is expected to
be reachable and comes out STUCK is a model gap; one expected to be blocked that is REACHED is
a model bug. Native failures on mutant arms are detection evidence only for cases that passed
the healthy control; observer candidates (first clean verdict per case) are reported separately,
as in v009/v011. Nothing here assigns a final per-bug score.
"""
import argparse
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for folder in ('campaign-v004', 'campaign-v006', 'campaign-v009', 'campaign-v011'):
    sys.path.insert(0, str(HERE.parent / folder))
import pilot_v006 as runtime  # noqa: E402  (observer Service and subprocess runner)
from resample_split_v009 import counts  # noqa: E402  (first-clean observer candidates per case)
from patch_runtime_v013 import patch, SOURCE_SHA  # noqa: E402
from prepare_model_v013 import prepare, sha, write  # noqa: E402

JAVA_SOURCES = ['V013Match.java', 'V013Scenarios.java', 'V013GuidedSuiteHarness.java']


class PlainSut:
    """The repository's original library/sut/sut.py on localhost:23242, no observer.

    Used with --sut original: the original rules (one active loan per reader) are what the
    repository model encodes, so the "original" profile is measured against this server and
    the case boundary is the SUT's own POST /reset. No HTTP ledger or semantic verdicts exist in
    this mode; it measures reachability and the model's own response-code checks only.
    """

    def __init__(self, root, folder):
        self.root, self.folder = root, folder

    def __enter__(self):
        import socket, subprocess, urllib.request
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', 23242)) == 0:
                raise RuntimeError('Port 23242 is occupied; no existing process will be stopped')
        self.output = open(self.folder / 'server.log', 'w', encoding='utf-8')
        self.proc = subprocess.Popen([sys.executable, str(self.root / 'sut.py')], stdout=self.output, stderr=subprocess.STDOUT,
                                     env=dict(os.environ, FLASK_DEBUG='0'))
        for _ in range(100):
            if self.proc.poll() is not None:
                raise RuntimeError('Original SUT failed to start: inspect server.log')
            try:
                with urllib.request.urlopen('http://127.0.0.1:23242/books', timeout=2) as reply:
                    if reply.status == 200:
                        return self
            except OSError:
                time.sleep(.1)
        self.__exit__(None, None, None)
        raise RuntimeError('Original SUT startup timed out')

    def __exit__(self, *_):
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()
        finally:
            self.output.close()


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def default_sets(profile):
    if profile == 'contract':
        return 'catalog,v013-common,v013-contract,v013-negative,v013-negative-contract,v013-gaps'
    return 'catalog,v013-common,v013-negative,v013-negative-original,v013-gaps'


def build_adapter(root, source, jar, java, sets, only):
    """Patch, copy and compile the Java adapter into root; list the selection.

    Returns (harness command prefix, selection arguments, scenario count)."""
    src = root / 'src'; src.mkdir()
    classes = root / 'classes'; classes.mkdir()
    (src / 'StrictGuidedRun.java').write_text(patch(source.read_text(encoding='utf-8')), encoding='utf-8')
    for name in JAVA_SOURCES:
        shutil.copy2(HERE / name, src / name)
    shutil.copy2(HERE.parent / 'campaign-v011/V011Actuation.java', src / 'V011Actuation.java')
    compile_result = runtime.run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-cp', jar, '-d', classes,
                                  *(src / n for n in ['StrictGuidedRun.java', 'V011Actuation.java'] + JAVA_SOURCES)], root, 'compile', 180)
    if compile_result['exit_code']:
        raise RuntimeError('Java compilation failed: inspect compile.log; use a JDK matching Provengo')
    cp = str(classes) + os.pathsep + str(jar)
    harness = [java, '-cp', cp, 'V013GuidedSuiteHarness']
    selection = ['--set', sets] + (['--only', only] if only else [])
    listing = runtime.run(harness + [root / 'model', root / 'selection.txt', '1', '--list'] + selection, root, 'catalog', 60)
    catalog_log = (root / 'catalog.log').read_text(encoding='utf-8', errors='replace')
    count_line = next((l for l in catalog_log.splitlines() if l.startswith('SCENARIO_COUNT=')), None)
    if listing['exit_code'] or not count_line:
        raise RuntimeError('Scenario listing failed; inspect catalog.log')
    count = int(count_line.split('=')[1])
    if count == 0:
        raise RuntimeError('No scenarios selected')
    return harness, selection, count, compile_result['wall_seconds']


def arm_name(bugs):
    return 'control' if bugs == 'none' else 'bugs-' + bugs.replace(',', '-')


def reachability(native):
    summary = {'reached_as_expected': [], 'blocked_as_expected': [], 'stuck_unexpectedly': [], 'reached_unexpectedly': [],
               'actuation_errors': [], 'exceptions': []}
    for r in native:
        case = str(r['case'])
        if r['exception']:
            summary['exceptions'].append(case)
        if r['actuator_errors'] or r['listener_errors']:
            summary['actuation_errors'].append(case)
        if r['expectReached'] and r['reached']:
            summary['reached_as_expected'].append(case)
        elif r['expectReached'] and not r['reached']:
            summary['stuck_unexpectedly'].append(case)
        elif not r['expectReached'] and not r['reached']:
            summary['blocked_as_expected'].append(case)
        else:
            summary['reached_unexpectedly'].append(case)
    by_set = {}
    for r in native:
        s = by_set.setdefault(r['set'], {'scenarios': 0, 'native_pass': 0})
        s['scenarios'] += 1
        s['native_pass'] += bool(r['native_pass'])
    summary['by_set'] = by_set
    summary['counts'] = {k: len(v) for k, v in summary.items() if isinstance(v, list)}
    return summary


def transport_counts(http):
    tool = [r for r in http if r['role'] == 'tool']
    def path(r): return r['path'].split('?')[0]
    return {'tool_requests': len(tool),
            'successful_loans': sum(r['method'] == 'POST' and path(r) == '/loans' and r['status'] == 201 for r in tool),
            'successful_holds': sum(r['method'] == 'POST' and path(r) == '/holds' and r['status'] == 201 for r in tool),
            'get_requests': sum(r['method'] == 'GET' for r in tool),
            'book_detail_reads': sum(r['method'] == 'GET' and path(r).startswith('/books/') for r in tool),
            'delete_requests': sum(r['method'] == 'DELETE' for r in tool),
            'rejected_as_expected_4xx': sum(r['method'] in ('POST', 'DELETE', 'GET') and 400 <= r['status'] < 500 for r in tool)}


def main(args):
    started = time.perf_counter()
    repo = args.repo.resolve()
    jar = args.jar.resolve()
    if not jar.is_file():
        raise RuntimeError('Provengo JAR missing: ' + str(jar))
    source = HERE.parent / 'src/StrictGuidedRun.java'
    root = (args.output_root or repo / 'library/ess-experiment/runs').resolve() / ('guided-v013-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    root.mkdir(parents=True)
    timing = {}
    complete = False
    original = args.sut == 'original'
    if original and (args.profile != 'original' or args.arms != 'none'):
        raise RuntimeError('--sut original requires --profile original and --arms none (the original SUT has no mutation switches)')
    try:
        profile = prepare(repo, root, profile=args.profile, stories=args.stories, users=args.users, books=args.books,
                          loan_cap=args.loan_cap, hold_cap=args.hold_cap, pair_cap=args.pair_cap, max_length=args.max_length,
                          port=23242 if original else 23243)
        if original:
            shutil.copy2(repo / 'library/sut/sut.py', root / 'sut.py')
        sets = args.sets or default_sets(args.profile)
        harness, selection, expected_count, compile_seconds = build_adapter(root, source, jar, args.java, sets, args.only)
        timing['compilation_seconds'] = compile_seconds
        if original:
            selection = selection + ['--boundary', 'direct']
        service = (lambda folder, bugs: PlainSut(root, folder)) if original else (lambda folder, bugs: runtime.Service(root, folder, bugs))
        write(root / 'environment.json', {
            'version': 'v013', 'repo': str(repo), 'provengo_jar': str(jar), 'jar_sha256': sha(jar), 'python': sys.version,
            'sut': 'library/sut/sut.py (original rules, no observer)' if original else 'library/sut/sut_buggy_issta.py behind the v006 observer',
            'java_source_sha256': sha(source), 'java_source_normalized_sha256': SOURCE_SHA,
            'patched_source_sha256': sha(root / 'src/StrictGuidedRun.java'),
            'runtime_patch': 'v011 native RTV evaluation, ActuationSummary checks, stop on failed actuation, cleanup; '
                             'v013 action naming from transport shape (V013Match), rejection checks as steps',
            'scenario_sets': sets, 'scenario_count': expected_count, 'only': args.only, 'model_profile': profile,
            'arms': [arm_name(a) for a in args.arms.split(',')],
            'case_timeout_seconds': args.case_timeout, 'arm_timeout_seconds': args.arm_timeout})
        write(root / 'input_hashes.json', {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file() and 'classes' not in p.parts})

        if not args.skip_preflight and not original:
            preflight_started = time.perf_counter()
            for name, negative in [('preflight-positive', False), ('preflight-wrong-status', True)]:
                folder = root / name; folder.mkdir()
                model = root / 'model'
                if negative:
                    model = root / 'preflight-negative-model'
                    shutil.copytree(root / 'model', model)
                    interface = model / 'spec/js/interfaces.library.js'
                    text = interface.read_text(encoding='utf-8')
                    if 'expectedResponseCodes: [201]' not in text:
                        raise RuntimeError('Negative self-check anchor changed')
                    interface.write_text(text.replace('expectedResponseCodes: [201]', 'expectedResponseCodes: [202]'), encoding='utf-8')
                with runtime.Service(root, folder, 'none'):
                    check = runtime.run(harness + [model, folder / 'native.jsonl', args.case_timeout, '--smoke'], folder, 'java-suite', args.case_timeout + 30)
                native = rows(folder / 'native.jsonl'); http = rows(folder / 'http.jsonl')
                if check['exit_code'] or len(native) != 1:
                    raise RuntimeError('Incomplete transport self-check: ' + name)
                if negative:
                    log = (folder / 'java-suite.log').read_text(encoding='utf-8', errors='replace')
                    if native[0]['native_pass'] or not native[0]['actuator_errors'] or 'unexpected response code' not in log:
                        raise RuntimeError('Native HTTP-status assertion self-check failed')
                else:
                    loans = [r for r in http if r['role'] == 'tool' and r['method'] == 'POST' and r['path'].split('?')[0] == '/loans' and r['status'] == 201]
                    if not native[0]['native_pass'] or len(loans) != 1 or any(r['role'] in ('verdict', 'observer_error') for r in http):
                        raise RuntimeError('Native RTV/loan self-check failed')
                    actual = loans[0]['response']
                    if str(loans[0]['request'].get('userId')) != str(actual.get('userId')) or str(loans[0]['request'].get('bookId')) != str(actual.get('bookId')):
                        raise RuntimeError('Loan request/response identity mismatch')
                write(folder / 'self_check.json', {'passed': True, 'negative_control': negative})
            timing['transport_preflight_seconds'] = time.perf_counter() - preflight_started

        summary = {}
        control = {}
        for bugs in args.arms.split(','):
            arm = arm_name(bugs)
            folder = root / arm; folder.mkdir()
            print('START JAVA ' + arm + ' BUGS=' + bugs, flush=True)
            with service(folder, bugs):
                outcome = runtime.run(harness + [root / 'model', folder / 'native.jsonl', args.case_timeout] + selection, folder, 'java-suite', args.arm_timeout)
            timing[arm + '_seconds'] = outcome['wall_seconds']
            native = rows(folder / 'native.jsonl')
            if len(native) != expected_count or outcome['exit_code']:
                raise RuntimeError('Incomplete ' + arm + '; evidence preserved; do not score incomplete suites')
            if original:
                failed = [str(r['case']) for r in native if not r['native_pass']]
                summary[arm] = {'bugs': 'n/a (original sut.py)', 'scenario_count': len(native), 'reachability': reachability(native),
                                'native_failures': failed, 'scoring_note': 'Reachability against the original rules; no observer in this mode'}
                write(root / 'results.json', summary)
                print('END JAVA ' + arm + ' NATIVE_FAILURES=' + str(len(failed)) + ' REACHABILITY=' + json.dumps(summary[arm]['reachability']['counts']), flush=True)
                continue
            http = rows(folder / 'http.jsonl')
            if any(r['role'] == 'observer_error' for r in http):
                raise RuntimeError('Observer error in ' + arm + '; inspect evidence before scoring')
            boundaries = [r for r in http if r['role'] == 'boundary']
            if len(boundaries) != expected_count or any(not r.get('empty_verified') for r in boundaries):
                raise RuntimeError('Missing verified empty case boundaries in ' + arm)
            if any('@{' in json.dumps(r.get('request')) for r in http if r['role'] == 'tool'):
                raise RuntimeError('Unresolved request-body RTV in ' + arm + '; execution invalid')
            transport = transport_counts(http)
            if arm == 'control' and not transport['successful_loans']:
                raise RuntimeError('Control created no real loans; do not score')
            if arm == 'control':
                control = {str(r['case']): r for r in native}
            observer = counts(folder)
            failed = [str(r['case']) for r in native if not r['native_pass']]
            eligible = {case for case, r in control.items() if r['native_pass']
                        and case not in summary.get('control', {}).get('observer', {}).get('clean_candidate_cases', {})}
            summary[arm] = {'bugs': bugs, 'scenario_count': len(native), 'reachability': reachability(native),
                            'native_failures': failed, 'transport_counts': transport, 'observer': observer,
                            'native_failures_on_control_eligible_cases': [c for c in failed if c in eligible],
                            'native_failures_with_clean_observer_candidate': {c: observer['clean_candidate_cases'][c] for c in failed
                                                                              if c in eligible and c in observer['clean_candidate_cases']},
                            'scoring_note': 'Native failure and observer candidate are separate evidence; inspect logs before assigning unique seeded bugs'}
            write(root / 'results.json', summary)
            print('END JAVA ' + arm + ' NATIVE_FAILURES=' + str(len(failed)) + ' REACHABILITY=' + json.dumps(summary[arm]['reachability']['counts']), flush=True)
        complete = True
        write(root / 'completed.json', {'complete': True, 'scenario_count': expected_count, 'sets': sets})
    finally:
        timing['total_before_packaging_seconds'] = time.perf_counter() - started
        write(root / 'timings.json', timing)
        archive = root.with_name(root.name + '-review.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob('*'):
                if p.is_file() and not {'products', '__pycache__', 'classes'}.intersection(p.relative_to(root).parts):
                    z.write(p, p.relative_to(root))
        print('V013_TIMINGS ' + json.dumps(timing), flush=True)
        print('V013_REVIEW_ZIP ' + str(archive), flush=True)
        if complete:
            print('GUIDED_V013_COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--java', default='java')
    parser.add_argument('--profile', choices=('contract', 'original'), default='contract')
    parser.add_argument('--sut', choices=('fixture', 'original'), default='fixture',
                        help='fixture: sut_buggy_issta.py behind the observer; original: plain sut.py on 23242 (profile original, arm none)')
    parser.add_argument('--stories', choices=('full', 'business'), default='full')
    parser.add_argument('--users', type=int, default=5)
    parser.add_argument('--books', type=int, default=5)
    parser.add_argument('--loan-cap', type=int, default=5)
    parser.add_argument('--hold-cap', type=int, default=5)
    parser.add_argument('--pair-cap', type=int, default=3)
    parser.add_argument('--max-length', type=int, default=500)
    parser.add_argument('--arms', default='none,1,2,3,4,5', help='comma-separated ISSTA_BUGS values; "-" joins bugs within one arm')
    parser.add_argument('--sets', help='scenario sets: catalog,v013-common,v013-contract (default by profile)')
    parser.add_argument('--only', help='keep only scenarios whose name contains this text')
    parser.add_argument('--skip-preflight', action='store_true')
    parser.add_argument('--case-timeout', type=int, default=120)
    parser.add_argument('--arm-timeout', type=int, default=7200)
    parser.add_argument('--output-root', type=Path)
    main(parser.parse_args())
