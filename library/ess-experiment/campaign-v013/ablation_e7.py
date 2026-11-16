"""E7: b-thread ablation of the single-event Library model.

For every story b-thread in lib_stories.js, build a model copy with that b-thread disabled and run
the whole guided catalog (frozen 542 + v013 additions, rejection steps included) against it.
Compare every scenario's outcome with the unablated baseline:

  newly stuck        expected-reachable scenarios that reached on the baseline and are STUCK now;
                     the action they stop at must be one the ablated b-thread produces
  blocked earlier    expected-blocked scenarios whose prefix got shorter (informational)
  newly reached      expected-blocked scenarios that now reach: a guard was lost (never expected
                     from removing a story; guards live in the DAL queries)
  native failures    a request the remaining model still sends now fails: unexpected coupling

Verdicts: CONFIRMED (every change is explained by the ablated b-thread's own actions),
NO_DEPENDENT_SCENARIO (nothing changed: the b-thread is either redundant or untested by the
catalog), UNEXPECTED (some change is not explained; listed).

    .venv/bin/python library/ess-experiment/campaign-v013/ablation_e7.py \\
        --repo . --jar ~/provengo/Provengo-2026-01-10.uber.jar --profile original --sut original
"""
import argparse
import collections
import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for folder in ('campaign-v004', 'campaign-v006', 'campaign-v009', 'campaign-v011'):
    sys.path.insert(0, str(HERE.parent / folder))
sys.path.insert(0, str(HERE))
import pilot_v006 as runtime  # noqa: E402
from guided_suite_v013 import build_adapter, rows, default_sets, PlainSut  # noqa: E402
from prepare_model_v013 import prepare, sha, write  # noqa: E402

BTHREAD = re.compile(r'^(ctx\.bthread|bthread|forEachEvent)\("([A-Za-z]+)"', re.M)

# Actions each b-thread is the producer of (what a scenario can only reach through it).
PREDICTED = {
    'createUsers': {'createUser'}, 'createBooks': {'createBook'},
    'createLoan': {'createLoan'}, 'createHold': {'createHold'},
    'deleteUser': {'deleteUser'}, 'deleteBook': {'deleteBook'}, 'deleteLoan': {'deleteLoan'}, 'deleteHold': {'deleteHold'},
    'verifyUserExistsAfterCreation': {'readUsers'}, 'verifyBookExistsAfterCreation': {'readBooks'},
    'verifyBookDetailExistsAfterCreation': {'readBookDetail'}, 'verifyLoanExists': {'readLoans'}, 'verifyHoldExistsAfterCreation': {'readHolds'},
    'verifyUserAbsentFromUsersAfterDeletion': {'readUsers'}, 'verifyUserAbsentFromLoansAfterDeletion': {'readLoans'}, 'verifyUserAbsentFromHoldsAfterDeletion': {'readHolds'},
    'verifyBookAbsentFromBooksAfterDeletion': {'readBooks'}, 'verifyBookAbsentFromLoansAfterDeletion': {'readLoans'}, 'verifyBookAbsentFromHoldsAfterDeletion': {'readHolds'},
    'verifyLoanAbsentAfterDeletion': {'readLoans'}, 'verifyHoldAbsentAfterDeletion': {'readHolds'},
    'verifyDeletedUserCannotBeDeletedAgain': {'rejectDeleteUser404'}, 'verifyDeletedBookCannotBeDeletedAgain': {'rejectDeleteBook404'},
    'verifyDeletedBookDetailIsRejected': {'rejectReadBookDetail404'},
    'verifyDeletedLoanCannotBeDeletedAgain': {'rejectDeleteLoan404'}, 'verifyDeletedHoldCannotBeDeletedAgain': {'rejectDeleteHold404'},
    'verifyLoanBlocksUserDeletion': {'rejectDeleteUser400'}, 'verifyHoldBlocksUserDeletion': {'rejectDeleteUser400'},
    'verifyLoanBlocksBookDeletion': {'rejectDeleteBook400'}, 'verifyHoldBlocksBookDeletion': {'rejectDeleteBook400'},
    'verifyCannotCreateLoan': {'rejectCreateLoan400'},
    'verifyCannotCreateLoanWithNonexistentBook': {'rejectCreateLoan400'}, 'verifyCannotCreateLoanWithNonexistentUser': {'rejectCreateLoan400'},
    'verifyCannotCreateLoanWithNonexistentUserAndBook': {'rejectCreateLoan400'},
    'verifyCannotCreateHoldWithNonexistentBook': {'rejectCreateHold400'}, 'verifyCannotCreateHoldWithNonexistentUser': {'rejectCreateHold400'},
    'verifyCannotCreateHoldWithNonexistentUserAndBook': {'rejectCreateHold400'},
    'tryToDeleteNonexistingUser': {'rejectDeleteUser404'}, 'tryToDeleteNonexistingBook': {'rejectDeleteBook404'},
    'tryToDeleteNonexistingLoan': {'rejectDeleteLoan404'}, 'tryToDeleteNonexistingHold': {'rejectDeleteHold404'},
}


def bthreads(stories):
    return [m.group(2) for m in BTHREAD.finditer(stories)]


def ablate(stories, name):
    pattern = re.compile(r'^((?:ctx\.bthread|bthread|forEachEvent)\("' + re.escape(name) + r'")', re.M)
    if len(pattern.findall(stories)) != 1:
        raise RuntimeError('Expected exactly one registration of ' + name)
    return pattern.sub(r'if (false) \1', stories, count=1)


def outcome(r):
    return 'reached' if r['reached'] else 'stuck@%d:%s' % (r['reachedSteps'], r['failedAction'])


def compare(baseline, ablated, predicted):
    base = {str(r['case']): r for r in baseline}
    newly_stuck, blocked_earlier, newly_reached, failures, other = [], [], [], [], []
    actions = collections.Counter()
    for r in ablated:
        case = str(r['case'])
        b = base[case]
        if r['actuator_errors'] or r['listener_errors'] or r['exception']:
            failures.append(case)
        if r['expectReached']:
            if b['reached'] and not r['reached']:
                newly_stuck.append(case)
                actions[r['failedAction']] += 1
            elif outcome(b) != outcome(r):
                other.append((case, outcome(b), outcome(r)))
        else:
            if r['reached'] and not b['reached']:
                newly_reached.append(case)
            elif not r['reached'] and r['reachedSteps'] < b['reachedSteps']:
                blocked_earlier.append(case)
            elif outcome(b) != outcome(r):
                other.append((case, outcome(b), outcome(r)))
    unexplained = sorted(a for a in actions if a is None or not any(a.startswith(p) for p in predicted))
    if newly_reached or failures or other or unexplained:
        verdict = 'UNEXPECTED'
    elif newly_stuck:
        verdict = 'CONFIRMED'
    elif blocked_earlier:
        verdict = 'CONFIRMED (prefixes only)'
    else:
        verdict = 'NO_DEPENDENT_SCENARIO'
    return {'verdict': verdict, 'newly_stuck': newly_stuck, 'failing_actions': dict(actions), 'unexplained_actions': unexplained,
            'blocked_earlier': blocked_earlier, 'newly_reached': newly_reached, 'native_failures': failures, 'other_changes': other}


def report(results, order):
    lines = ['# E7 b-thread ablation (%s profile, %d scenarios)' % (results['profile'], results['scenario_count']), '',
             'Baseline: %d reached, %d blocked as expected, %d stuck, %d reached unexpectedly.' % tuple(results['baseline_counts'][k] for k in ('reached', 'blocked', 'stuck', 'reached_unexpectedly')), '',
             '| Ablated b-thread | Produces | Newly stuck | Stuck at | Blocked earlier | Unexpected | Verdict |', '| --- | --- | ---: | --- | ---: | --- | --- |']
    for name in order:
        c = results['ablations'][name]
        unexpected = []
        if c['newly_reached']: unexpected.append('reached-unexpectedly: ' + ','.join(c['newly_reached']))
        if c['native_failures']: unexpected.append('native-failures: ' + ','.join(c['native_failures']))
        if c['unexplained_actions']: unexpected.append('unexplained: ' + ','.join(map(str, c['unexplained_actions'])))
        if c['other_changes']: unexpected.append('other: %d' % len(c['other_changes']))
        lines.append('| %s | %s | %d | %s | %d | %s | %s |' % (
            name, ', '.join(sorted(PREDICTED.get(name, {'?'}))), len(c['newly_stuck']),
            ', '.join('%s×%d' % (a, n) for a, n in sorted(c['failing_actions'].items(), key=lambda x: str(x[0]))) or '-',
            len(c['blocked_earlier']), '; '.join(unexpected) or '-', c['verdict']))
    counts = collections.Counter(results['ablations'][n]['verdict'] for n in order)
    lines += ['', ', '.join('%s: %d' % kv for kv in sorted(counts.items())) + '.']
    return '\n'.join(lines) + '\n'


def main(args):
    repo = args.repo.resolve()
    jar = args.jar.resolve()
    original = args.sut == 'original'
    if original and args.profile != 'original':
        raise RuntimeError('--sut original requires --profile original')
    root = (args.output_root or repo / 'library/ess-experiment/runs').resolve() / ('e7-ablation-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    root.mkdir(parents=True)
    started = time.perf_counter()
    results = {'profile': args.profile, 'ablations': {}}
    try:
        profile = prepare(repo, root, profile=args.profile, stories='full', users=args.users, books=args.books, port=23242 if original else 23243)
        if original:
            shutil.copy2(repo / 'library/sut/sut.py', root / 'sut.py')
        stories_path = root / 'model/spec/js/lib_stories.js'
        stories = stories_path.read_text(encoding='utf-8')
        names = bthreads(stories)
        if args.only:
            names = [n for n in names if n in args.only.split(',')]
        unknown = [n for n in names if n not in PREDICTED]
        if unknown:
            raise RuntimeError('No prediction for b-threads: ' + ', '.join(unknown) + ' (add them to PREDICTED)')
        sets = args.sets or default_sets(args.profile)
        harness, selection, count, _ = build_adapter(root, HERE.parent / 'src/StrictGuidedRun.java', jar, args.java, sets, None)
        if original:
            selection = selection + ['--boundary', 'direct']
        results.update({'scenario_count': count, 'scenario_sets': sets, 'bthreads': names, 'model_profile': profile})
        write(root / 'environment.json', {'version': 'v013-E7', 'provengo_jar': str(jar), 'jar_sha256': sha(jar), 'python': sys.version,
                                          'sut': 'library/sut/sut.py' if original else 'sut_buggy_issta.py behind the observer', 'bthreads': names})
        service = (lambda folder: PlainSut(root, folder)) if original else (lambda folder: runtime.Service(root, folder, 'none'))

        def arm(folder, model):
            folder.mkdir()
            with service(folder):
                outcome_ = runtime.run(harness + [model, folder / 'native.jsonl', args.case_timeout] + selection, folder, 'java-suite', args.arm_timeout)
            native = rows(folder / 'native.jsonl')
            if len(native) != count or outcome_['exit_code']:
                raise RuntimeError('Incomplete arm ' + folder.name)
            return native, outcome_['wall_seconds']

        print('BASELINE', flush=True)
        baseline, seconds = arm(root / 'baseline', root / 'model')
        results['baseline_counts'] = {'reached': sum(r['expectReached'] and r['reached'] for r in baseline),
                                      'blocked': sum(not r['expectReached'] and not r['reached'] for r in baseline),
                                      'stuck': sum(r['expectReached'] and not r['reached'] for r in baseline),
                                      'reached_unexpectedly': sum(not r['expectReached'] and r['reached'] for r in baseline),
                                      'wall_seconds': seconds}
        write(root / 'results.json', results)
        for name in names:
            print('ABLATE ' + name, flush=True)
            model = root / 'ablations' / name / 'model'
            shutil.copytree(root / 'model', model, ignore=shutil.ignore_patterns('products'))
            (model / 'spec/js/lib_stories.js').write_text(ablate(stories, name), encoding='utf-8')
            native, seconds = arm(root / 'ablations' / name / 'run', model)
            comparison = compare(baseline, native, PREDICTED[name])
            comparison['wall_seconds'] = seconds
            results['ablations'][name] = comparison
            write(root / 'results.json', results)
            print('  %s newly_stuck=%d blocked_earlier=%d %s' % (comparison['verdict'], len(comparison['newly_stuck']), len(comparison['blocked_earlier']), comparison['failing_actions']), flush=True)
            shutil.rmtree(model / 'products', ignore_errors=True)
        (root / 'E7_RESULTS.md').write_text(report(results, names), encoding='utf-8')
        print((root / 'E7_RESULTS.md').read_text(encoding='utf-8'))
        write(root / 'completed.json', {'complete': True, 'ablations': len(names)})
        print('E7_COMPLETE', flush=True)
    finally:
        results['total_seconds'] = time.perf_counter() - started
        write(root / 'timings.json', {'total_seconds': results['total_seconds']})
        archive = root.with_name(root.name + '-review.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob('*'):
                if p.is_file() and not {'products', '__pycache__', 'classes'}.intersection(p.relative_to(root).parts):
                    z.write(p, p.relative_to(root))
        print('E7_DIR ' + str(root), flush=True)
        print('E7_REVIEW_ZIP ' + str(archive), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--java', default='java')
    parser.add_argument('--profile', choices=('contract', 'original'), default='original')
    parser.add_argument('--sut', choices=('fixture', 'original'), default='original')
    parser.add_argument('--sets')
    parser.add_argument('--only', help='comma-separated b-thread names to ablate (default all)')
    parser.add_argument('--users', type=int, default=5)
    parser.add_argument('--books', type=int, default=5)
    parser.add_argument('--case-timeout', type=int, default=120)
    parser.add_argument('--arm-timeout', type=int, default=7200)
    parser.add_argument('--output-root', type=Path)
    main(parser.parse_args())
