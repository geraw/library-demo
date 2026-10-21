"""Export all pinned v004/v005 evidence from the local study Git checkout."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v004'))
from prepare_evidence import prepare


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();base=json.loads((ROOT.parent/'natchan-v004/manifest-tse-v004.json').read_text())
    extra=json.loads((ROOT/'manifest-coverage-v005.json').read_text())
    paths={}
    for r in base['runs']:
        paths[r['path']]={k:r[k] for k in ['path','sha256','git_blob_sha']}
        if r.get('contract'):paths[r['contract']]={'path':r['contract'],'sha256':r['contract_sha256'],'git_blob_sha':r['contract_git_blob_sha']}
    for r in extra['inputs']:paths[r['path']]=r
    with tempfile.TemporaryDirectory() as temp:
        manifest=Path(temp)/'manifest.json'
        manifest.write_text(json.dumps({'commit':extra['commit'],'runs':list(paths.values())}),encoding='utf-8')
        prepare(a.repo,manifest,a.destination)


if __name__=='__main__':main()
