"""Tool-independent, recorded-case-local evaluator. Domain rules live in named profiles."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
PROFILES={
    'library-issta-v006':('library_issta_v006.py','current Library experiment: five seeded faults'),
    'library-v38':('library_v38.py','historical Library: HOLD_OWNERSHIP and LOAN_LIMIT (three accepted loans)'),
    'garage-v38':('garage_v38.py','historical Garage active orders and cross-garage car rules'),
    'pharmacy-v38':('pharmacy_v38.py','historical Pharmacy refill/ownership rules; class-specific response markers required'),
    'netbox-legacy-v38':('netbox_legacy_v38.py','historical two-fault NetBox fixture; not the A2A fixture'),
    'netbox-a2a-v38':('netbox_a2a_v38.py','historical five-class NetBox A2A fixture'),
    'todoist-runtime-v38':('todoist_runtime_v38.py','runtime smoke only; does not detect semantic bugs'),
}


def vendor_path(filename):
    path=ROOT/'vendor'/filename
    manifest=json.loads((ROOT/'provenance.json').read_text(encoding='utf-8'))
    expected=manifest['files']['vendor/'+filename]['sha256']
    # Git may convert line endings on Windows; source identity is normalized for import verification.
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected:
        normalized=hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        if normalized!=manifest['files']['vendor/'+filename].get('lf_sha256'):
            raise ValueError('Historical rule source changed: '+filename)
    return path


def load_vendor(profile):
    path=vendor_path(PROFILES[profile][0])
    spec=importlib.util.spec_from_file_location('semantic_profile_'+profile.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def load_trace(path):
    records=[];issues=[]
    for number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        text=line.strip();marker='MODEL_EVENT '
        if marker in text:text=text.split(marker,1)[1].strip()
        elif not text.startswith('{'):continue
        try:
            record=json.loads(text)
            if not isinstance(record,dict):raise ValueError('Expected object')
        except (ValueError,TypeError) as exc:
            issues.append({'line':number,'error':str(exc)});continue
        record['_source_line']=number
        records.append(record)
    return records,issues


def split_cases(records,single_sequence=False,initial_empty=False):
    cases=[];current=None;ignored=0
    if single_sequence:
        current={'case':'declared-single-sequence','initial_empty':initial_empty,'boundary_evidence':'user-declared',
                 'records':[],'issues':[]};cases.append(current)
    for record in records:
        role=record.get('role')
        if role=='boundary':
            current={'case':str(record.get('case')),'initial_empty':record.get('empty_verified') is True,
                     'boundary_evidence':'recorded-empty-verification','records':[],'issues':[]}
            cases.append(current);continue
        if role=='startup':continue
        if role in ('verdict',):continue  # Recompute; never trust previous oracle conclusions.
        if role not in (None,'tool','oracle','observer_error'):continue
        if role is None and not all(k in record for k in ('method','path','status')):continue
        if current is None:ignored+=1;continue
        if role is not None and 'case' in record and str(record['case'])!=current['case']:
            current['issues'].append({'line':record['_source_line'],'error':'Case label differs from current boundary'})
        current['records'].append(record)
    return cases,ignored


def canonical(record):
    return {'kind':'api_success' if 200<=int(record['status'])<300 else 'api_result',
            'method':str(record['method']).upper(),'path':urlsplit(record['path']).path,
            'body':record.get('request',record.get('body')),'status':int(record['status']),
            'response':record.get('response'),'_source_line':record['_source_line']}


def current_library(records):
    module=load_vendor('library-issta-v006');emitted=[];missing=[]
    ledger=module.Ledger(None,emitted.append);ledger.case='one-recorded-case'
    for index,record in enumerate(records):
        if record.get('role')=='observer_error':
            missing.append({'line':record['_source_line'],'error':'Source observer error'});ledger.tainted=True;continue
        if record.get('role')!='tool' and record.get('role') is not None:continue
        following=[]
        for item in records[index+1:]:
            if item.get('role')=='tool' or item.get('role') is None:break
            if item.get('role')=='oracle':following.append(item)
        def readback(method,path,raw):
            if not following or following[0].get('method')!=method or following[0].get('path')!=path:
                missing.append({'line':record['_source_line'],'error':'Missing ordered readback '+path})
                return None,None
            evidence=following.pop(0)
            if evidence.get('status')!=200 or not isinstance(evidence.get('response'),list):
                missing.append({'line':evidence['_source_line'],'error':'Readback unavailable '+path})
            return evidence['status'],evidence.get('response')
        ledger.forward=readback
        before=len(emitted)
        try:
            ledger.check(str(record['method']).upper(),record['path'],record.get('request',record.get('body')),
                         int(record['status']),record.get('response'))
        except Exception as exc:
            missing.append({'line':record['_source_line'],'error':repr(exc)});ledger.tainted=True
        for generated in emitted[before:]:generated['source_line']=record['_source_line']
    verdicts=[r for r in emitted if r['role']=='verdict']
    clean=[r for r in verdicts if not r['prefix_tainted']]
    candidates=[]
    for verdict in clean:
        for violation in verdict['violations']:
            label=None;rule=violation['rule'];path=urlsplit(verdict['path']).path
            if rule=='EXISTING_BOOK_READ':label='bug-4'
            elif rule=='VALID_LOAN_REJECTED':
                active=violation['active_for_user'];prior=violation['prior_pair_loans']
                if active==3 and prior<2:label='bug-1-candidate'
                elif prior==2 and active<3:label='bug-2-candidate'
                else:label='loan-rejection-ambiguous'
            elif rule=='STATE_MISMATCH' and verdict['method']=='DELETE':
                if path.startswith('/loans/') and violation.get('entity')=='loans':label='bug-3-candidate'
                if path.startswith('/holds/') and violation.get('entity')=='holds':label='bug-5-candidate'
            if label:candidates.append(label)
    return {'confirmed_classes':[], 'candidate_classes':sorted(set(candidates)),
            'verdicts':verdicts,'first_clean_verdicts':clean,'evidence_issues':missing,
            'scoring_note':'Recomputed v006 observer diagnostics; seeded-bug labels require control/native review'}


def historical(profile,events):
    if profile=='garage-v38':
        # Preserve the historical script byte-for-byte, including its CLI-only interface.
        path=vendor_path(PROFILES[profile][0])
        with tempfile.TemporaryDirectory() as tmp:
            trace=Path(tmp)/'trace.jsonl'
            trace.write_text(''.join('MODEL_EVENT '+json.dumps(e)+'\n' for e in events),encoding='utf-8')
            result=subprocess.run([sys.executable,str(path),str(trace)],capture_output=True,text=True,timeout=30)
            if result.returncode:raise ValueError(result.stderr)
            raw=json.loads(result.stdout)
        labels=[name for key,name in [('three_active_orders_confirmed','GARAGE_THREE_ACTIVE_ORDERS'),
                ('one_car_two_garages_confirmed','GARAGE_ONE_CAR_TWO_GARAGES')] if raw.get(key)]
        return {'confirmed_classes':labels,'historical_result':raw,
                'scoring_note':'Historical Garage rules preserved; no new invariant inference'}
    module=load_vendor(profile)
    if profile in ('library-v38','netbox-a2a-v38'):return module.evaluate_sequence(events)
    if profile=='pharmacy-v38':
        confirmed=[];witnesses={}
        for function,name in [('evaluate_p1','P1_REFILL_UNDERFLOW'),('evaluate_p2','P2_DOUBLE_PROCESS')]:
            found,witness=getattr(module,function)(events)
            if found:confirmed.append(name);witnesses[name]=witness
        return {'confirmed_classes':confirmed,'witnesses':witnesses}
    raw=module.evaluate(events)
    if profile=='netbox-legacy-v38':
        return {'confirmed_classes':[name for name,r in raw['faults'].items() if r['confirmed']], 'historical_result':raw}
    return {'confirmed_classes':[],'runtime_diagnostic':raw,'scoring_note':'Runtime smoke, not semantic bug discovery'}


def evaluate_trace(path,profile,single_sequence=False,initial_empty=False):
    records,parse_issues=load_trace(path)
    cases,unscoped=split_cases(records,single_sequence,initial_empty)
    results=[]
    for ordinal,case in enumerate(cases,1):
        issues=list(case['issues'])
        http=[]
        for record in case['records']:
            if record.get('role') in ('oracle','observer_error'):continue
            try:http.append(canonical(record))
            except Exception as exc:issues.append({'line':record['_source_line'],'error':str(exc)})
        if profile!='library-issta-v006' and any(e['method']=='POST' and e['path']=='/reset' for e in http):
            issues.append({'error':'Internal reset requires separately recorded case boundaries; no stitching across reset'})
        try:
            result=current_library(case['records']) if profile=='library-issta-v006' else historical(profile,http)
            issues.extend(result.get('evidence_issues',[]))
        except Exception as exc:
            result={'confirmed_classes':[],'candidate_classes':[]};issues.append({'error':repr(exc)})
        if any(r.get('role')=='observer_error' for r in case['records']):issues.append({'error':'Source observer error'})
        eligible=case['initial_empty'] and not issues and bool(http) and not parse_issues
        results.append({'ordinal':ordinal,'case':case['case'],'initial_empty':case['initial_empty'],
                        'boundary_evidence':case['boundary_evidence'],'evaluable':eligible,'issues':issues,
                        'http_event_count':len(http),'result':result})
    classes=sorted({c for r in results if r['evaluable'] for c in r['result'].get('confirmed_classes',[])})
    candidates=sorted({c for r in results if r['evaluable'] for c in r['result'].get('candidate_classes',[])})
    complete=bool(results) and all(r['evaluable'] for r in results) and not parse_issues and unscoped==0
    return {'schema_version':1,'profile':profile,'profile_description':PROFILES[profile][1],
            'trace_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scope':'recorded-case-local',
            'status':'EVALUATED_RECORDED_CASES' if complete else 'NOT_FULLY_EVALUABLE',
            'case_count':len(results),'evaluable_case_count':sum(r['evaluable'] for r in results),
            'parse_issues':parse_issues,'unscoped_record_count':unscoped,
            'external_evaluator':{'confirmed_classes_in_evaluable_cases':classes,
                'candidate_classes_in_evaluable_cases':candidates,
                'cases_with_candidates':sum(r['evaluable'] and bool(r['result'].get('candidate_classes')) for r in results)},
            'native_tool_faults':{'status':'not_supplied','note':'Never inferred from external-evaluator findings'},
            'scope_note':'A case boundary proves only its recorded scope; it does not establish native test boundaries inside a campaign.',
            'cases':results}


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('profiles')
    check=commands.add_parser('evaluate');check.add_argument('--profile',choices=PROFILES,required=True)
    check.add_argument('--trace',type=Path,required=True);check.add_argument('--output',type=Path,required=True)
    check.add_argument('--single-sequence',action='store_true');check.add_argument('--initial-empty',action='store_true')
    check.add_argument('--native-report',type=Path,help='Preserve a separately supplied native JSON report without converting its metric')
    serve=commands.add_parser('serve-library');serve.add_argument('arguments',nargs=argparse.REMAINDER)
    capture=commands.add_parser('capture');capture.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    if args.command=='profiles':
        print(json.dumps({k:v[1] for k,v in PROFILES.items()},indent=2));return 0
    if args.command in ('capture','serve-library'):
        name='http_trace_proxy_v38.py' if args.command=='capture' else 'library_issta_v006.py'
        extra=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
        return subprocess.call([sys.executable,str(vendor_path(name)),*extra])
    if args.initial_empty and not args.single_sequence:parser.error('--initial-empty requires --single-sequence')
    if args.output.exists():parser.error('Output already exists; choose a new path')
    report=evaluate_trace(args.trace,args.profile,args.single_sequence,args.initial_empty)
    if args.native_report:
        report['native_tool_faults']={'status':'supplied_separately','source_sha256':hashlib.sha256(args.native_report.read_bytes()).hexdigest(),
                                      'uninterpreted_report':json.loads(args.native_report.read_text(encoding='utf-8-sig'))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))
    return 0 if report['status']=='EVALUATED_RECORDED_CASES' else 2


if __name__=='__main__':raise SystemExit(main())
