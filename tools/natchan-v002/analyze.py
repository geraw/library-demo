"""Evaluate imported evidence through product gateways using preserved rule providers."""
import argparse
import json
from pathlib import Path
from evidence import ingest
from gateways import select


def analyze_envelope(envelope, control_run_id=None):
    artifacts={a['id']:a for a in envelope['artifacts']}
    result=dict(schema_version='natchan-analysis/1',evidence=envelope,runs=[],findings=[],
                status='complete',control_comparison=dict(status='not_requested'),
                policy=dict(native_and_external_separate=True,candidates_are_not_confirmed_bugs=True))
    if control_run_id is not None and control_run_id not in {r['id'] for r in envelope['runs']}:
        raise ValueError('Control run ID not found')
    for run in envelope['runs']:
        _,product=select(run)
        trace_id=run['artifacts'].get('trace')
        selected=[e for e in envelope['events'] if e['run_id']==run['id'] and e['source']['artifact_id']==trace_id]
        row=dict(id=run['id'],tool=run['tool'],product=run['product'],product_gateway=product.id,
                 semantic=dict(status='NOT_EVALUATED',reason='Product gateway has no semantic provider'),native=dict(status='unknown'))
        result['runs'].append(row)
        native=[e for e in envelope['events'] if e['run_id']==run['id'] and e.get('native_interpretation')=='recorded_test_verdict']
        if native:
            row['native']=dict(status='recorded',metric='failed_fixed_java_tests',
                failed_cases=[str(e['payload']['case']) for e in native if not e['native_value']],
                passed_cases=[str(e['payload']['case']) for e in native if e['native_value']],
                note='Recorded native test flags; not unique bugs or external findings')
        native_records=[e for e in envelope['events'] if e['run_id']==run['id'] and e['kind']=='native_record']
        native_cases=[str(e['payload']['case']) for e in native]
        if len(native)!=len(native_records) or len(set(native_cases))!=len(native_cases):
            row['native']['status']='incomplete'
        if envelope['status']!='complete' or run['status']!='complete':
            row['semantic']=dict(status='NOT_EVALUATED',reason='Ingestion incomplete; no verdicts inferred from partial import')
            row['native']['status']='incomplete'
            result['status']='incomplete'
            continue
        if 'semantic_evaluation' not in product.contract.capabilities:
            result['status']='incomplete'
            continue
        if not trace_id or not selected:
            row['semantic']=dict(status='NOT_EVALUATED',reason='Trace evidence unavailable')
            result['status']='incomplete'
            continue
        try:
            report=product.evaluate(selected,artifacts[trace_id])
        except Exception as exc:
            row['semantic']=dict(status='NOT_EVALUATED',reason='Semantic provider failed',error=type(exc).__name__+': '+str(exc))
            result['status']='incomplete'
            continue
        row['semantic']=report
        if report['status']!='EVALUATED_RECORDED_CASES': result['status']='incomplete'
        by_line={e['source']['line']:e for e in selected}
        for case in report['cases']:
            if not case['evaluable']: continue
            for verdict in case['result'].get('first_clean_verdicts',[]):
                source_event=by_line[verdict['source_line']]
                boundary_lines=[e['source']['line'] for e in selected if e['kind']=='boundary']
                start=max((n for n in boundary_lines if n<=verdict['source_line']),default=0)
                end=min((n for n in boundary_lines if n>verdict['source_line']),default=float('inf'))
                context=[e['id'] for e in selected if start<=e['source']['line']<end]
                for violation in verdict['violations']:
                    # One occurrence per rule violation; no deduplication into unique product bugs.
                    result['findings'].append(dict(id='f'+str(len(result['findings'])+1),run_id=run['id'],
                        case=case['case'],case_ordinal=case['ordinal'],classification='external_observation',
                        qualification='candidate_requires_control_review',rule=violation['rule'],
                        source_event_id=source_event['id'],source=source_event['source'],
                        evidence=dict(verdict=verdict,violation=violation),
                        context_event_ids=context,
                        candidate_classes=case['result'].get('candidate_classes',[])))
    if control_run_id is not None:
        control=next(r for r in result['runs'] if r['id']==control_run_id)
        baseline=control['native']
        comparison=dict(status='unavailable',control_run_id=control_run_id,runs=[])
        if baseline['status']=='recorded':
            passing=set(baseline['passed_cases']);failing=set(baseline['failed_cases'])
            comparison['status']='recorded'
            for row in result['runs']:
                if row['id']==control_run_id: continue
                native=row['native']
                if native['status']!='recorded':
                    comparison['runs'].append(dict(id=row['id'],status='unavailable'));continue
                failures=native['failed_cases']
                comparison['runs'].append(dict(id=row['id'],status='recorded',
                    native_failed_on_passing_control=[c for c in failures if c in passing],
                    native_failed_on_failing_control=[c for c in failures if c in failing],
                    native_failed_without_control_verdict=[c for c in failures if c not in passing|failing]))
        comparison['note']='Explicit case-ID correlation only; pairing assumes the declared same catalog. It does not confirm unique bugs.'
        result['control_comparison']=comparison
    result['summary']=dict(run_count=len(result['runs']),external_observation_count=len(result['findings']),
                           confirmed_unique_bug_count=None,
                           candidate_cases=sum(r['semantic'].get('external_evaluator',{}).get('cases_with_candidates',0) for r in result['runs']))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path)
    mapping=parser.add_mutually_exclusive_group(required=True)
    mapping.add_argument('--manifest',type=Path)
    mapping.add_argument('--library-v011',action='store_true')
    parser.add_argument('--control-run',help='Explicit paired healthy run ID; Library layout uses control')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output exists; choose a new path')
    manifest=json.loads(args.manifest.read_text(encoding='utf-8-sig')) if args.manifest else None
    envelope=ingest(args.archive,manifest,library=args.library_v011)
    report=analyze_envelope(envelope,args.control_run or ('control' if args.library_v011 else None))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:
        json.dump(report,target,indent=2,ensure_ascii=False);target.write('\n')
    print('NATCHAN_ANALYSIS '+str(args.output.resolve()))
    print('NATCHAN_ANALYSIS_STATUS '+report['status'].upper())
    return 0 if report['status']=='complete' else 2


if __name__=='__main__': raise SystemExit(main())
