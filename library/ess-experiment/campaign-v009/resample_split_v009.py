"""Fresh sample of ten; immutable replay in the business-four and book-read-one arms."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'campaign-v006'))
import pilot_v006 as runtime
core=runtime.core
ARMS={'business-four':'1,2,3,5','book-read-one':'4'}


def source_inputs(reference,override=None):
    reference=reference.resolve()
    env=json.loads((reference/'environment.json').read_text())
    jar=Path(override or env['provengo_jar'])
    if not jar.is_file():raise RuntimeError('Provengo JAR missing: '+str(jar))
    if core.sha(jar)!=env['jar_sha256']:raise RuntimeError('Provengo JAR differs from the reference campaign')
    profile=json.loads((reference/'model_profile.json').read_text())
    if profile['profile']!='business':raise RuntimeError('Expected the business model')
    manifest=json.loads((reference/'input_hashes.json').read_text())
    for relative,digest in manifest.items():
        path=Path(relative)
        if (path.parts and path.parts[0]=='model') or str(path)=='sut_buggy_issta.py':
            if core.sha(reference/path)!=digest:raise RuntimeError('Reference input changed: '+relative)
    return reference,jar,profile


def counts(folder):
    result={'clean_candidate_cases':{},'later_candidates':0,'tool_requests':0}
    first=set()
    with (folder/'http.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['role']=='tool':result['tool_requests']+=1
            if row['role']!='verdict':continue
            if row.get('prefix_tainted') or str(row['case']) in first:
                result['later_candidates']+=1;continue
            first.add(str(row['case']))
            labels=[]
            for violation in row['violations']:
                rule=violation['rule']
                if rule=='EXISTING_BOOK_READ':labels.append('bug-4')
                elif rule=='STATE_MISMATCH' and row['method']=='DELETE':
                    entity=violation.get('entity')
                    if row['path'].split('?')[0].startswith('/loans/') and entity=='loans':labels.append('bug-3-candidate')
                    elif row['path'].split('?')[0].startswith('/holds/') and entity=='holds':labels.append('bug-5-candidate')
                elif rule=='VALID_LOAN_REJECTED':
                    if violation.get('active_for_user')==3 and violation.get('prior_pair_loans',0)<2:labels.append('bug-1-candidate')
                    elif violation.get('prior_pair_loans')==2 and violation.get('active_for_user',0)<3:labels.append('bug-2-candidate')
                    else:labels.append('loan-rejection-ambiguous')
            result['clean_candidate_cases'][str(row['case'])]=labels or ['unclassified']
    result['unique_candidate_types']=sorted({x for labels in result['clean_candidate_cases'].values() for x in labels})
    result['score_status']='Observer diagnostics; inspect native failures and control evidence before final scoring'
    return result


def main(args):
    started=time.perf_counter()
    reference,jar,profile=source_inputs(args.reference_campaign,args.jar)
    root=reference.parent/('provengo-sample10-split-v009-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
    root.mkdir()
    timing={};summary={};core.Service=runtime.Service
    try:
        prep=time.perf_counter()
        shutil.copytree(reference/'model',root/'model',ignore=shutil.ignore_patterns('products','__pycache__','.git'))
        shutil.copy2(reference/'sut_buggy_issta.py',root/'sut_buggy_issta.py')
        contract=json.loads((Path(__file__).resolve().parents[1]/'campaign-v007/library_openapi_v007.json').read_text())
        contract['servers']=[{'url':'http://127.0.0.1:23243'}]
        core.write(root/'openapi.json',contract)
        core.write(root/'model_profile.json',profile)
        core.write(root/'environment.json',{'version':'v009','reference_campaign':str(reference),
            'provengo_jar':str(jar),'jar_sha256':core.sha(jar),'python':sys.version,
            'sample_size':10,'batch_size':5,'selection':'Fresh native sample; no ranking or fault-directed selection',
            'sut_sha256':core.sha(root/'sut_buggy_issta.py'),'contract_sha256':core.sha(root/'openapi.json'),
            'java_tests_next':'Existing StrictGuidedRun.java; not executed in this sampling measurement'})
        core.write(root/'input_hashes.json',{str(p.relative_to(root)):core.sha(p) for p in root.rglob('*') if p.is_file()})
        result=core.command([args.java,'-jar',jar,'sample','-h'],root/'sample-help.log',timeout=60)
        if result['exit_code']:raise RuntimeError('Provengo sample help failed')
        help_text=(root/'sample-help.log').read_text(errors='replace')
        length='--max-length' if '--max-length' in help_text else '--max-depth' if '--max-depth' in help_text else None
        if not length:raise RuntimeError('No recognized native sampling length flag')
        timing['preparation_seconds']=time.perf_counter()-prep
        sample,generated=core.batched_sample(args.java,jar,root,root/'model',10,length,5)
        timing['sampling_native_seconds']=generated['wall_seconds']
        immutable={str(path):core.sha(path) for path,_ in sample}
        def verify():
            if any(core.sha(Path(path))!=digest for path,digest in immutable.items()):raise RuntimeError('Saved sample changed')
        verify()
        control=core.replay(args.java,jar,root,sample,10,'control','none')
        timing['control_validation_seconds']=control['wall_seconds']
        if control['native_nonzero_count'] or control['semantic_candidates'] or not control['successful_dependent_creations']:
            raise RuntimeError('New sample failed control validation; no mutant replay started')
        for arm,bugs in ARMS.items():
            verify()
            outcome=core.replay(args.java,jar,root,sample,10,arm,bugs)
            timing[arm+'_replay_seconds']=outcome['wall_seconds']
            timing[arm+'_sampling_plus_replay_seconds']=timing['sampling_native_seconds']+outcome['wall_seconds']
            summary[arm]={'bugs':bugs,'sample_size':10,'native_nonzero_count':outcome['native_nonzero_count'],**counts(root/arm)}
            core.write(root/'results.json',summary)
        timing['combined_sampling_plus_two_arms_seconds']=timing['sampling_native_seconds']+sum(timing[arm+'_replay_seconds'] for arm in ARMS)
        timing['sample_charged_once_in_combined_total']=True
        timing['standalone_arm_totals_each_include_full_sampling_cost']=True
        core.write(root/'completed.json',{'complete':True,'same_saved_ten_in_both_arms':True})
    finally:
        timing['total_elapsed_before_packaging_seconds']=time.perf_counter()-started
        core.write(root/'timings.json',timing)
        archive=root.with_name(root.name+'-review.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts and 'products' not in p.relative_to(root).parts:
                    z.write(p,p.relative_to(root))
        print('V009_TIMINGS '+json.dumps(timing),flush=True)
        print('V009_REVIEW_ZIP '+str(archive),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference-campaign',type=Path,required=True)
    parser.add_argument('--jar',type=Path)
    parser.add_argument('--java',default='java')
    main(parser.parse_args())
