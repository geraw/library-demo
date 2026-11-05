"""Run a full control preflight, then replay frozen samples on isolated workers."""
import argparse
import hashlib
import os
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid


def main(args):
    benchmark = args.repo / 'library/benchmark-v001'
    sys.path.insert(0, str(benchmark))
    import campaign_v001 as bench
    source = args.reuse_run
    manifest = json.loads((source / 'samples/manifest.json').read_text(encoding='utf-8-sig'))
    cases = sorted(item['case'] for item in manifest)
    if cases != list(range(1, 101)):
        raise ValueError('Expected exactly the original 100 frozen samples')
    root = source.parent / ('library-replay-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    root.mkdir()
    print('REPLAY_DIRECTORY', root, flush=True)
    base = [sys.executable, str(Path(__file__).with_name('pilot_library.py')),
            '--benchmark', str(benchmark), '--original', str(source / 'frozen-sut/original.py'),
            '--mutants', str(source / 'frozen-sut/mutants.py'),
            '--config', str(benchmark / 'tools.local.json'), '--reuse-run', str(source),
            '--sample-size', '100', '--case-timeout', str(args.case_timeout)]
    source_pilot = json.loads((source / 'pilot.json').read_text())
    base += ['--seed', str(source_pilot['seed']), '--max-length', str(source_pilot['max_length'])]
    fingerprint = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                   for name in ('pilot_library.py', 'replay_parallel.py')}
    bench.write(root / 'replay.json', {'source': str(source), 'workers': args.workers,
                                     'ports': [23501 + i for i in range(args.workers)],
                                     'script_sha256': fingerprint, 'case_timeout': args.case_timeout,
                                     'B6': 'BLOCKED_BY_SERIAL_GATEWAY'})
    gate = root / 'preflight'
    try:
        print('PREFLIGHT original and baseline: case 12, port 23500', flush=True)
        result = bench.launch(base + ['--output', str(gate), '--cases', '12', '--port', '23500',
                                      '--controls-only'],
                              root, 'preflight', 2 * args.case_timeout + 600)
        bench.require(result, root, 'preflight')
        if not (gate / 'completed.json').is_file():
            raise RuntimeError('Control preflight did not produce completed.json')
        print('PREFLIGHT PASSED', flush=True)
        if args.preflight_only:
            return
        groups = [cases[index::args.workers] for index in range(args.workers)]

        running = []
        folders = []
        try:
            for index, group in enumerate(groups):
                port = 23501 + index
                name = f'worker-{index + 1}'
                folder = root / name
                folders.append(folder)
                command = base + ['--output', str(folder), '--port', str(port), '--cases',
                                  ','.join(map(str, group))]
                log = (root / (name + '.log')).open('w', encoding='utf-8')
                bench.write(root / (name + '-command.json'), command)
                proc = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=os.name != 'nt')
                running.append((name, proc, log))
                print(f'START {name} PORT={port} CASES={len(group)} LOG={root / (name + ".log")}', flush=True)
            next_notice = time.monotonic() + 30
            while any(proc.poll() is None for _, proc, _ in running):
                for name, proc, _ in running:
                    if proc.poll() not in (None, 0):
                        raise RuntimeError(f'{name} failed. Inspect {root / (name + ".log")}')
                if time.monotonic() >= next_notice:
                    for name, proc, _ in running:
                        progress = root / name
                        executions = list(progress.glob('*/case-*-execution.json'))
                        print(f'PROGRESS {name} finished_replays={len(executions)} process={proc.poll()}', flush=True)
                    next_notice = time.monotonic() + 30
                time.sleep(1)
            for name, proc, _ in running:
                if proc.returncode != 0:
                    raise RuntimeError(f'{name} failed; inspect its log')
        finally:
            for _, proc, log in running:
                bench.terminate(proc)
                log.close()
        merged = {}
        for folder in folders:
            if not (folder / 'completed.json').is_file():
                raise RuntimeError(f'Worker did not complete: {folder}')
            for arm, report in json.loads((folder / 'summary.json').read_text()).items():
                cell = merged.setdefault(arm, {'cases': {}, 'http_requests': 0, 'http_5xx': 0,
                                                'passive_bug_ids': set(),
                                                'native_failures_on_passing_baseline': []})
                if set(cell['cases']) & set(report['cases']):
                    raise ValueError('Duplicate case across workers')
                cell['cases'].update(report['cases'])
                cell['http_requests'] += report['http_requests']
                cell['http_5xx'] += report['http_5xx']
                cell['passive_bug_ids'].update(report['passive_bug_ids'])
                cell['native_failures_on_passing_baseline'].extend(report['native_failures_on_passing_baseline'])
        for arm, report in merged.items():
            if set(report['cases']) != set(map(str, cases)):
                raise ValueError(f'Incomplete aggregate for {arm}')
            report['passive_bug_ids'] = sorted(report['passive_bug_ids'])
            if arm == 'B6':
                report['reachability'] = 'BLOCKED_BY_SERIAL_GATEWAY'
        bench.write(root / 'summary.json', merged)
        bench.write(root / 'completed.json', {'replays': 800, 'preflight_replays': 2,
                                             'B6': 'BLOCKED_BY_SERIAL_GATEWAY'})
        print('REPLAY_COMPLETE', root, flush=True)
    except Exception as exc:
        bench.write(root / 'failure.json', {'error': str(exc)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--reuse-run', type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--workers', type=int, choices=(1, 2), default=2)
    parser.add_argument('--case-timeout', type=int, default=7200)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if args.case_timeout <= 0:
        parser.error('Case timeout must be positive')
    main(args)
