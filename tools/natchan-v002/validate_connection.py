"""Offline parity check: gateway output versus preserved checker and archived diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
from evidence import ingest
from analyze import analyze_envelope
from library_bridge import checker


def validate(archive):
    result=analyze_envelope(ingest(archive,library=True),'control')
    summary=dict(source=result['evidence']['source'],analysis_status=result['status'],arms={},
                 control_comparison=result['control_comparison'],summary=result['summary'])
    if result['status']!='complete': raise ValueError('Incomplete analysis')
    with zipfile.ZipFile(archive) as z,tempfile.TemporaryDirectory() as directory:
        inputs=json.loads(z.read('input_hashes.json'))
        for name,digest in inputs.items():
            if hashlib.sha256(z.read(name.replace('\\','/'))).hexdigest()!=digest:
                raise ValueError('Input hash mismatch: '+name)
        summary['input_manifest_verified']=True
        stored=json.loads(z.read('results.json'))
        for run in result['runs']:
            name=run['id'];path=Path(directory)/(name+'.jsonl');path.write_bytes(z.read(name+'/http.jsonl'))
            legacy=checker().evaluate_trace(path,'library-issta-v006')
            connected=dict(run['semantic'])
            for key in ['adapter_trace_sha256','adapter_note','evaluator_source']: connected.pop(key)
            exact=connected==legacy
            candidates={r['case']:sorted(r['result']['candidate_classes']) for r in connected['cases'] if r['evaluable'] and r['result']['candidate_classes']}
            archived={k:sorted(v) for k,v in stored[name]['observer']['clean_candidate_cases'].items()}
            native=[json.loads(line) for line in z.read(name+'/native.jsonl').splitlines()]
            failed=[str(r['case']) for r in native if not r['native_pass']]
            native_same=run['native'].get('failed_cases')==failed
            summary['arms'][name]=dict(case_count=connected['case_count'],evaluable_case_count=connected['evaluable_case_count'],
                exact_legacy_report_parity=exact,archived_candidate_cases_parity=candidates==archived,
                native_failed_cases_parity=native_same,native_failed_cases=failed,
                candidate_case_count=len(candidates),external_evaluator=connected['external_evaluator'])
            if not exact or candidates!=archived or not native_same: raise ValueError('Parity mismatch: '+name)
    summary['validation']='PASS'
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output exists')
    result=validate(args.archive)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as output: json.dump(result,output,indent=2);output.write('\n')
    print('NATCHAN_CONNECTION_PARITY_PASS '+str(args.output.resolve()))
