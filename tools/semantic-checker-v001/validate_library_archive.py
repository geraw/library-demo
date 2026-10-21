"""Re-evaluate a v011 review ZIP without starting any SUT or generator."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
from checker import evaluate_trace


def validate(path):
    summary={'archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'profile':'library-issta-v006','arms':{}}
    with zipfile.ZipFile(path) as archive,tempfile.TemporaryDirectory() as temporary:
        completed=json.loads(archive.read('completed.json'))
        if not completed.get('complete') or completed.get('scenario_count')!=542:
            raise ValueError('Expected a complete 542-case v011 archive')
        manifest=json.loads(archive.read('input_hashes.json'))
        for name,digest in manifest.items():
            if hashlib.sha256(archive.read(name.replace('\\','/'))).hexdigest()!=digest:
                raise ValueError('Input digest mismatch: '+name)
        summary['input_manifest_verified']=True
        historical=json.loads(archive.read('results.json'))
        baseline=[json.loads(line) for line in archive.read('control/native.jsonl').splitlines()]
        eligible={str(r['case']) for r in baseline if r['native_pass']}
        for arm in ('control','business-four','book-read-one'):
            trace=Path(temporary)/(arm+'.jsonl');trace.write_bytes(archive.read(arm+'/http.jsonl'))
            report=evaluate_trace(trace,'library-issta-v006')
            computed={r['case']:r['result']['candidate_classes'] for r in report['cases'] if r['evaluable'] and r['result']['candidate_classes']}
            expected=historical[arm]['observer']['clean_candidate_cases']
            # Existing diagnostic ordering is irrelevant; class membership and case identity must agree.
            same={k:sorted(v) for k,v in computed.items()}=={k:sorted(v) for k,v in expected.items()}
            native=[json.loads(line) for line in archive.read(arm+'/native.jsonl').splitlines()]
            if len(native)!=542 or report['case_count']!=542:raise ValueError('Incomplete case count: '+arm)
            summary['arms'][arm]={
                'case_count':report['case_count'],'evaluable_case_count':report['evaluable_case_count'],
                'status':report['status'],'matches_original_candidate_cases':same,
                'external_evaluator':report['external_evaluator'],
                'native_failed_cases':[str(r['case']) for r in native if not r['native_pass']],
                'native_failed_control_eligible_cases':[str(r['case']) for r in native if not r['native_pass'] and str(r['case']) in eligible],
                'native_metric_note':'Native JSON flags retained separately; not inferred from oracle candidates'}
            if not same or report['status']!='EVALUATED_RECORDED_CASES':
                raise ValueError('Archive regression mismatch or insufficient evidence: '+arm)
        summary['work_provenance']=json.loads(archive.read('work-provenance.json')) if 'work-provenance.json' in archive.namelist() else None
    summary['validation']='PASS'
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; choose a new path')
    result=validate(args.archive);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
