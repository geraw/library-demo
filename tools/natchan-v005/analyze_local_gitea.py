"""Analyze complete original Gitea run folders still present on the user's machine.

Reads files only. Does not start the server, replay requests or alter run artifacts.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v004'))
import analyze as baseline
from tse_gateways import digest
from coverage_classifier import classify
from analyze_coverage import augment_gitea


def analyze(root,version=None):
    if root.resolve()==Path(root.anchor):raise ValueError('Choose a study/runs directory, not an entire filesystem')
    observations=[];inputs=[];skipped=[];scanned=0
    for folder,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d not in ('.git','.venv','node_modules','__pycache__')]
        scanned+=len(files)
        if scanned>50000:raise ValueError('Scan limit exceeded; choose a narrower runs directory')
        if 'gateway-journal.jsonl' not in files:continue
        directory=Path(folder);journal=directory/'gateway-journal.jsonl';ir_path=directory/'generated/contract-ir.json'
        if not ir_path.exists():skipped.append({'folder':str(directory),'reason':'original IR missing'});continue
        if journal.stat().st_size>64*1024*1024:raise ValueError('Journal exceeds 64 MiB')
        raw=journal.read_bytes();ir_raw=ir_path.read_bytes();ir=json.loads(ir_raw)
        title=str(ir.get('document',{}).get('info',{}).get('title',''))
        if title and 'gitea' not in title.lower():
            skipped.append({'folder':str(directory),'reason':'IR identifies another product: '+title});continue
        meta={}
        native_paths=sorted(directory.glob('result*.json'))
        if len(native_paths)==1:meta=json.loads(native_paths[0].read_text(encoding='utf-8-sig'))
        actual_version=version or meta.get('sut_version') or ir.get('source',{}).get('version')
        if not actual_version:skipped.append({'folder':str(directory),'reason':'product version missing; supply --product-version'});continue
        rows=[json.loads(s) for s in raw.decode('utf-8-sig').splitlines() if s.strip()]
        log_path=directory/'sut.log'
        logs=log_path.read_text(encoding='utf-8-sig') if log_path.exists() else ''
        rid='local-'+digest(str(directory.resolve()).encode())[:12]
        source={'file':str(journal),'sha256':digest(raw),'IR_file':str(ir_path),'IR_sha256':digest(ir_raw)}
        if log_path.exists():source.update(log_file=str(log_path),log_sha256=digest(log_path.read_bytes()))
        run=dict(id=rid,product='gitea',version=str(actual_version).lstrip('v'),tool='recorded-http; native attribution not inferred',source=source)
        obs,oracles=baseline.gitea_observations(run,{'records':rows,'ir':ir,'sut_log':logs})
        augment_gitea(obs,rows);observations.extend(obs)
        inputs.append({'source':source,'run_id':rid,'original_native_summary':meta,'original_oracle_records':len(oracles)})
    report=classify(observations,ROOT/'catalogs')
    report.update(inputs=inputs,skipped=skipped,new_sut_calls=0)
    if not inputs:report['status']='NO_EVALUABLE_INPUTS'
    else:report['status']='ANALYZED'
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--product-version');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    report=analyze(a.root,a.product_version);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('NATCHAN_LOCAL_GITEA '+report['status'])
    raise SystemExit(0 if report['status']=='ANALYZED' else 2)
