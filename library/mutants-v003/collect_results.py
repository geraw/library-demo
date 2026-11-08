"""Collect one completed/stopped v003 run without modifying it."""
import argparse,hashlib,json,zipfile
from pathlib import Path
from datetime import datetime

def collect(root):
    if not root.is_dir() or not (root/'summary.json').exists():raise ValueError('Pass a result directory containing summary.json')
    target=root.parent/(root.name+'-analysis-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip')
    inventory=[]
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix in ['.json','.jsonl','.log']:
                data=p.read_bytes();name=p.relative_to(root).as_posix();z.writestr(name,data)
                inventory.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        z.writestr('collection-manifest.json',json.dumps({'source':str(root),'files':inventory},indent=2))
    with zipfile.ZipFile(target) as z:
        if z.testzip():raise RuntimeError('Archive verification failed')
    print('UPLOAD_THIS',target)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);collect(p.parse_args().run)
