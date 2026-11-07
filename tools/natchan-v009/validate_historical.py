"""Validate the frozen 18-journal cohort; compare independent expected counts."""
import argparse
import hashlib
import json
from pathlib import Path
from historical import analyze,ROOT
EXPECTED={'GEN-REFERENCE-PROJECTION-DIFFERENCE':174,'GEN-STATUS-PAIR-DIFFERENCE':28,'GEN-SERVER_ERROR':23}
def validate(manifest,root):
    paths=[]
    for item in manifest['inputs']:
        p=root/item['path']
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Changed input '+item['path'])
        paths.append(p)
    r=analyze(paths)
    if r['distinct_journals']!=18 or r['pattern_occurrences']!=EXPECTED:raise ValueError('Historical parity mismatch')
    if any(a.get('known_bugs') for a in r['assessments']):raise ValueError('Unqualified historical evidence became named known bug')
    return dict(validation='PASS',distinct_journals=18,pattern_occurrences=r['pattern_occurrences'],new_sut_requests=0,
                note='Frozen descriptive evidence baseline, not full semantic or named-bug confirmation')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    print(json.dumps(validate(json.loads((ROOT/'reviews/historical-summary.json').read_text()),a.root),indent=2))
