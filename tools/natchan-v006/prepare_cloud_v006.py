"""Export immutable original g009 cloud evidence from the local study repository."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v004'))
from prepare_evidence import prepare

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();m=json.loads((ROOT/'manifest-cloud-v006.json').read_text())
    with tempfile.TemporaryDirectory() as temp:
        manifest=Path(temp)/'export.json';manifest.write_text(json.dumps({'commit':m['commit'],'runs':m['inputs']}),encoding='utf-8')
        prepare(a.repo,manifest,a.destination)
