"""Focused offline audit of five paired fixed-Java failures, not a general classifier."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
import zipfile

CASES=(80,257,260,266,433)


def audit(archive):
    checker_path=Path(__file__).resolve().parents[3]/'semantic-checker-v001'/'checker.py'
    spec=importlib.util.spec_from_file_location('preserved_library_checker',checker_path)
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    def path(r): return urlsplit(r.get('path','')).path
    def hold_id(r): return int(path(r).rsplit('/',1)[-1])
    out=dict(schema_version=1,scope='Focused retrospective audit; no new execution or automatic general classification',
             archive_sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest(),cases=[],source_files={})
    with zipfile.ZipFile(archive) as z,tempfile.TemporaryDirectory() as temporary:
        hashes=json.loads(z.read('input_hashes.json'))
        for name,digest in hashes.items():
            if hashlib.sha256(z.read(name.replace('\\','/'))).hexdigest()!=digest:raise ValueError('Input hash mismatch')
        out['input_manifest_verified']=True
        traces={};natives={};reports={}
        for arm in ['control','business-four']:
            member=arm+'/http.jsonl';raw=z.read(member)
            traces[arm]=[(i,json.loads(line)) for i,line in enumerate(raw.splitlines(),1)]
            natives[arm]={r['case']:r for r in map(json.loads,z.read(arm+'/native.jsonl').splitlines())}
            target=Path(temporary)/(arm+'.jsonl');target.write_bytes(raw)
            reports[arm]=checker.evaluate_trace(target,'library-issta-v006')
        for name in ['control/http.jsonl','business-four/http.jsonl','control/native.jsonl','business-four/native.jsonl',
                     'business-four/java-suite.log','src/V011Actuation.java','src/V011GuidedSuiteHarness.java',
                     'model/spec/js/interfaces.library.js','sut_buggy_issta.py']:
            out['source_files'][name]=hashlib.sha256(z.read(name)).hexdigest()
        for number in CASES:
            arm_evidence={}
            for arm in ['control','business-four']:
                records=[(i,r) for i,r in traces[arm] if r.get('case')==number]
                deletes=[(i,r) for i,r in records if r.get('role')=='tool' and r['method']=='DELETE' and path(r).startswith('/holds/')]
                first_line,first=deletes[0];second_line,second=deletes[1]
                previous=[(i,r) for i,r in records if i<first_line and r.get('role')=='oracle' and path(r)=='/holds'][-1]
                observation=[(i,r) for i,r in records if first_line<i<second_line and r.get('role')=='oracle' and path(r)=='/holds'][0]
                before=previous[1]['response'];after=observation[1]['response']
                target_id,sibling_id=hold_id(first),hold_id(second)
                target=next(r for r in before if r['id']==target_id)
                sibling=next(r for r in before if r['id']==sibling_id)
                created={r['response']['id']:(i,r) for i,r in records if i<first_line and r.get('role')=='tool' and r['method']=='POST' and path(r)=='/holds' and r['status']==201}
                result=next(r for r in reports[arm]['cases'] if r['case']==str(number))
                checks=dict(verified_empty_start=any(r.get('role')=='boundary' and r.get('empty_verified') is True for _,r in records),
                    both_hold_ids_came_from_successful_creation=target_id in created and sibling_id in created,
                    distinct_holds_same_owner=target_id!=sibling_id and target['userId']==sibling['userId'],
                    readbacks_succeeded=previous[1]['status']==200 and observation[1]['status']==200,
                    first_delete_success=first['status']==200,
                    target_removed=all(r['id']!=target_id for r in after),
                    sibling_preserved=(any(r['id']==sibling_id for r in after)),
                    second_delete_status=second['status'],
                    recomputed_case_evaluable=result['evaluable'])
                arm_evidence[arm]=dict(native=natives[arm][number],checks=checks,
                    first_delete=dict(line=first_line,step=next(j for j,(i,r) in enumerate([(i,r) for i,r in records if r.get('role')=='tool'],1) if i==first_line),path=first['path'],target_id=target_id),
                    second_delete=dict(line=second_line,path=second['path'],sibling_id=sibling_id,response=second['response']),
                    owner_id=target['userId'],before_readback=dict(line=previous[0],holds=before),after_readback=dict(line=observation[0],holds=after),
                    creation_lines={str(k):created[k][0] for k in [target_id,sibling_id]},
                    recomputed_clean_verdicts=result['result']['first_clean_verdicts'])
            good,bad=arm_evidence['control'],arm_evidence['business-four']
            common=['verified_empty_start','both_hold_ids_came_from_successful_creation','distinct_holds_same_owner','readbacks_succeeded','first_delete_success','target_removed','recomputed_case_evaluable']
            checks=[all(v['checks'][key] is True for key in common) for v in [good,bad]]
            checks += [good['checks']['sibling_preserved'] is True,good['checks']['second_delete_status']==200,good['native']['native_pass'] is True,
                       bad['checks']['sibling_preserved'] is False,bad['checks']['second_delete_status']==404,bad['native']['native_pass'] is False,
                       bad['native']['failedAction']=='deleteHold',bad['native']['actuator_errors']==1,
                       bad['native']['listener_errors']==0,bad['native']['exception'] is None,
                       any(v['source_line']==bad['first_delete']['line'] and any(x['rule']=='STATE_MISMATCH' and x.get('entity')=='holds' for x in v['violations']) for v in bad['recomputed_clean_verdicts'])]
            if not all(checks):raise ValueError('Audit did not qualify case '+str(number))
            out['cases'].append(dict(case=number,assessment='Confirmed manifestation of seeded bug 5 in retained evidence',
                native_failure='Later deleteHold receives 404 instead of expected 200',
                common_observer='Earlier successful delete removes the non-target same-owner hold',arms=arm_evidence))
        out['summary']=dict(qualified_case_count=5,distinct_seeded_bugs=1,seeded_bug='bug-5',new_sut_executions=0,
            native_detection='Response-code assertion detects the later consequence; the business explanation comes from independent state evidence',
            limits=['Paired runs use the same fixed catalog but fuzz payload variants and allocated IDs differ',
                    'No isolated bug-5-only replay was performed in this audit',
                    'No universal tool capability conclusion follows from this run'])
    out['validation']='PASS'
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists')
    result=audit(args.archive)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2);target.write('\n')
    print('NATIVE_FIVE_AUDIT_PASS '+str(args.output.resolve()))
