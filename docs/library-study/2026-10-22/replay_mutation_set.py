"""Replay a frozen accepted v004-compatible sample with an explicit mutation set.

Invoke from a library-demo checkout. No generation or silent path rebinding.
This documentation helper delegates to the existing v004 replay implementation.
"""
import argparse
import json
from pathlib import Path
import sys
from datetime import datetime


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-campaign',type=Path,required=True)
    p.add_argument('--bugs',required=True,choices=['1','2','3','4','5','1,2,3,4,5'])
    p.add_argument('--java',default='java')
    a=p.parse_args();repo=Path.cwd()
    sys.path.insert(0,str(repo/'library/ess-experiment/campaign-v005'))
    from split_v005 import inputs, core
    root=a.reference_campaign.resolve();jar,samples=inputs(root)
    manifest=json.loads((root/'sample_manifest.json').read_text())
    for item in manifest:
        path=root/item['source_file']
        if core.sha(path)!=item['source_sha256']:raise ValueError('Frozen sample hash mismatch: '+str(path))
    name='isolated-doc-v001-bugs-'+a.bugs.replace(',','-')+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    result=core.replay(a.java,jar,root,samples,len(samples),name,a.bugs)
    print('REPLAY_OUTPUT',root/name)
    print('Replay completion is not a unique-bug score. Inspect native and HTTP evidence.')
    return result


if __name__=='__main__':main()
