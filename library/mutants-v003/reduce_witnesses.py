"""Greedy deletion reduction; not proof of global minimality.
A deletion is accepted only when original and baseline still reproduce every
retained expected response and the targeted mutant still differs.
"""
import json,logging,random,tempfile
from pathlib import Path
from verify import witness
from replay import replay
logging.disable(logging.CRITICAL)

def run():
    output={}
    with tempfile.TemporaryDirectory() as directory:
        trace=Path(directory)/'trial.jsonl'
        for bug in ['B1','B2','B3','B4','B5','B6']:
            random.seed(42)
            steps=witness(bug,'original')
            rows=[dict(row,url='http://127.0.0.1'+row['path'],role='tool',order=i+1) for i,row in enumerate(steps)]
            def qualifies(candidate):
                try:
                    if any(replay(candidate,mode,trace,123)['status']!='PASS' for mode in ['original','baseline']):return False
                    return replay(candidate,bug,trace,123)['status']=='DIFFERENT'
                except (ValueError,KeyError,TypeError):return False
            if not qualifies(rows):raise AssertionError(bug)
            reduced=rows[:]
            changed=True
            while changed:
                changed=False
                for i in range(len(reduced)):
                    candidate=reduced[:i]+reduced[i+1:]
                    if qualifies(candidate):
                        reduced=candidate;changed=True;break
            output[bug]={'full_requests':len(rows),'reduced_requests':len(reduced),
                'reduction':'greedy deletion under retained-response equivalence; not globally minimal',
                'full_trace':rows,'reduced_trace':reduced}
    return output
if __name__=='__main__':print(json.dumps(run(),indent=2))
