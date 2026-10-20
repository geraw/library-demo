"""Sequential all-mutant pilot. Native findings and observer diagnostics stay separate."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import secrets
import subprocess
import sys
import time
import traceback
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap_v006 as bootstrap

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


def fixed_drives():
    """Local fixed disks only; do not probe network shares or removable media."""
    if os.name != 'nt':
        return []
    import ctypes
    api = ctypes.windll.kernel32
    mask = api.GetLogicalDrives()
    return [Path(chr(65 + i) + ':/') for i in range(26)
            if mask & (1 << i) and api.GetDriveTypeW(chr(65 + i) + ':\\') == 3]


def scan_tools(root, missing, deep=False):
    found = {'evo': [], 'restler': []}
    skip = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '$recycle.bin',
            'system volume information', 'windows', 'winsxs', 'state', 'volumes'}
    if not root.is_dir():
        return found
    print('DISCOVERY_SCAN ' + str(root), flush=True)
    last = time.monotonic()
    for directory, dirs, files in os.walk(root, followlinks=False):
        path = Path(directory)
        dirs[:] = sorted(d for d in dirs if d.lower() not in skip
                         and not (path / d).is_symlink()
                         and not (hasattr(os.path, 'isjunction') and os.path.isjunction(path / d)))
        if not deep and len(path.relative_to(root).parts) >= 12:
            dirs[:] = []
        for name in files:
            low = name.lower()
            if 'evo' in missing and low.endswith('.jar') and 'evomaster' in low and not any(x in low for x in ('sources', 'javadoc')):
                found['evo'].append(path / name)
            if 'restler' in missing and low in ('restler.exe', 'restler.dll'):
                found['restler'].append(path / name)
        if all(found[key] for key in missing):
            break
        if time.monotonic() - last > 5:
            print('DISCOVERY_PROGRESS ' + str(path), flush=True)
            last = time.monotonic()
    return found


def managed_home():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ISSTA-tools-v006'


def find_tools(repo, evo, restler):
    explicit = {'evo': evo or os.environ.get('EVOMASTER_JAR'),
                'restler': restler or os.environ.get('RESTLER_EXE') or os.environ.get('RESTLER_DLL')}
    home = managed_home()
    bootstrap.activate(home)
    manifest = home / 'manifest.json'
    managed = json.loads(manifest.read_text()) if manifest.is_file() else {}
    found = {'evo': [], 'restler': []}
    for key, value in explicit.items():
        if not value and managed.get(key) and Path(managed[key]).is_file():
            value = managed[key]
        if not value:
            continue
        path = Path(value).expanduser().resolve()
        if path.is_dir():
            found[key] = scan_tools(path, {key}, deep=True)[key]
        elif path.is_file():
            found[key] = [path]
        if not found[key]:
            raise RuntimeError('No tool found at explicit ' + key + ' path: ' + str(path))
    for name in ('Restler.exe', 'restler.exe', 'Restler.dll'):
        if not found['restler']:
            hit = shutil.which(name)
            if hit:
                found['restler'] = [Path(hit).resolve()]
    roots = [repo, repo.parent, Path.home() / 'Downloads', Path.home() / 'tools',
             Path.home() / 'AppData/Local/Programs']
    if os.name == 'nt':
        roots += [Path(p) for p in ('C:/tools', 'D:/tools', 'C:/RESTler', 'D:/RESTler',
                                   'C:/work', 'D:/work', 'C:/Program Files', 'C:/Program Files (x86)')]
    checked = []
    disks = fixed_drives()
    for root in roots + disks:
        missing = {key for key in found if not found[key]}
        if not missing:
            break
        if str(root).lower() in checked:
            continue
        checked.append(str(root).lower())
        hits = scan_tools(root, missing, deep=root in disks)
        for key in missing:
            found[key].extend(hits[key])
    missing = {key for key in found if not found[key]}
    if missing:
        installed = bootstrap.install(home, missing)
        for key in missing:
            found[key] = [Path(installed[key])]
    for key in found:
        choices = sorted(set(p.resolve() for p in found[key]), key=lambda p: (p.suffix.lower() != '.exe', str(p)))
        if key == 'restler':
            exe_dirs = {str(p.parent).lower() for p in choices if p.suffix.lower() == '.exe'}
            choices = [p for p in choices if p.suffix.lower() != '.dll' or str(p.parent).lower() not in exe_dirs]
        option = '-EvoMasterJar' if key == 'evo' else '-RestlerPath'
        if len(choices) != 1:
            raise RuntimeError('Tool discovery: ' + key + '. Candidates: ' +
                               (', '.join(map(str, choices)) or 'NONE') +
                               '. Use PowerShell parameter ' + option + ' with the installed binary or folder. '
                               'Searched: ' + ', '.join(checked) +
                               '. No search was started; no runtime budget was used.')
        found[key] = choices[0]
        print('DISCOVERY_FOUND ' + key.upper() + ' ' + str(choices[0]), flush=True)
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
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / 'observed_server_v006.py'),
            '--sut', str(self.root / 'sut_buggy_issta.py'), '--bugs', self.bugs,
            '--log', str(self.folder / 'http.jsonl')], stdout=self.output, stderr=subprocess.STDOUT,
            env=environment)
        try:
            for _ in range(100):
                if self.proc.poll() is not None:
                    raise RuntimeError('Managed server failed: inspect server.log')
                try:
                    health = core.call('http://127.0.0.1:23243/__campaign__/health')
                    # Windows venv python.exe can be a redirector process: the HTTP
                    # worker's PID is not necessarily Popen.pid. Authenticate ownership.
                    if health.get('service_token') != self.token:
                        raise RuntimeError('Unexpected listening process')
                    health.pop('service_token', None)
                    health['launcher_pid'] = self.proc.pid
                    core.write(self.folder / 'server_identity.json', health)
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
                core.call('http://127.0.0.1:23243/__campaign__/shutdown', {'token': self.token})
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



def main(args):
    root = args.campaign.resolve()
    repo = Path(__file__).resolve().parents[3]
    for name in ('openapi.json', 'sut_buggy_issta.py'):
        if not (root / name).is_file():
            raise RuntimeError('Missing campaign input: ' + str(root / name))
    previous = getattr(args, 'previous_pilot', None)
    if previous:
        provenance = json.loads((previous / 'provenance.json').read_text())
        for name, key in [('openapi.json', 'contract_sha256'), ('sut_buggy_issta.py', 'sut_sha256')]:
            if core.sha(root / name) != provenance[key]:
                raise RuntimeError('Campaign input differs from previous pilot: ' + name)
        if not args.evomaster_jar:
            args.evomaster_jar = Path(provenance['evomaster_jar'])
        if not args.restler:
            args.restler = Path(provenance['restler'])
    selected = ['restler', 'evomaster'] if getattr(args, 'tools', 'both') == 'both' else [args.tools]
    if getattr(args, 'install_local_tools', False):
        installed = bootstrap.install(managed_home(), {'evo', 'restler'})
        args.evomaster_jar, args.restler = Path(installed['evo']), Path(installed['restler'])
    evo, restler = find_tools(repo, args.evomaster_jar, args.restler)
    java = shutil.which('java')
    if not java:
        bootstrap.install(managed_home(), set())
        java = shutil.which('java')
    if not java:
        raise RuntimeError('Local Java installation did not produce an executable')
    driver = [restler] if restler.suffix.lower() == '.exe' else [shutil.which('dotnet'), restler]
    if not driver[0]:
        raise RuntimeError('dotnet is required for Restler.dll')
    output = root / ('baselines-all-v006-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    output.mkdir()
    results = {}
    try:
        preflight = output / 'preflight'
        preflight.mkdir()
        install_manifest = managed_home() / 'manifest.json'
        if install_manifest.is_file():
            shutil.copy2(install_manifest, preflight / 'installation-manifest.json')
        help_result = run([java, '-jar', evo, '--help'], preflight, 'help', 60)
        if help_result['exit_code'] or help_result['watchdog_timeout']:
            raise RuntimeError('EvoMaster help failed: ' + str(preflight / 'help.log'))
        evocommand = evo_command(java, evo, (preflight / 'help.log').read_text(errors='replace'),
                                root / 'openapi.json', output / 'evomaster/generated-tests')
        core.write(output / 'provenance.json', dict(bugs=BUGS, search_seconds_per_tool=SECONDS,
            order=selected, observer_version='v006-fixed-http-body',
            internal_transport='Flask WSGI client; external tool HTTP unchanged', previous_pilot=str(previous) if previous else None, evomaster_jar=str(evo), restler=str(restler),
            evomaster_sha256=core.sha(evo), restler_sha256=core.sha(restler),
            contract_sha256=core.sha(root / 'openapi.json'), sut_sha256=core.sha(root / 'sut_buggy_issta.py'),
            scope='Pilot; campaign-global observer diagnostics, not sequence-local official scores',
            native_detection='Inspect native reports separately; observer findings are not native tool findings',
            stopping='Observer never stops tools on a semantic finding; tools retain their native behavior',
            preparation='Compilation, startup and output finalization are outside the 600-second engine budget'))
        for tool in selected:
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
                with Service(root, folder, BUGS):
                    core.call('http://127.0.0.1:23243/__campaign__/case', {'case': tool + '-pilot-global'})
                    result = run(command, folder, 'search', 690)
                summary = core.evaluate(folder)
                summary.pop('semantic_candidates', None)
                with (folder / 'http.jsonl').open(encoding='utf-8') as log:
                    observer_errors = sum(json.loads(line).get('role') == 'observer_error' for line in log)
                summary['observer_error_count'] = observer_errors
                result['observation'] = summary
                result['status'] = 'WATCHDOG_TIMEOUT' if result['watchdog_timeout'] else 'TOOL_EXIT_NONZERO' if result['exit_code'] else 'FINISHED'
                if observer_errors:
                    result['status'] = 'OBSERVER_ERROR'
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
    if len(results) != len(selected) or any(v['status'] != 'FINISHED' for v in results.values()):
        raise RuntimeError('Pilot incomplete or tool returned nonzero; results preserved in REVIEW_ZIP')
    print('PILOT_V006_COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--evomaster-jar', type=Path)
    parser.add_argument('--restler', type=Path)
    parser.add_argument('--install-local-tools', action='store_true')
    parser.add_argument('--tools', choices=['both', 'restler', 'evomaster'], default='both')
    parser.add_argument('--previous-pilot', type=Path)
    main(parser.parse_args())
