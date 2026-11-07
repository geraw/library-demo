"""Frozen offline G014 acceptance. Raw HTTP only; no producer verdict input.
Usage: python acceptance_real.py --study-root PATH --output NEW_DIRECTORY
The private study repository supplies the original archive; it is not republished.
"""
import argparse,hashlib,io,json,tempfile,zipfile
from pathlib import Path
from contract_context import derive
from traffic import exchanges
from judge import analyze
from common import engine_hashes


def run(study_root, output):
    archive=study_root/'results/gitea-g014-work-20261022/review_g014_s1.zip'
    contract=study_root/'toolkit/v2.7/configs/gitea/contract.json'
    raw_zip=archive.read_bytes()
    expected_blob='75ac336228bd5929bf438d98694ea41982393b09'
    blob=hashlib.sha1(b'blob '+str(len(raw_zip)).encode()+b'\0'+raw_zip).hexdigest()
    if blob!=expected_blob:raise ValueError('Frozen G014 archive bytes changed')
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as z: raw=z.read('gateway-journal.jsonl')
    cb=contract.read_bytes()
    expected_contract='a9c7e8dc4723f53dd3268405cec1f597a6d742898fea4443e72410c27f08519f'
    if hashlib.sha256(cb).hexdigest()!=expected_contract:raise ValueError('Frozen contract bytes changed')
    context=derive(json.loads(cb),expected_contract)
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'raw.jsonl';p.write_bytes(raw);out=io.StringIO()
        stats={};result=analyze(exchanges(p,'journal-jsonl',hashlib.sha256(raw).hexdigest(),stats),context,out,capture={})
    verdicts=[json.loads(l) for l in out.getvalue().splitlines()]
    observations=[v for v in verdicts if v['reason'].startswith('OBSERVED_FAILED_WRITE_')]
    observed_lines={v['evidence'][0]['line_1based'] for v in observations if v['status']==500}
    expected_lines={40,86,180,208,646,676}
    if observed_lines!=expected_lines:raise AssertionError(('G014 six failed-write witnesses',observed_lines))
    if any(v['value']!='policy_observation' or v['details']['background_concurrency_excluded'] for v in observations):
        raise AssertionError('Legacy evidence was promoted beyond its capture guarantees')
    # Counterfactual negative controls: preserve requests/errors but make each
    # adjacent readback equal its preimage. Explicitly not an original SUT run.
    lines=raw.decode().splitlines();rows=[json.loads(l) for l in lines]
    changed=0
    for v in observations:
        before=v['evidence'][1]['line_1based']-1;after=v['evidence'][2]['line_1based']-1
        rows[after]['response']=rows[before]['response'];changed+=1
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'control.jsonl';p.write_text('\n'.join(json.dumps(r) for r in rows));control_out=io.StringIO()
        control=analyze(exchanges(p,'journal-jsonl',hashlib.sha256(p.read_bytes()).hexdigest(),{}),context,control_out,capture={})
    if control['local_sequence_audit']['observations']!=0:raise AssertionError('Rollback negative control flagged')
    output.mkdir(parents=True,exist_ok=False)
    report={'status':'PASS','source_repository':'weissye/vikunja_study','source_commit':'d378389226c1af05e767ddb0db895fcc41bd368d',
            'archive_git_blob':blob,'journal_sha256':hashlib.sha256(raw).hexdigest(),'contract_sha256':expected_contract,
            'engine':engine_hashes(),'raw_stats':stats,'five_hundred_state_effects':len(observed_lines),
            'partial_500':sum(v['status']==500 and v['details']['outcome']=='partial' for v in observations),
            'subset_applied_500':sum(v['status']==500 and v['details']['outcome']=='committed_despite_error' for v in observations),
            'four_hundred_state_observations':sum(400<=v['status']<500 for v in observations),
            'counterfactual_rollback_controls':changed,'control_state_observations':0,
            'producer_verdicts_used':False,'new_SUT_requests':0,'isolation_proven':False,
            'scope':'requested comparable fields; not full-resource commit; observations are not new distinct bugs'}
    (output/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','five_hundred_state_effects','partial_500','subset_applied_500','four_hundred_state_observations','counterfactual_rollback_controls')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.study_root,a.output)
