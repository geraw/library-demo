"""Build the compact ZIP expected by mutants-v002/replay.py from Git JSONL files."""
import argparse,hashlib,json,zipfile
from pathlib import Path

def build(output):
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if output.exists():raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
        for item in manifest['cases']:
            path=root/(item['case']+'.jsonl');content=path.read_bytes()
            # Normalize checkout line endings before applying repository checksums.
            content=content.replace(b'\r\n',b'\n')
            if hashlib.sha256(content).hexdigest()!=item['sha256']:raise ValueError(f'Changed scenario: {path}')
            z.writestr(item['case']+'/original/http.jsonl',content)
        z.writestr('clean-scenarios-manifest.json',json.dumps(manifest,indent=2))
    print('REPLAY_INPUT',output)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);build(p.parse_args().output)
