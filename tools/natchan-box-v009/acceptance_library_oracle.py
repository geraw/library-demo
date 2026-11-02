"""Acceptance only: compare independent verdict request IDs to the Library oracle.
The engine never receives the oracle's output or mutation labels. Repairs are
synthetic controls, not new SUT executions. Original files are never modified.
"""
import argparse,copy,hashlib,importlib.util,io,json
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from common import engine_hashes,write
from contract_context import derive
from traffic import exchanges
from judge import analyze

REASONS={'CREATED_RESOURCE_NOT_READABLE':'B1','DELETED_RESOURCE_STILL_READABLE':'B2','CONJUNCTIVE_FILTER_VIOLATION':'B4'}

def run(root,contract,oracle_path,output):
    if output.exists():raise ValueError('Use a new output directory')
    spec=importlib.util.spec_from_file_location('acceptance_reference_oracle',oracle_path)
    oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    cb=contract.read_bytes();context=derive(json.loads(cb),hashlib.sha256(cb).hexdigest());results=[]
    for path in sorted(root.rglob('http.jsonl')):
        raw=path.read_bytes();source_hash=hashlib.sha256(raw).hexdigest()
        physical=[json.loads(s) if s.strip() else None for s in raw.splitlines()]
        reference=oracle.evaluate([r for r in physical if r is not None])
        capture=json.loads((path.parent/'natchan-request.json').read_text())['evidence']['capture']
        rows=list(exchanges(path,'observer-tool-jsonl',source_hash,{}))
        def inspect(data):
            buf=io.StringIO();coverage=analyze(data,context,buf,capture=copy.deepcopy(capture))
            verdicts=[v for v in map(json.loads,buf.getvalue().splitlines()) if v['reason'] in REASONS and v['value'] in ('violation','policy_observation')]
            return coverage,verdicts
        coverage,verdicts=inspect(rows)
        expected={(v['bug'],v['request_id']) for v in reference['findings'] if v['bug'] in REASONS.values()}
        actual={(REASONS[v['reason']],physical[v['evidence'][0]['line_1based']-1]['request_id']) for v in verdicts}
        if actual!=expected:raise AssertionError({'source':str(path),'missing':sorted(expected-actual),'extra':sorted(actual-expected)})
        repaired=copy.deepcopy(rows);by_line={r['source']['line_1based']:r for r in repaired}
        for v in verdicts:
            r=by_line[v['evidence'][0]['line_1based']]
            if REASONS[v['reason']]=='B1':r['status']=200
            elif REASONS[v['reason']]=='B2':r['status']=404
            else:
                # A synthetic empty filter response violates no returned-item predicate.
                r['response']=[]
        _,control=inspect(repaired)
        if control:raise AssertionError('Repaired control still has target findings')
        results.append({'source':str(path.relative_to(root)),'http_sha256':source_hash,'exchanges':coverage['exchanges'],
                        'oracle_request_ids':sorted(expected),'analyzer_request_ids':sorted(actual),
                        'exact_request_id_match':True,'finding_partitions':coverage['finding_partitions'],
                        'synthetic_repaired_control_target_findings':len(control)})
    if not results:raise ValueError('No original traces found')
    output.mkdir(parents=True)
    report={'status':'PASS','engine':engine_hashes(),'contract_sha256':hashlib.sha256(cb).hexdigest(),
            'oracle_sha256':hashlib.sha256(oracle_path.read_bytes()).hexdigest(),'new_SUT_requests':0,'resampled':False,
            'scope':'All supplied raw cells; exact B1/B2/B4 detection-request comparison, not all four configurations',
            'controls':'Synthetic corrected responses; not independent successful SUT runs','results':results}
    write(output/'acceptance.json',report)
    print('PASS',sum(len(x['analyzer_request_ids']) for x in results),'exact oracle request matches;',len(results),'cells and repaired controls')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs-root',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--oracle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.runs_root,a.contract,a.oracle,a.output)
