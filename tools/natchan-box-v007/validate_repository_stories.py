"""Offline, pinned evidence-subset reanalysis. Does not start a SUT or use NOTE.md."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
PRODUCER_COMMIT='62ff20a9da589e3b4ac18189e6f8f7f46f4ccde8'
CASES=['gitea-stories-20261026-214605', 'gitea-stories-20261026-214948', 'gitea-v2reg-20261026-232345', 'mealie-pg-stories-20261026-180615', 'mealie-stories-20261026-152627', 'mealie-stories-20261026-155056', 'mealie-stories-20261026-155119', 'mealie-stories-20261026-160113', 'mealie-stories-20261026-160850', 'mealie-stories-20261026-174809', 'mealie-stories-20261026-185652', 'mealie-v2reg-20261026-233607', 'vikunja-stories-20261026-203334', 'vikunja-stories-20261026-205024', 'vikunja-stories-20261026-210546', 'vikunja-stories-20261026-210902', 'vikunja-stories-20261026-213955', 'vikunja-stories-20261026-214347', 'vikunja-v2reg-20261026-232251', 'wger-stories-20261026-162150', 'wger-stories-20261026-163108', 'wger-stories-20261026-173331', 'wger-stories-20261026-181318', 'wger-stories-20261026-181911', 'wger-stories-20261026-182700', 'wger-stories-20261026-183640', 'wger-stories-20261026-204904', 'wger-stories-20261026-205327', 'wger-v2reg-20261026-230849']


def git(repo,*args):
    return subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout


def validate_case(name,files,output):
    archive=output/(name+'-repository-subset.zip')
    inventory=[]
    with zipfile.ZipFile(archive,'w') as z:
        for member,raw in sorted(files.items()):
            info=zipfile.ZipInfo(member,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            z.writestr(info,raw)
            blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            inventory.append(dict(path='results/'+name+'/'+member,git_blob_sha1=blob,sha256=hashlib.sha256(raw).hexdigest()))
    product=json.loads(files['result_stories.json'].decode('utf-8-sig'))['sut']
    aliases=json.loads((ROOT/'story_profiles.json').read_text())['product_aliases']
    product=aliases.get(product,product)
    request=output/(name+'.request.json')
    request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id=name,tool='provengo' if json.loads(files['result_stories.json'].decode('utf-8-sig')).get('runner')=='provengo' else 'story-harness',product=product,product_version='unknown'),evidence=dict(adapter='toolkit-v1',archive=archive.name)),indent=2)+'\n',encoding='utf-8')
    target=output/(name+'-analysis')
    run=subprocess.run([sys.executable,str(ROOT/'natchan.py'),'--request',str(request),'--output',str(target)],capture_output=True,text=True)
    if run.returncode:raise RuntimeError(f'Analysis failed for {name}, exit {run.returncode}; inspect {target}')
    a=json.loads((target/'analysis.json').read_text());r=json.loads((target/'result.json').read_text())
    return dict(case=name,source_repository='weissye/vikunja_study',source_commit=PRODUCER_COMMIT,
        input_kind='repository-retained-evidence-subset; NOT original uploaded ZIP',
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),source_members=inventory,
        exit_code=run.returncode,status=r['status'],counts=r['counts'],evidence_summary=a['evidence_summary'],
        semantic_comparisons=[dict(source_member=o['source']['members'],record=o['source'].get('record'),checks=o['story_semantic_checks']) for o in a['observations'] if o.get('story_semantic_checks')],
        rule_occurrences=a['rule_occurrences'],behavior_candidates=dict(Counter(c['candidate_id'] for c in a['story_known_bug_candidates'])),
        evidence_tiers=dict(Counter(o.get('evidence_tier') for o in a['observations'])),
        coverage_gaps=dict(Counter(g['code'] for g in a['toolkit_coverage_gaps'])),
        observed_versions=sorted({str(x.get('version')) for x in a['runs']}),
        original_user_zip_tested=False,new_sut_requests=a['new_sut_requests'],analyst_narrative_used=a['analyst_narrative_used'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    git(args.producer_repo,'cat-file','-e',PRODUCER_COMMIT+'^{commit}')
    args.output.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for name in CASES:
        prefix='results/'+name+'/'
        paths=git(args.producer_repo,'ls-tree','-r','--name-only',PRODUCER_COMMIT,'--',prefix).decode().splitlines()
        paths=[s for s in paths if s.endswith(('/result_stories.json','/gateway-journal.jsonl','/native.log'))]
        files={s[len(prefix):]:git(args.producer_repo,'show',PRODUCER_COMMIT+':'+s) for s in paths}
        if 'result_stories.json' not in files:raise RuntimeError('Pinned result evidence missing: '+name)
        summaries.append(validate_case(name,files,args.output))
        print(name,summaries[-1]['status'],summaries[-1]['behavior_candidates'])
    (args.output/'repository-reanalysis-summary.json').write_text(json.dumps(summaries,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
