"""Sequential all-mutant pilot. Native findings and observer diagnostics stay separate."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'campaign-v004'))
import campaign_v004 as core

BUGS = '1,2,3,4,5'
SECONDS = 600


def run(command, folder, name, timeout):
    started = time.perf_counter()
    with (folder / (name + '.log')).open('w', encoding='utf-8') as stream:
        stream.write('COMMAND ' + json.dumps([str(x) for x in command]) + '\n')
        stream.flush()
        proc = subprocess.Popen([str(x) for x in command], cwd=folder,
                                stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=os.name != 'nt')
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=15)
        result = dict(command=[str(x) for x in command], exit_code=proc.returncode,
                      watchdog_timeout=timed_out, wall_seconds=time.perf_counter() - started)
    core.write(folder / (name + '-execution.json'), result)
    return result


def find_tools(repo, evo, restler):
    explicit = {'evo': evo or os.environ.get('EVOMASTER_JAR'),
                'restler': restler or os.environ.get('RESTLER_EXE') or os.environ.get('RESTLER_DLL')}
    for key, value in explicit.items():
        if value and not Path(value).is_file():
            raise RuntimeError(key + ' path does not exist: ' + str(value))
    found = {key: [Path(value).resolve()] if value else [] for key, value in explicit.items()}
    roots = [repo, repo.parent, Path.home() / 'Downloads', Path.home() / 'tools']
    if os.name == 'nt':
        roots += [Path(p) for p in ('C:/tools', 'D:/tools', 'C:/RESTler', 'D:/RESTler',
                                   'C:/work/temp', 'C:/Program Files/EvoMaster')]
    seen = set()
    skip = {'.git', '.venv', 'node_modules', '__pycache__', 'runs', 'state', 'data', 'postgres', 'volumes'}
    for root in roots:
        if all(found.values()):
            break
        if not root.is_dir():
            continue
        count = 0
        for directory, dirs, files in os.walk(root):
            path = Path(directory)
            depth = len(path.relative_to(root).parts)
            dirs[:] = sorted(d for d in dirs if d.lower() not in skip) if depth < 6 else []
            if str(path).lower() in seen:
                dirs[:] = []
                continue
            seen.add(str(path).lower())
            count += 1
            if count > 15000:
                break
            for name in files:
                low = name.lower()
                if not explicit['evo'] and low.endswith('.jar') and 'evomaster' in low and 'source' not in low and 'javadoc' not in low:
                    found['evo'].append(path / name)
                if not explicit['restler'] and low in ('restler.exe', 'restler.dll'):
                    found['restler'].append(path / name)
    for key in found:
        # The exe and dll from the same RESTler build count as one installation.
        choices = sorted(set(p.resolve() for p in found[key]), key=lambda p: (p.suffix != '.exe', str(p)))
        if key == 'restler':
            choices = [p for p in choices if p.suffix.lower() != '.dll' or not p.with_suffix('.exe').exists()]
        if len(choices) != 1:
            raise RuntimeError('Specify --' + ('evomaster-jar' if key == 'evo' else 'restler') +
                               '; found: ' + ', '.join(map(str, choices)))
        found[key] = choices[0]
    return found['evo'], found['restler']


def evo_command(java, jar, help_text, schema, output):
    schema_flag = '--schema' if re.search(r'--schema\b', help_text) else '--bbSwaggerUrl' if '--bbSwaggerUrl' in help_text else None
    base_flag = '--base' if re.search(r'--base\b', help_text) else '--bbTargetUrl' if '--bbTargetUrl' in help_text else None
    if not schema_flag or not base_flag or '--maxTime' not in help_text:
        raise RuntimeError('Unsupported EvoMaster options; inspect preflight/help.log')
    return [java, '-jar', jar, '--blackBox', 'true', schema_flag, schema,
            base_flag, 'http://127.0.0.1:23243', '--maxTime', '600s',
            '--seed', '1', '--outputFolder', output]


def restler_settings():
    return dict(target_ip='127.0.0.1', target_port=23243, host='127.0.0.1:23243',
                no_ssl=True, time_budget=SECONDS / 3600, fuzzing_mode='bfs-cheap',
                random_seed=1, garbage_collector_cleanup_time=10,
                max_request_execution_time=10, max_async_resource_creation_time=1)


def main(args):
    root = args.campaign.resolve()
    repo = Path(__file__).resolve().parents[3]
    for name in ('openapi.json', 'sut_buggy_issta.py'):
        if not (root / name).is_file():
            raise RuntimeError('Missing campaign input: ' + str(root / name))
    evo, restler = find_tools(repo, args.evomaster_jar, args.restler)
    java = shutil.which('java')
    if not java:
        raise RuntimeError('Java is not on PATH')
    driver = [restler] if restler.suffix.lower() == '.exe' else [shutil.which('dotnet'), restler]
    if not driver[0]:
        raise RuntimeError('dotnet is required for Restler.dll')
    output = root / ('baselines-all-v006-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    output.mkdir()
    results = {}
    try:
        preflight = output / 'preflight'
        preflight.mkdir()
        help_result = run([java, '-jar', evo, '--help'], preflight, 'help', 60)
        if help_result['exit_code'] or help_result['watchdog_timeout']:
            raise RuntimeError('EvoMaster help failed: ' + str(preflight / 'help.log'))
        evocommand = evo_command(java, evo, (preflight / 'help.log').read_text(errors='replace'),
                                root / 'openapi.json', output / 'evomaster/generated-tests')
        core.write(output / 'provenance.json', dict(bugs=BUGS, search_seconds_per_tool=SECONDS,
            order=['restler', 'evomaster'], evomaster_jar=str(evo), restler=str(restler),
            evomaster_sha256=core.sha(evo), restler_sha256=core.sha(restler),
            contract_sha256=core.sha(root / 'openapi.json'), sut_sha256=core.sha(root / 'sut_buggy_issta.py'),
            scope='Pilot; campaign-global observer diagnostics, not sequence-local official scores',
            native_detection='Inspect native reports separately; observer findings are not native tool findings',
            stopping='Observer never stops tools on a semantic finding; tools retain their native behavior',
            preparation='Compilation, startup and output finalization are outside the 600-second engine budget'))
        for tool in ('restler', 'evomaster'):
            folder = output / tool
            folder.mkdir()
            print('START ' + tool.upper() + ' ALL_BUGS SEARCH_SECONDS=600', flush=True)
            try:
                if tool == 'restler':
                    compiled = run(driver + ['compile', '--api_spec', root / 'openapi.json'], folder, 'compile', 180)
                    grammar, dictionary = folder / 'Compile/grammar.py', folder / 'Compile/dict.json'
                    if compiled['exit_code'] or compiled['watchdog_timeout'] or not grammar.is_file() or not dictionary.is_file():
                        raise RuntimeError('RESTler compile failed; inspect compile.log')
                    settings = restler_settings()
                    grammar_json = folder / 'Compile/grammar.json'
                    if grammar_json.is_file():
                        settings['grammar_schema'] = str(grammar_json)
                    core.write(folder / 'settings.json', settings)
                    command = driver + ['fuzz', '--grammar_file', grammar, '--dictionary_file', dictionary,
                                        '--settings', folder / 'settings.json', '--no_ssl']
                else:
                    command = evocommand
                with core.Service(root, folder, BUGS):
                    core.call('http://127.0.0.1:23243/__campaign__/case', {'case': tool + '-pilot-global'})
                    result = run(command, folder, 'search', 690)
                summary = core.evaluate(folder)
                summary.pop('semantic_candidates', None)
                result['observation'] = summary
                result['status'] = 'WATCHDOG_TIMEOUT' if result['watchdog_timeout'] else 'TOOL_EXIT_NONZERO' if result['exit_code'] else 'FINISHED'
                results[tool] = result
            except Exception as exc:
                results[tool] = dict(status='HARNESS_ERROR', error=str(exc))
                (folder / 'error.log').write_text(traceback.format_exc())
            core.write(output / 'summary.json', results)
            print('END ' + tool.upper() + ' ' + results[tool]['status'], flush=True)
    finally:
        archive = output.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for path in output.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts:
                    z.write(path, path.relative_to(output))
        print('REVIEW_ZIP ' + str(archive), flush=True)
    if len(results) != 2 or any(v['status'] != 'FINISHED' for v in results.values()):
        raise RuntimeError('Pilot incomplete or tool returned nonzero; results preserved in REVIEW_ZIP')
    print('PILOT_V006_COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--evomaster-jar', type=Path)
    parser.add_argument('--restler', type=Path)
    main(parser.parse_args())
