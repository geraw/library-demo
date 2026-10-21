"""Re-analyze the complete original g009 cloud runs, without native Provengo attribution."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v005'))
import analyze_coverage as previous
from coverage_classifier import classify
from log_join import join,error_family


def analyze(manifest,root):
    ir_path=root/manifest['ir_archive']
    if previous.digest(ir_path.read_bytes())!=manifest['ir_archive_sha256']:raise ValueError('IR source archive hash mismatch')
    with zipfile.ZipFile(ir_path) as z:ir=json.loads(z.read('generated/contract-ir.json'))
    observations=[];runs=[];oracles=[]
    for spec in manifest['runs']:
        if spec['tool']!='route-harness':raise ValueError('This manifest declares cloud harness evidence only')
        folder=root/spec['folder'];payloads={}
        for name,expected in spec['files'].items():
            raw=(folder/name).read_bytes()
            if previous.digest(raw)!=expected['sha256']:raise ValueError('Input hash mismatch: '+str(folder/name))
            payloads[name]=raw
        summary_raw=(root/spec['result_summary']).read_bytes()
        if previous.digest(summary_raw)!=spec['result_summary_sha256']:raise ValueError('Harness result hash mismatch')
        summary=json.loads(summary_raw)
        if summary.get('sut_version')!=spec['version']:raise ValueError('SUT version mismatch')
        rows=[json.loads(s) for s in payloads['gateway-journal.jsonl'].decode('utf-8-sig').splitlines() if s.strip()]
        links,calibration=join(rows,payloads['sut.log'].decode('utf-8-sig'),complete_sequential=spec['complete_sequential'])
        source={'file':str(folder/'gateway-journal.jsonl'),'sha256':previous.digest(payloads['gateway-journal.jsonl']),
                'source_commit':manifest['commit'],'IR_archive_sha256':manifest['ir_archive_sha256']}
        run=dict(id=spec['id'],product='gitea',version=spec['version'],tool='route-harness',seed=spec['seed'],source=source)
        obs,original_oracles=previous.baseline.gitea_observations(run,{'records':rows,'ir':ir,'sut_log':''})
        for o in obs:
            i=o['source']['record']
            if i in links:
                witness=dict(links[i],file=str(folder/'sut.log'),sha256=previous.digest(payloads['sut.log']))
                o['correlated_log']=witness;o['server_message']=witness['message']
                o['facts']['correlated_error_family']=error_family(witness['message']);o['witnesses'].append(witness)
        previous.augment_gitea(obs,rows)
        for o in obs:
            request=o.get('request')
            if o['entity']=='release' and isinstance(request,dict) and isinstance(request.get('tag_name'),str):
                family=o['facts'].get('correlated_error_family')
                o['facts']['release_tag_error_context_verified']=(family=='invalid_tag' or
                        (family=='git_ref_failure' and len(request['tag_name'])>=10000))
                o['facts']['tag_name_length']=len(request['tag_name'])
        observations.extend(obs);oracles.extend(original_oracles)
        if summary.get('requests')!=len(obs):raise ValueError('Full journal does not match original request count')
        runs.append(dict(id=spec['id'],tool='route-harness',version=spec['version'],http_records=len(obs),
                         http_5xx=sum(o['status']==500 for o in obs),correlated_5xx=len(links),clock_alignment=calibration,
                         native_provengo_run=False,original_harness_status=summary.get('status'),
                         runner_log_sha256=previous.digest(payloads['native.log'])))
    report=classify(observations,ROOT/'catalogs')
    report.update(schema_version='natchan-cloud-complete/1',runs=runs,source_commit=manifest['commit'],original_oracles=oracles,
                  known_signature_occurrences=dict(sorted(Counter(a['catalog_id'] for a in report['assessments'] if a.get('kind')=='known_bug').items())),
                  provider_audit=previous.provider_audit(observations,oracles),new_sut_calls=0)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence-root',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=ROOT/'manifest-cloud-v006.json');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    r=analyze(json.loads(a.manifest.read_text()),a.evidence_root)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('NATCHAN_CLOUD_V006_COMPLETE '+str(a.output.resolve()))


if __name__=='__main__':main()
