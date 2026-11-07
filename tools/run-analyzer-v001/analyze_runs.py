"""Compare retained run results across tools and systems; never execute generators or SUTs."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile
from native_adapters import analyze as native_analyze

ROOT=Path(__file__).resolve().parent
CHECKER_ROOT=ROOT.parent/'semantic-checker-v001'
spec=importlib.util.spec_from_file_location('shared_semantic_checker',CHECKER_ROOT/'checker.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def resolve(base,value):return (base/Path(value)).resolve()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_http(path):
    records,issues=checker.load_trace(path);requests=[]
    for r in records:
        if r.get('role') in (None,'tool') and all(k in r for k in ('method','path','status')):
            try:requests.append(checker.canonical(r))
            except (ValueError,TypeError):issues.append({'line':r['_source_line'],'error':'Invalid HTTP record'})
    return {'request_count':len(requests),'http_4xx':sum(400<=r['status']<500 for r in requests),
            'http_5xx':sum(500<=r['status']<600 for r in requests),'parse_issues':issues,
            'note':'HTTP anomalies are not themselves confirmed semantic bugs; oracle readbacks are excluded'}


def analyze_run(run,base):
    for key in ('id','tool','system'):
        if not isinstance(run.get(key),str) or not run[key]:raise ValueError('Each run requires '+key)
    artifacts={k:resolve(base,v) for k,v in run.get('artifacts',{}).items()}
    native=native_analyze(run['tool'].lower(),artifacts)
    result={'id':run['id'],'tool':run['tool'].lower(),'system':run['system'],'variant':run.get('variant'),
            'profile':run.get('profile'),'native':native,'execution':{'status':'unknown'},
            'http_anomalies':None,'semantic':{'status':'not_evaluated','reason':'No trace/profile supplied'},'input_sha256':{}}
    execution=artifacts.get('execution_json')
    if execution:
        try:
            value=json.loads(execution.read_text(encoding='utf-8-sig'))
            result['execution']={'status':'recorded','exit_code':value.get('exit_code'),
                'watchdog_timeout':value.get('watchdog_timeout'),'wall_seconds':value.get('wall_seconds'),'source_sha256':digest(execution)}
        except (OSError,ValueError) as exc:result['execution']={'status':'invalid_artifact','error':str(exc)}
    trace=artifacts.get('trace')
    if trace:
        try:
            result['http_anomalies']=summarize_http(trace)
            if run.get('profile'):
                if run['profile'] not in checker.PROFILES:raise ValueError('Unknown semantic profile')
                report=checker.evaluate_trace(trace,run['profile'],run.get('single_sequence',False),run.get('initial_empty',False))
                result['semantic']={k:v for k,v in report.items() if k!='cases'}
                result['semantic']['case_evidence']=report['cases']
        except (OSError,ValueError) as exc:result['semantic']={'status':'invalid_or_missing_evidence','error':str(exc)}
    for label,name in run.get('inputs',{}).items():
        path=resolve(base,name)
        result['input_sha256'][label]=digest(path) if path.is_file() else None
    return result


def analyze_manifest(manifest,base):
    if manifest.get('schema_version')!=1 or not isinstance(manifest.get('runs'),list):raise ValueError('Expected schema_version 1 and runs array')
    ids=[r.get('id') for r in manifest['runs']]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate run ids; runs must never overwrite one another')
    rows=[analyze_run(run,base) for run in manifest['runs']]
    # No unconditional "same SUT/OpenAPI" assertions and no latest-run collapse.
    return {'schema_version':1,'analyzer_version':'v001','run_count':len(rows),'runs':rows,
        'policy':{'all_runs_retained':True,'native_metrics_not_interchangeable':True,
                  'generic_http_errors_are_not_semantic_bugs':True,'missing_evidence_is_not_zero':True,
                  'measurement_parity':'Not assumed. Compare supplied input_sha256, scope and configuration explicitly.'}}


def analyze_library_archive(path):
    with zipfile.ZipFile(path) as archive,tempfile.TemporaryDirectory() as temporary:
        completed=json.loads(archive.read('completed.json'))
        base=Path(temporary);runs=[]
        for arm,variant in [('control','healthy'),('business-four','bugs-1-2-3-5'),('book-read-one','bug-4')]:
            artifacts={}
            for key,name in [('trace','http.jsonl'),('native_jsonl','native.jsonl'),('execution_json','java-suite-execution.json')]:
                data=archive.read(arm+'/'+name);target=base/arm/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                artifacts[key]=str(target)
            runs.append({'id':arm,'tool':'provengo','system':'library','variant':variant,
                         'profile':'library-issta-v006','artifacts':artifacts})
        report=analyze_manifest({'schema_version':1,'runs':runs},base)
        report['source_archive_sha256']=digest(path)
        control=report['runs'][0]['native']
        expected=completed.get('scenario_count')
        archive_complete=completed.get('complete') is True and type(expected) is int
        for row in report['runs']:
            if not archive_complete or row['native'].get('case_count')!=expected:
                row['native'].update(status='incomplete',count=None,reason='Native case count or archive completion metadata is incomplete')
        baseline_failed=set(control.get('failed_cases',[]))
        baseline_passed=set(control.get('passed_cases',[])) if control['status']=='reported' else set()
        for row in report['runs']:
            failed=row['native'].get('failed_cases')
            if failed is not None:
                row['native']['failed_cases_also_failing_control']=[c for c in failed if c in baseline_failed]
                row['native']['failed_cases_on_passing_control']=[c for c in failed if c in baseline_passed]
            # Temporary extraction paths are not stable source references; bind them to archive entries.
            for evidence in row['native'].get('evidence',[]):evidence['path']=row['id']+'/'+Path(evidence['path']).name
        return report


def write_report(report,output):
    table=output.with_suffix('.csv')
    if output.exists() or table.exists():raise ValueError('Choose new JSON/CSV output paths')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    columns=['id','system','tool','variant','native_status','native_metric','native_count','http_4xx','http_5xx','semantic_status','external_classes','external_candidates']
    with table.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=columns);writer.writeheader()
        for r in report['runs']:
            semantic=r['semantic'];external=semantic.get('external_evaluator',{});http=r['http_anomalies'] or {}
            writer.writerow({'id':r['id'],'system':r['system'],'tool':r['tool'],'variant':r['variant'],
                'native_status':r['native']['status'],'native_metric':r['native']['metric'],'native_count':r['native']['count'],
                'http_4xx':http.get('http_4xx'),'http_5xx':http.get('http_5xx'),'semantic_status':semantic['status'],
                'external_classes':';'.join(external.get('confirmed_classes_in_evaluable_cases',[])),
                'external_candidates':';'.join(external.get('candidate_classes_in_evaluable_cases',[]))})
    return table


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--manifest',type=Path);source.add_argument('--library-archive',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.library_archive:report=analyze_library_archive(args.library_archive)
    else:report=analyze_manifest(json.loads(args.manifest.read_text(encoding='utf-8-sig')),args.manifest.resolve().parent)
    table=write_report(report,args.output)
    print('RUN_ANALYSIS_JSON '+str(args.output));print('RUN_ANALYSIS_CSV '+str(table))
    print('ANALYZED_RUNS '+str(report['run_count']))
