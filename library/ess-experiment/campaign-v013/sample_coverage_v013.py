"""v013: unguided sampling coverage of the single-event Library model.

Samples N scenarios with `provengo sample` (no SUT involved: the sampler explores the b-program
and never actuates), compacts each sampled event to {action, outcome, parameters}, and measures
what the unguided model reaches on its own:

  * action coverage      every kind of request the model can send, by action and outcome
  * state coverage       abstract states visited, replaying creates/deletes over logical ids:
                         (users, books, active loans, holds, max active loans per reader,
                          max holds per reader, max holds per book, max borrowings per pair)
  * trigger reachability the five ISSTA logic-bug triggers as trace predicates, plus a set of
                         bug-catalog chapter-3 flows, with the first sample that hits each one
  * degeneracy indicators samples with no loan / no hold, eager-deletion rate, length

    .venv/bin/python library/ess-experiment/campaign-v013/sample_coverage_v013.py \\
        --repo . --profile contract --size 50

Writes coverage.json and coverage.md to library/ess-experiment/runs/sample-v013-<timestamp>-<pid>/.
Sample files are large (the sampler serializes REST callbacks); batches are compacted and deleted
unless --keep-samples is given.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from prepare_model_v013 import prepare, write  # noqa: E402

ENTITY = {'books': 'Book', 'users': 'User', 'loans': 'Loan', 'holds': 'Hold'}


def classify(event):
    """Action name and outcome of one sampled REST event, from its transport shape only."""
    data = event.get('data') or {}
    if data.get('lib') != 'REST':
        return None
    method = str(data.get('method', '')).upper()
    path = re.sub(r'^https?://[^/]+', '', str(data.get('url', ''))).split('?')[0]
    segments = [s for s in path.split('/') if s]
    if not segments or segments[0] not in ENTITY:
        return None
    entity = ENTITY[segments[0]]
    if method == 'POST':
        action = 'create' + entity
    elif method == 'DELETE':
        action = 'delete' + entity
    elif method == 'GET':
        action = 'readBookDetail' if entity == 'Book' and len(segments) == 2 else 'read' + entity + 's'
    else:
        action = method.lower() + entity
    codes = [int(c) for c in data.get('expectedResponseCodes', [])]
    outcome = 'ok' if codes and all(200 <= c < 300 for c in codes) else 'rejected-' + '/'.join(str(c) for c in codes)
    parameters = data.get('parameters') or {}
    ids = {k: int(parameters[k]) for k in ('id', 'userId', 'bookId', 'loanNumber') if isinstance(parameters.get(k), (int, float))}
    description = str(parameters.get('description', ''))
    if not ids:
        # Rejection checks (tryTo*AndExpectError) label the event with the logical id in the
        # description only: "Verify: delete User 3 is rejected ...", "... Loan 2/4 ...".
        pair = re.search(r'\bLoan (\d+)/(\d+)', description)
        single = re.search(r'\b(User|Book|Hold) (\d+)', description)
        if pair:
            ids = {'userId': int(pair.group(1)), 'bookId': int(pair.group(2))}
        elif single:
            ids = {'id': int(single.group(2))}
    return {'action': action, 'outcome': outcome, 'ids': ids, 'description': description}


def compact_file(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    samples = data if isinstance(data, list) else next(data[k] for k in ('scenarios', 'runs', 'samples') if isinstance(data.get(k), list))
    return [[c for c in (classify(e) for e in sample) if c] for sample in samples]


class State:
    """Abstract state replay over logical ids; mirrors the DAL's bookkeeping, not the SUT's."""

    def __init__(self):
        self.users, self.books, self.loans, self.holds = set(), set(), set(), {}
        self.pair_borrowings = collections.Counter()

    def apply(self, event):
        a, ids = event['action'], event['ids']
        if event['outcome'] != 'ok':
            return
        if a == 'createUser': self.users.add(ids['id'])
        elif a == 'deleteUser': self.users.discard(ids['id'])
        elif a == 'createBook': self.books.add(ids['id'])
        elif a == 'deleteBook': self.books.discard(ids['id'])
        elif a == 'createLoan':
            self.loans.add((ids['userId'], ids['bookId'])); self.pair_borrowings[(ids['userId'], ids['bookId'])] += 1
        elif a == 'deleteLoan': self.loans.discard((ids['userId'], ids['bookId']))
        elif a == 'createHold': self.holds[ids['id']] = (ids['userId'], ids['bookId'])
        elif a == 'deleteHold': self.holds.pop(ids['id'], None)

    def loans_of(self, user): return sum(u == user for u, _ in self.loans)
    def holds_of(self, user): return sum(u == user for u, _ in self.holds.values())
    def holds_on(self, book): return sum(b == book for _, b in self.holds.values())

    def abstract(self):
        return (len(self.users), len(self.books), len(self.loans), len(self.holds),
                max([self.loans_of(u) for u in self.users] or [0]), max([self.holds_of(u) for u in self.users] or [0]),
                max([self.holds_on(b) for b in self.books] or [0]), max(self.pair_borrowings.values() or [0]))


TRIGGERS = {
    'ISSTA-1 fourth distinct active loan for one reader': lambda s, e: e['action'] == 'createLoan' and e['outcome'] == 'ok' and s.loans_of(e['ids']['userId']) >= 3,
    'ISSTA-2 third borrowing of the same pair': lambda s, e: e['action'] == 'createLoan' and e['outcome'] == 'ok' and s.pair_borrowings[(e['ids']['userId'], e['ids']['bookId'])] >= 2,
    'ISSTA-3 return while the reader has another active loan': lambda s, e: e['action'] == 'deleteLoan' and e['outcome'] == 'ok' and s.loans_of(e['ids']['userId']) >= 2,
    'ISSTA-4 detail read of an existing book': lambda s, e: e['action'] == 'readBookDetail' and e['outcome'] == 'ok' and e['ids'].get('id') in s.books,
    'ISSTA-5 hold cancelled while the reader has another hold': lambda s, e: e['action'] == 'deleteHold' and e['outcome'] == 'ok' and e['ids']['id'] in s.holds and s.holds_of(s.holds[e['ids']['id']][0]) >= 2,
    'ISSTA-5b hold cancelled while the book has another hold': lambda s, e: e['action'] == 'deleteHold' and e['outcome'] == 'ok' and e['ids']['id'] in s.holds and s.holds_on(s.holds[e['ids']['id']][1]) >= 2,
    '3.4 re-borrow of the same pair after a return': lambda s, e: e['action'] == 'createLoan' and e['outcome'] == 'ok' and s.pair_borrowings[(e['ids']['userId'], e['ids']['bookId'])] >= 1,
    '3.2 loan on a book that another reader holds': lambda s, e: e['action'] == 'createLoan' and e['outcome'] == 'ok' and any(b == e['ids']['bookId'] and u != e['ids']['userId'] for u, b in s.holds.values()),
    '3.6 hold on a book that is on loan': lambda s, e: e['action'] == 'createHold' and e['outcome'] == 'ok' and any(b == e['ids']['bookId'] for _, b in s.loans),
    '3.1 hold then loan by the same reader on the same book': lambda s, e: e['action'] == 'createLoan' and e['outcome'] == 'ok' and (e['ids']['userId'], e['ids']['bookId']) in s.holds.values(),
    '3.7 delete attempt of a reader who only holds (must be rejected)': lambda s, e: e['action'] == 'deleteUser' and e['outcome'].startswith('rejected') and e['ids']['id'] in s.users and s.holds_of(e['ids']['id']) >= 1 and s.loans_of(e['ids']['id']) == 0,
    '2.4.3 delete attempt of a reader with a loan (must be rejected)': lambda s, e: e['action'] == 'deleteUser' and e['outcome'].startswith('rejected') and s.loans_of(e['ids']['id']) >= 1,
    '2.7.4 delete attempt of a loaned book (must be rejected)': lambda s, e: e['action'] == 'deleteBook' and e['outcome'].startswith('rejected') and any(b == e['ids']['id'] for _, b in s.loans),
    '2.7.3 delete attempt of a held book (must be rejected)': lambda s, e: e['action'] == 'deleteBook' and e['outcome'].startswith('rejected') and s.holds_on(e['ids']['id']) >= 1,
    '2.9.4 second loan on a loaned book (must be rejected)': lambda s, e: e['action'] == 'createLoan' and e['outcome'].startswith('rejected') and any(b == e['ids'].get('bookId') for _, b in s.loans),
    '3.17 loan for a deleted book (must be rejected)': lambda s, e: e['action'] == 'createLoan' and e['outcome'].startswith('rejected') and e['ids'].get('bookId', 0) < 10 ** 9 and e['ids'].get('bookId') not in s.books,
    'read of a deleted book detail (must be 404)': lambda s, e: e['action'] == 'readBookDetail' and e['outcome'].startswith('rejected') and e['ids'].get('id') not in s.books,
    're-delete of a deleted entity (must be 404)': lambda s, e: e['action'].startswith('delete') and e['outcome'] == 'rejected-404' and e['ids'].get('id', 0) < 10 ** 9 and e['ids'].get('userId', 0) < 10 ** 9,
    '3.12 handover: book borrowed by a second reader after a return': lambda s, e: e['action'] == 'createLoan' and e['outcome'] == 'ok' and any(u != e['ids']['userId'] and b == e['ids']['bookId'] for (u, b) in s.pair_borrowings),
}


def analyze(samples, profile):
    actions = collections.Counter()
    per_sample_actions = []
    states = set()
    state_growth = []
    trigger_first = {}
    trigger_samples = collections.Counter()
    maxima = collections.Counter()
    no_loan = no_hold = 0
    lengths = []
    eager = 0  # a user or book deleted before any loan/hold existed in that sample
    for index, sample in enumerate(samples, 1):
        state = State()
        seen = set()
        hits = set()
        had_relation = False
        lengths.append(len(sample))
        for event in sample:
            key = event['action'] + ' ' + event['outcome']
            actions[key] += 1
            seen.add(key)
            for name, predicate in TRIGGERS.items():
                try:
                    if predicate(state, event):
                        hits.add(name)
                except KeyError:
                    pass
            if event['outcome'] == 'ok' and event['action'] in ('createLoan', 'createHold'):
                had_relation = True
            if event['outcome'] == 'ok' and event['action'] in ('deleteUser', 'deleteBook') and not had_relation:
                eager += 1; had_relation = True  # count once per sample
            state.apply(event)
            abstract = state.abstract()
            states.add(abstract)
            for i, name in enumerate(('users', 'books', 'active_loans', 'holds', 'loans_per_reader', 'holds_per_reader', 'holds_per_book', 'borrowings_per_pair')):
                maxima[name] = max(maxima[name], abstract[i])
        per_sample_actions.append(len(seen))
        state_growth.append(len(states))
        for name in hits:
            trigger_samples[name] += 1
            trigger_first.setdefault(name, index)
        if not any(k.startswith('createLoan ok') for k in seen): no_loan += 1
        if not any(k.startswith('createHold ok') for k in seen): no_hold += 1
    n = len(samples)
    return {
        'profile': profile, 'samples': n,
        'length': {'mean': sum(lengths) / n, 'min': min(lengths), 'max': max(lengths)},
        'action_kinds_total': len(actions), 'action_kinds': dict(sorted(actions.items())),
        'action_kinds_per_sample_mean': sum(per_sample_actions) / n,
        'abstract_states_distinct': len(states), 'abstract_state_growth': state_growth, 'maxima': dict(maxima),
        'triggers': {name: {'samples_hit': trigger_samples.get(name, 0), 'first_sample': trigger_first.get(name)} for name in TRIGGERS},
        'degeneracy': {'samples_without_loan': no_loan, 'samples_without_hold': no_hold, 'samples_with_eager_deletion': eager},
    }


def report(result):
    lines = ['# Sampling coverage v013 (' + result['profile'] + ' profile, ' + str(result['samples']) + ' samples)', '',
             '| Measure | Value |', '| --- | --- |',
             '| Events per sample (mean / min / max) | %.1f / %d / %d |' % (result['length']['mean'], result['length']['min'], result['length']['max']),
             '| Distinct action kinds (action + outcome) | %d |' % result['action_kinds_total'],
             '| Action kinds per sample (mean) | %.1f |' % result['action_kinds_per_sample_mean'],
             '| Distinct abstract states | %d |' % result['abstract_states_distinct'],
             '| Samples without any loan / hold | %d / %d |' % (result['degeneracy']['samples_without_loan'], result['degeneracy']['samples_without_hold']),
             '| Samples with a reader/book deleted before any loan or hold | %d |' % result['degeneracy']['samples_with_eager_deletion'], '',
             '## Maxima reached', '', '| Dimension | Max |', '| --- | ---: |']
    lines += ['| %s | %d |' % (k, v) for k, v in result['maxima'].items()]
    lines += ['', '## Trigger reachability', '', '| Trigger | Samples hitting it | First sample |', '| --- | ---: | ---: |']
    lines += ['| %s | %d | %s |' % (k, v['samples_hit'], v['first_sample'] if v['first_sample'] else 'never') for k, v in result['triggers'].items()]
    lines += ['', '## Action kinds', '', '| Action | Count |', '| --- | ---: |']
    lines += ['| %s | %d |' % (k, v) for k, v in result['action_kinds'].items()]
    growth = result['abstract_state_growth']
    checkpoints = sorted({1, 5, 10, 20, 50, 100, 200, len(growth)} & set(range(1, len(growth) + 1)))
    lines += ['', '## Abstract-state saturation', '', '| Samples | Distinct states |', '| ---: | ---: |']
    lines += ['| %d | %d |' % (c, growth[c - 1]) for c in checkpoints]
    return '\n'.join(lines) + '\n'


def main(args):
    repo = args.repo.resolve()
    root = (args.output_root or repo / 'library/ess-experiment/runs').resolve() / ('sample-v013-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    root.mkdir(parents=True)
    profile = prepare(repo, root, profile=args.profile, stories=args.stories, users=args.users, books=args.books,
                      loan_cap=args.loan_cap, hold_cap=args.hold_cap, pair_cap=args.pair_cap, max_length=args.max_length)
    samples = []
    batches = []
    started = time.perf_counter()
    batch = 0
    while len(samples) < args.size:
        batch += 1
        count = min(args.batch, args.size - len(samples))
        sample_file = root / ('batch-%03d.json' % batch)
        command = [args.provengo, 'sample', '--overwrite', '--size', str(count), '--max-length', str(args.max_length), '-o', str(sample_file), str(root / 'model')]
        with (root / ('batch-%03d.log' % batch)).open('w', encoding='utf-8') as log:
            outcome = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=args.batch_timeout)
        if outcome.returncode or not sample_file.exists():
            raise RuntimeError('Sampling batch %d failed; inspect its log' % batch)
        compacted = compact_file(sample_file)
        if len(compacted) != count:
            raise RuntimeError('Batch %d returned %d samples, expected %d' % (batch, len(compacted), count))
        samples.extend(compacted)
        batches.append({'batch': batch, 'count': count, 'bytes': sample_file.stat().st_size})
        if not args.keep_samples:
            sample_file.unlink()
        print('sampled %d/%d' % (len(samples), args.size), flush=True)
    write(root / 'samples-compact.json', samples)
    result = analyze(samples, args.profile)
    result['model_profile'] = profile
    result['sampling_seconds'] = time.perf_counter() - started
    result['batches'] = batches
    write(root / 'coverage.json', result)
    (root / 'coverage.md').write_text(report(result), encoding='utf-8')
    print(report(result))
    print('SAMPLE_V013_DIR ' + str(root))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--provengo', default='provengo', help='Provengo CLI command')
    parser.add_argument('--profile', choices=('contract', 'original'), default='contract')
    parser.add_argument('--stories', choices=('full', 'business'), default='full')
    parser.add_argument('--users', type=int, default=5)
    parser.add_argument('--books', type=int, default=5)
    parser.add_argument('--loan-cap', type=int, default=5)
    parser.add_argument('--hold-cap', type=int, default=5)
    parser.add_argument('--pair-cap', type=int, default=3)
    parser.add_argument('--max-length', type=int, default=500)
    parser.add_argument('--size', type=int, default=50)
    parser.add_argument('--batch', type=int, default=5)
    parser.add_argument('--batch-timeout', type=int, default=900)
    parser.add_argument('--keep-samples', action='store_true')
    parser.add_argument('--output-root', type=Path)
    main(parser.parse_args())
