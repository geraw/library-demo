"""Two-arm replay of immutable v004 samples; no new sampling or control replay."""
import argparse
import json
import math
from pathlib import Path
import sys
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'campaign-v004'))
import campaign_v004 as core

ARMS = {'business-four': '1,2,3,5', 'book-read-one': '4'}


def inputs(root):
    runs = json.loads((root / 'control/runs.json').read_text())
    if not runs or any(r['exit_code'] or r.get('timed_out') for r in runs):
        raise RuntimeError('A successful control suite is required')
    profile = json.loads((root / 'model_profile.json').read_text())
    if profile['profile'] != 'business':
        raise RuntimeError('A business sample is required')
    env = json.loads((root / 'environment.json').read_text())
    jar = Path(env['provengo_jar'])
    if core.sha(jar) != env['jar_sha256']:
        raise RuntimeError('Provengo JAR changed')
    samples = [(Path(r['source_file']), r['source_run_id']) for r in runs]
    for file, _ in samples:
        if not file.is_file():
            raise RuntimeError('Missing sample: ' + str(file))
    # Verify the prepared model and fixture against the original manifest.
    for relative, digest in json.loads((root / 'input_hashes.json').read_text()).items():
        if core.sha(root / relative) != digest:
            raise RuntimeError('Prepared input changed: ' + relative)
    return jar, samples


def compact(root):
    target = root.with_name(root.name + '-split-v005-compact.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for arm in ARMS:
            folder = root / ('split-v005-' + arm)
            if not folder.exists():
                continue
            for p in folder.glob('*.json'):
                z.write(p, p.relative_to(root))
            source = folder / 'http.jsonl'
            if source.exists():
                with z.open(folder.name + '/actions.jsonl', 'w') as output:
                    with source.open(encoding='utf-8') as stream:
                        for line in stream:
                            row = json.loads(line)
                            if row.get('role') in ('tool', 'verdict', 'boundary'):
                                output.write((json.dumps(row) + '\n').encode())
    print('REVIEW_ZIP ' + str(target), flush=True)


def replay(args):
    root = args.campaign.resolve()
    jar, samples = inputs(root)
    try:
        for arm, bugs in ARMS.items():
            folder = root / ('split-v005-' + arm)
            if (folder / 'completed.json').exists():
                print('ALREADY_COMPLETE ' + arm, flush=True)
                continue
            if folder.exists():
                raise RuntimeError('Incomplete output preserved; inspect ' + str(folder))
            result = core.replay(args.java, jar, root, samples, len(samples), folder.name, bugs)
            generation = json.loads((root / 'sampling.json').read_text())['wall_seconds']
            core.write(folder / 'budget.json', {
                'arm': arm, 'bugs': bugs, 'sample_size': len(samples),
                'sampling_seconds': generation,
                'mutant_execution_seconds': result['wall_seconds'],
                'baseline_search_budget_seconds': math.ceil(generation + result['wall_seconds']),
                'policy': 'Full generation plus this arm replay; control and isolated validation excluded',
                'official_score': 'NOT_YET_SCORED'})
            core.write(folder / 'completed.json', {'arm': arm, 'bugs': bugs, 'complete': True})
    finally:
        compact(root)


def evomaster(args):
    # Reuse the established version-adaptive launcher without altering its source
    # or the original campaign. Override only the chosen arm and budget input.
    root = args.campaign.resolve()
    budget_file = root / ('split-v005-' + args.arm) / 'budget.json'
    budget = json.loads(budget_file.read_text())['baseline_search_budget_seconds']
    folder = root / ('evomaster-v005-' + args.arm + '-' + time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    core.command([args.java, '-jar', args.jar, '--help'], folder / 'help.log', timeout=60)
    help_text = (folder / 'help.log').read_text()
    import re
    schema = '--schema' if re.search(r'--schema\b', help_text) else '--bbSwaggerUrl' if '--bbSwaggerUrl' in help_text else None
    base = '--base' if re.search(r'--base\b', help_text) else '--bbTargetUrl' if '--bbTargetUrl' in help_text else None
    if not schema or not base or '--maxTime' not in help_text:
        raise RuntimeError('Unsupported EvoMaster version: inspect help.log')
    command = [args.java, '-jar', args.jar, '--blackBox', 'true', schema, root / 'openapi.json',
               base, 'http://127.0.0.1:23243', '--maxTime', str(budget) + 's',
               '--seed', '1', '--outputFolder', folder / 'generated-tests']
    core.write(folder / 'provenance.json', {'arm': args.arm, 'bugs': ARMS[args.arm],
        'budget_seconds': budget, 'jar_sha256': core.sha(args.jar),
        'contract_sha256': core.sha(root / 'openapi.json'), 'official_score': 'UNDETERMINED',
        'scope': 'Campaign-global diagnostic; generated tests require individual reset replay',
        'native_result_required': True})
    with core.Service(root, folder, ARMS[args.arm]):
        core.call('http://127.0.0.1:23243/__campaign__/case', {'case': 'campaign-global-diagnostic'})
        result = core.command(command, folder / 'search.log', timeout=budget + 300)
    core.write(folder / 'execution.json', result)
    core.evaluate(folder)
    print('EVOMASTER_REVIEW ' + str(folder))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('replay', 'evomaster'))
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--java', default='java')
    parser.add_argument('--arm', choices=ARMS)
    parser.add_argument('--jar', type=Path)
    args = parser.parse_args()
    if args.mode == 'replay':
        replay(args)
    else:
        if not args.arm or not args.jar:
            parser.error('evomaster requires --arm and --jar')
        evomaster(args)
