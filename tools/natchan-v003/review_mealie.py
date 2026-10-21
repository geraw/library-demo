"""Reclassify selected original Mealie TSE receipts; never replay or emit credentials."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
from classifier import classify, markdown

ROOT=Path(__file__).resolve().parent
# Fixed household-controls protocol, also declared by historical STEP_SPEC.
FAILED_WRITE_TARGETS={'other_list_add_a':'list_b','other_list_add_b':'list_a'}


def unresolved_writes(saved,order,start,end,target):
    result=[]
    for key in order[order.index(start)+1:order.index(end)]:
        v=saved[key]
        if not v.get('operation','').startswith(('POST ','PUT ','PATCH ','DELETE ')):continue
        body=v.get('body')
        if 200<=v.get('code',0)<300 and isinstance(body,dict) and body.get('id') and body['id']!=target:continue
        declared=FAILED_WRITE_TARGETS.get(key)
        resource=saved.get(declared,{}).get('body') if declared else None
        if isinstance(resource,dict) and resource.get('id') and resource['id']!=target:continue
        result.append(key)
    return result


def review(archive):
    historical=ROOT/'history/mealie_saved_evidence_audit.py'
    provenance=json.loads((ROOT/'history/provenance.json').read_text())
    raw=historical.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=provenance['retained_sha256'] and hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()!=provenance['retained_lf_sha256']:
        raise ValueError('Preserved historical audit source changed')
    spec=importlib.util.spec_from_file_location('preserved_mealie_audit',historical)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    archive_hash=hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    observations=[];runs=[];comparisons=[]
    with zipfile.ZipFile(archive) as z:
        members=[n for n in z.namelist() if 'historical/' in n and 'campaign-original/' in n and '/result-' in n and n.endswith('.json')]
        for member in members:
            data=z.read(member);record=json.loads(data)
            program=record.get('runtime_receipt',{}).get('identity_program',{})
            if not program:continue
            order=program['order'];saved=program['observations'];run=record['case']+'-'+str(record['sample'])
            runs.append(dict(id=run,case=record['case'],sample=record['sample'],receipt_response_count=record['runtime_receipt'].get('response_count'),source=member))
            for key in order:
                v=saved.get(key,{})
                if type(v.get('code')) is int and v['code']>=500:
                    observations.append(dict(id=run+':'+key,product='mealie',product_version='historical-unqualified-version',
                        run_id=run,tool='provengo',operation=v.get('operation'),status=v['code'],
                        source=dict(archive_sha256=archive_hash,member=member,member_sha256=hashlib.sha256(data).hexdigest(),observation=key),facts={},fact_basis='recomputed'))
            if record['case']=='household-controls':
                for actor in ['a','b']:
                    action_key='other_list_add_'+actor;after_key='owner_list_after_'+actor
                    after=saved[after_key];target=after['body']['id'];action=saved[action_key]
                    candidates=[k for k in order[:order.index(action_key)] if saved.get(k,{}).get('code')==200 and saved[k].get('actor')==after.get('actor') and isinstance(saved[k].get('body'),dict) and saved[k]['body'].get('id')==target and 'listItems' in saved[k]['body'] and saved[k].get('operation','').startswith('GET ')]
                    if not candidates:raise ValueError('No same-owner preimage')
                    before_key=candidates[-1]
                    comparison=audit.compare_owner_readbacks(saved[before_key],action,after,order,[before_key,action_key,after_key])
                    intervening=unresolved_writes(saved,order,before_key,action_key,target)
                    qualified=comparison['complete'] and not intervening
                    row=dict(run_id=run,action=action_key,preimage=before_key,readback=after_key,qualified=qualified,
                             intervening_unresolved_writes=intervening,**comparison)
                    comparisons.append(row)
                    obs=next(o for o in observations if o['id']==run+':'+action_key)
                    obs['facts']['state_changed_after_error']=qualified and comparison['state_changed']
                    obs['comparison']=row
    report=classify(observations)
    report['source_archive_sha256']=archive_hash
    report['historical_audit_source_sha256']=hashlib.sha256(historical.read_bytes()).hexdigest()
    report['review']=dict(runs=runs,owner_comparisons=comparisons,
        changed_after_error=sum(c['qualified'] and c['state_changed'] for c in comparisons),
        server_error_count=len(observations),new_sut_executions=0,
        limits=['Original receipt reanalysis only; no new tool execution',
                'Nearest owner preimage is used to avoid attributing earlier successful cross-add changes to the later failure',
                'No root cause or permission-policy confirmation from the 500 alone',
                'No automatic named F04/F05 assignment; product known-bug definitions remain to be qualified'])
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():parser.error('Output exists')
    report=review(args.archive);args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:json.dump(report,target,indent=2);target.write('\n')
    with args.output.with_suffix('.md').open('x',encoding='utf-8') as target:target.write(markdown(report))
    print('MEALIE_REANALYSIS '+str(args.output.resolve()))
