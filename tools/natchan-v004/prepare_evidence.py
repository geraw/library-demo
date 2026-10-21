"""Export pinned Git blobs locally, preserving exact bytes and checking SHA256."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def prepare(repo, manifest_path, destination):
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8-sig'))
    if destination.exists():
        raise ValueError('Destination exists; use a new directory')
    paths={}
    for run in manifest['runs']:
        paths[run['path']]=(run['sha256'],run.get('git_blob_sha'))
        if 'contract' in run:
            paths[run['contract']]=(run['contract_sha256'],run.get('contract_git_blob_sha'))
    # Resolve the requested commit before creating outputs.
    subprocess.run(['git','-C',str(repo),'cat-file','-e',manifest['commit']+'^{commit}'],check=True)
    destination.mkdir(parents=True)
    receipts=[]
    for name,(expected,blob_sha) in sorted(paths.items()):
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe manifest path')
        result=subprocess.run(['git','-C',str(repo),'show',manifest['commit']+':'+name],check=True,stdout=subprocess.PIPE)
        raw=result.stdout
        sha=hashlib.sha256(raw).hexdigest()
        git_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if sha!=expected or (blob_sha and git_sha!=blob_sha):
            raise ValueError('Pinned input hash mismatch: '+name)
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        receipts.append({'path':name,'sha256':sha,'git_blob_sha':git_sha})
    (destination/'export-receipt.json').write_text(json.dumps({'commit':manifest['commit'],'files':receipts},indent=2)+'\n',encoding='utf-8')
    print('NATCHAN_EVIDENCE_READY '+str(destination.resolve()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=Path(__file__).with_name('manifest-tse-v004.json'))
    p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();prepare(a.repo,a.manifest,a.destination)
