"""Validate known findings, partial-evidence boundaries and v004 parity."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v004'))
from validate_parity import validate as validate_v004


def validate(report):
    checks=[]
    def check(name,actual,expected):checks.append(dict(name=name,actual=actual,expected=expected,passed=actual==expected))
    ids=set(report['known_signature_occurrences'])
    for id in ['VIK-F01','VIK-F02','VIK-F03','VIK-F04','VIK-F05','VIK-F06','GIT-C1','GIT-C2','GIT-C3','GIT-C8']:
        check(id+' has original-evidence match',id in ids,True)
    check('F03 original 2.6.0 overlength/readback occurrences',report['known_signature_occurrences'].get('VIK-F03'),6)
    check('F01 uniquely linked lock responses',report['known_signature_occurrences'].get('VIK-F01'),8)
    counts=dict(Counter(x['id'] for x in report['candidate_known_signatures']))
    check('Cloud symptom-only occurrences',counts,{'GIT-C4':10,'GIT-C5':2,'GIT-C6':3,'GIT-C7':5})
    check('Partial cloud evidence never becomes a full signature',any(id in ids for id in ['GIT-C4','GIT-C5','GIT-C6','GIT-C7']),False)
    check('All trap provider families registered',len(report['provider_audit']['families']),11)
    old=validate_v004(report,json.loads((ROOT.parent/'natchan-v004/expectations-tse-v004.json').read_text()))
    check('v004 scoped historical parity retained',old['status'],'PASS_FOR_SCOPED_EXPECTATIONS')
    return {'status':'PASS_FOR_RECORDED_COVERAGE' if all(c['passed'] for c in checks) else 'MISMATCH','checks':checks,
            'baseline_checks':old['checks'],'not_claimed':['Complete C4-C7 confirmation without raw bodies/logs',
            'Independent ATOM snapshots where only field labels were retained','Causal timing/handler inference from a scoped lock join']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    result=validate(json.loads(a.report.read_text(encoding='utf-8-sig')))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('NATCHAN_COVERAGE_VALIDATION '+result['status']);raise SystemExit(0 if result['status']=='PASS_FOR_RECORDED_COVERAGE' else 1)
