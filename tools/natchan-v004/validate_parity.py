"""Check predeclared manual expectations without using manual labels as detector inputs."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def validate(report, expectations):
    checks=[]
    def check(name,actual,expected):
        checks.append(dict(name=name,actual=actual,expected=expected,passed=actual==expected))
    for item in expectations['expectations']:
        scope,metric=item['scope'],item['metric']
        runs=[r for r in report['runs'] if r['id'].startswith(scope)]
        if metric=='http_5xx':actual=sum(r['http_5xx'] for r in runs if r['http_5xx'] is not None)
        elif metric=='original_partial_oracles':
            # Join retained archive members to their run by archive directory/name.
            actual=sum(o['category']=='atomicity-check' and o['payload'].get('verdict')=='partial'
                       for o in report['original_oracles'] if scope in o['source']['file'])
        elif metric=='adjacency_5xx':
            probes=[o for o in report['observations'] if o['run_id'].startswith(scope) and o.get('action')=='adjacency_probe']
            actual=sum(type(o['status']) is int and 500<=o['status']<=599 for o in probes)
            check(scope+' eligible adjacency probes',len(probes),item['eligible'])
        elif metric=='GIT-C8_runs':
            actual=len({r['run_id'] for r in report['assessments'] if r.get('catalog_id')=='GIT-C8' and r['run_id'].startswith(scope)})
        elif metric=='VIK-F06_occurrences':
            actual=sum(r.get('catalog_id')=='VIK-F06' and r['run_id'].startswith(scope) for r in report['assessments'] if r.get('status')=='matched')
        else:raise ValueError('Unknown expectation metric '+metric)
        check(scope+' '+metric,actual,item['expected'])
    for product,ids in expectations['required_known_signatures'].items():
        versions=['2.6.0','2.7.0'] if product=='vikunja' else ['28.1.0']
        for version in versions:
            for id in ids:
                found=any(r.get('catalog_id')==id and r.get('product')==product and r.get('product_version')==version for r in report['assessments'])
                check(product+' '+version+' '+id,found,True)
    return {'schema_version':'natchan-parity/1','status':'PASS_FOR_SCOPED_EXPECTATIONS' if all(c['passed'] for c in checks) else 'MISMATCH',
            'checks':checks,'unresolved':expectations['expected_unresolved'],
            'scope':'Historical evidence signature parity, not independent re-confirmation of every historical root cause'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--expectations',type=Path,default=ROOT/'expectations-tse-v004.json')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    result=validate(json.loads(a.report.read_text(encoding='utf-8-sig')),json.loads(a.expectations.read_text(encoding='utf-8-sig')))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('NATCHAN_PARITY '+result['status'])
    raise SystemExit(0 if result['status']=='PASS_FOR_SCOPED_EXPECTATIONS' else 1)
