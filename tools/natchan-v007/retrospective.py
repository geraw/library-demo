"""Offline backward audit: original receipts and isolated historical regressions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/natchan-v005'))
from coverage_classifier import classify
CATALOG=ROOT/'tools/natchan-v006/catalogs'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(args):
    result=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,capture_output=True,text=True)
    return dict(exit_code=result.returncode,output=(result.stdout+result.stderr)[-6000:])

def audit(history,output):
    output.mkdir(parents=True,exist_ok=False)
    archive=history/'sources/Mealie_Supervisor_Artifact_v003.zip'
    mealie_path=output/'mealie-original.json'
    execution=run([ROOT/'tools/natchan-v003/review_mealie.py','--archive',archive,'--output',mealie_path])
    if execution['exit_code']:raise RuntimeError(execution['output'])
    original=json.loads(mealie_path.read_text())
    updated=classify(original['observations'],CATALOG)
    (output/'mealie-updated.json').write_text(json.dumps(updated,indent=2)+'\n')
    old_counts=Counter(x for _,x in {(a['observation_id'],x) for a in original['assessments'] for x in a.get('patterns',[])})
    new_counts=Counter(x for _,x in {(a['observation_id'],x) for a in updated['assessments'] for x in a.get('patterns',[])})
    suites=[('shared-historical-profiles',ROOT/'tools/semantic-checker-v001/tests')]
    for folder,test in [('immich_prefix_evaluator_rc2a_delta','test_causal_prefix.py'),
                        ('immich_concurrency_reevaluation_delta','test_concurrency_specific_oracle.py'),
                        ('mealie_evaluator_intervening_write_v0268_delta','test_intervening_write_verifier.py'),
                        ('openapi_sbt_empirical_evaluator_replay_delta','test_empirical_update_delete.py')]:
        suites.append((folder,history/'extracted'/folder/'tests'/test))
    regressions=[]
    for name,path in suites:
        regressions.append(dict(name=name,evidence_kind='code-regression-not-product-run',**run(['-m','pytest',path,'-q'] if name=='shared-historical-profiles' else [path])))
    inventory=[]
    for path in sorted((history/'sources').rglob('*.zip')):
        if not any(s in path.name.lower() for s in ['immich','keycloak','mealie']):continue
        with zipfile.ZipFile(path) as z:
            members=[n for n in z.namelist() if not n.endswith('/')]
            candidates=[n for n in members if any(t in n.lower() for t in ['receipt','http.json','trace.json','gateway-journal'])]
        inventory.append(dict(archive=str(path.relative_to(history)),sha256=digest(path),member_count=len(members),candidate_members=candidates,
                              interpretation='Filename inventory only; candidates are not validated HTTP evidence'))
    summary=dict(schema_version='natchan-retrospective/1',new_sut_executions=0,
                 classifier_catalog='natchan-v006',mealie=dict(archive_sha256=digest(archive),review=original['review'],
                 previous_labels=dict(old_counts),updated_labels=dict(new_counts),
                 boundary='16 server-error occurrences and four state-change witnesses; no named F04/F05 or new unique bug claim'),
                 regressions=regressions,archive_inventory=inventory,
                 limitations=['Historical unit tests do not establish raw-run support in the current classifier',
                              'Immich and Keycloak need original HTTP traces, matching manifests, controls and product adapters',
                              'Garage, Pharmacy, NetBox and historical Library retain frozen semantic profiles, not new generic adapters'])
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.history.resolve(),a.output.resolve())
    print(json.dumps(dict(mealie=r['mealie'],regressions=r['regressions']),indent=2))
