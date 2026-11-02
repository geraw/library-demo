"""Offline story package reader. Producer checks are comparison data, never oracle input."""
import argparse,hashlib,json,tempfile,zipfile
from collections import Counter
from pathlib import Path
import natchan
from common import write


def producer_summary(result):
    candidates=[];observations=0;excluded=[]
    for story in result.get('stories',[]):
        observations+=len(story.get('observations',[]))
        for check in story.get('failed_checks',[]):
            if check.get('pass') is not False:continue
            record={'story':story.get('story'),'check':check.get('check'),'source':'producer_last_attempt_only','independently_confirmed':False}
            detail=check.get('detail') or {}
            empty=(check.get('expected')==[] and check.get('observed')==[] and detail.get('A')==[] and detail.get('B')==[])
            if story.get('status')!='COMPLETED':record['reason']='STORY_DID_NOT_COMPLETE';excluded.append(record)
            elif 'INTRA-REF' in str(check.get('check')) and empty:record['reason']='EMPTY_REFERENCE_SETS_ARE_NOT_A_VIOLATION';excluded.append(record)
            else:candidates.append(record)
    return {'story_statuses':dict(Counter(s.get('status') for s in result.get('stories',[]))),
            'producer_check_candidates':candidates,'excluded_checks':excluded,'producer_observations_not_failures':observations,
            'checks_used_by_independent_judge':False,'attempt_scope':'producer summary describes last attempt; independent analysis retains raw attempts separately',
            'reference_warning':'Names and producer reference bindings do not prove relationships; enum fields require contract validation'}


def run(evidence,contract,output):
    if output.exists():raise ValueError('Use a new output directory')
    def read(name):
        if evidence.is_dir():return (evidence/name).read_bytes()
        with zipfile.ZipFile(evidence) as z:
            matches=[n for n in z.namelist() if n.replace('\\','/').rstrip('/').split('/')[-1]==name]
            if len(matches)!=1:raise ValueError('Missing or ambiguous '+name)
            if z.getinfo(matches[0]).file_size>512*1024*1024:raise ValueError('Evidence exceeds 512 MiB')
            return z.read(matches[0])
    raw=read('gateway-journal.jsonl');result=json.loads(read('result_stories.json'));cb=contract.read_bytes()
    expected=result.get('contract_sha256')
    if expected and hashlib.sha256(cb).hexdigest()!=expected:raise ValueError('Contract hash does not match the producer run')
    output.mkdir(parents=True);contract=contract.resolve();knowledge=output.resolve()/'knowledge.json';freeze=output.resolve()/'freeze.json'
    write(knowledge,natchan.contract(contract));write(freeze,natchan.make_freeze(contract,knowledge))
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'gateway-journal.jsonl';path.write_bytes(raw)
        request={'schema_version':'natchan-semantic-request/1','run':{'id':'story-package-replay','product':'captured-api','tool':'raw-http','start_state':'unknown'},
                 'contract':str(contract),'knowledge':str(knowledge),'freeze':str(freeze),
                 'evidence':{'format':'journal-jsonl','traffic':str(path),'capture':{}}}
        rp=output/'request.json';write(rp,request);independent=natchan.run(rp,output/'analysis')
    report={'producer':producer_summary(result),'independent':independent,'journal_sha256':hashlib.sha256(raw).hexdigest(),
            'contract_sha256':hashlib.sha256(cb).hexdigest(),'new_SUT_requests':0,
            'source_evidence':str(evidence.resolve()),'request_note':'request.json points to a temporary copy; rerun this command with the unchanged source package'}
    write(output/'story-review.json',report);return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=run(a.evidence,a.contract,a.output);print('STORY_REVIEW',a.output/'story-review.json');raise SystemExit(r['independent']['exit_code'])
