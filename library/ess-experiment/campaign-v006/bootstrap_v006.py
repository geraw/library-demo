"""User-local Windows tool installation for v006. No administrator or global PATH changes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import zipfile

EVO_VERSION = '6.2.0'
EVO_SHA = '93f9c4a0de88b01395d2a1009776aa739973e9f64343778d2fd49c212fd17915'
RESTLER_COMMIT = '6d984deedbc54aad957fa3da0c7e9e5df23a2aee'


def fetch(url, path, expected=None, algorithm='sha256'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def digest(p):
        h = hashlib.new(algorithm)
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
        return h.hexdigest()
    if path.is_file() and (not expected or digest(path).lower() == expected.lower()):
        return path
    print('INSTALL_DOWNLOAD ' + url, flush=True)
    part = path.with_suffix(path.suffix + '.part')
    with urlopen(Request(url, headers={'User-Agent': 'ISSTA-v006'}), timeout=120) as response, part.open('wb') as out:
        shutil.copyfileobj(response, out)
    if expected and digest(part).lower() != expected.lower():
        part.unlink()
        raise RuntimeError('Download digest mismatch: ' + url)
    part.replace(path)
    return path


def unpack(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            dest = (target / member.filename).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise RuntimeError('Archive path escapes installation folder')
        z.extractall(target)


def execute(args, folder, name, timeout=1200):
    print('INSTALL_STEP ' + name + ' LOG=' + str(folder / (name + '.log')), flush=True)
    with (folder / (name + '.log')).open('w') as out:
        proc = subprocess.Popen([str(x) for x in args], stdout=out, stderr=subprocess.STDOUT)
        started = time.monotonic()
        while proc.poll() is None:
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print('INSTALL_PROGRESS ' + name + ' seconds=' + str(int(time.monotonic()-started)), flush=True)
            if time.monotonic()-started > timeout and proc.poll() is None:
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                proc.wait(timeout=15)
                raise RuntimeError('Install timeout; inspect ' + str(folder / (name + '.log')))
        if proc.returncode:
            raise RuntimeError('Install step failed; inspect ' + str(folder / (name + '.log')))


def activate(home):
    manifest = home / 'manifest.json'
    if not manifest.is_file(): return
    data = json.loads(manifest.read_text())
    paths = [data.get('python_bin'), data.get('dotnet_bin'), data.get('java_bin')]
    os.environ['PATH'] = os.pathsep.join([p for p in paths if p and Path(p).is_dir()] + [os.environ.get('PATH','')])
    if data.get('dotnet_bin'):
        os.environ['DOTNET_ROOT'] = data['dotnet_bin']
        os.environ['DOTNET_MULTILEVEL_LOOKUP'] = '0'


def install(home, tools):
    if os.name != 'nt': raise RuntimeError('Automatic local installation currently supports Windows x64 only')
    import platform
    if platform.machine().lower() not in ('amd64','x86_64'):
        raise RuntimeError('Automatic tool installation requires Windows x64')
    home.mkdir(parents=True, exist_ok=True)
    activate(home)
    manifest = home / 'manifest.json'
    data = json.loads(manifest.read_text()) if manifest.exists() else {}
    def save(): manifest.write_text(json.dumps(data, indent=2))
    if 'evo' in tools:
        jar = home / ('evomaster-' + EVO_VERSION) / 'evomaster.jar'
        fetch('https://github.com/WebFuzzing/EvoMaster/releases/download/v'+EVO_VERSION+'/evomaster.jar', jar, EVO_SHA)
        data.update(evo=str(jar), evomaster_version=EVO_VERSION, evomaster_sha256=EVO_SHA)
        save()
    if 'restler' in tools:
        # RESTler publishes source, so build the pinned official revision locally.
        dotnet = home / 'dotnet'
        if not (dotnet / 'dotnet.exe').is_file():
            metadata_file = fetch('https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json', home / 'dotnet-releases.json')
            metadata = json.loads(metadata_file.read_text(encoding='utf-8-sig'))
            sdk = next(r['sdk'] for r in metadata['releases'] if r.get('sdk',{}).get('version') == metadata['latest-sdk'])
            package = next(f for f in sdk['files'] if f['rid']=='win-x64' and f['name'].endswith('.zip'))
            archive = fetch(package['url'], home / 'dotnet-sdk.zip', package['hash'], 'sha512')
            unpack(archive, dotnet)
            data['dotnet_sdk_version'] = sdk['version']
        data['dotnet_bin'] = str(dotnet)
        save(); activate(home)
        env = home / 'restler-python'
        python = env / 'Scripts/python.exe'
        if not python.is_file(): execute([sys.executable,'-m','venv',env],home,'python-venv')
        data['python_bin'] = str(python.parent)
        save(); activate(home)
        source = home / ('restler-fuzzer-' + RESTLER_COMMIT)
        if not (source / 'build-restler.py').is_file():
            archive = fetch('https://github.com/microsoft/restler-fuzzer/archive/'+RESTLER_COMMIT+'.zip',home / ('restler-'+RESTLER_COMMIT+'.zip'))
            unpack(archive,home)
        execute([python,'-m','pip','install','setuptools<81','-r',source/'restler/requirements.txt'],home,'python-dependencies')
        output = home / ('restler-bin-' + RESTLER_COMMIT[:12])
        dll = output / 'restler/Restler.dll'
        ready = output / 'v006-build-complete.json'
        if not dll.is_file() or not ready.is_file():
            execute([python,source/'build-restler.py','--dest_dir',output,'--python_path',python],home,'restler-build')
        if not dll.is_file(): raise RuntimeError('RESTler build did not produce ' + str(dll))
        ready.write_text(json.dumps({'commit': RESTLER_COMMIT}))
        data.update(restler=str(dll), restler_commit=RESTLER_COMMIT,
                    restler_sha256=hashlib.sha256(dll.read_bytes()).hexdigest())
        # Capture resolved Python package versions for reproducibility.
        execute([python,'-m','pip','freeze'],home,'python-freeze')
        save()
    if not shutil.which('java'):
        # Portable JDK 21, obtained from the official Adoptium API; verify its SHA256.
        meta = fetch('https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows',home/'java-releases.json')
        package = json.loads(meta.read_text())[0]['binary']['package']
        archive = fetch(package['link'],home/'jdk21.zip',package['checksum'])
        unpack(archive,home/'java')
        java = next((home/'java').rglob('java.exe'))
        data['java_bin'] = str(java.parent)
        data['java_sha256'] = package['checksum']
        save(); activate(home)
    print('INSTALL_READY ' + str(manifest),flush=True)
    return data
