"""Run generic trap providers and the shared classifier on normalized measurements."""
import argparse
import json
import hashlib
from pathlib import Path
import sys
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v003'))
from coverage_classifier import classify
from providers import evaluate


def make_observation(probe,result):
    facts=dict(result['facts']);facts.update(entity=probe.get('entity'),operation=probe.get('operation'))
    kinds=set(facts.get('change_subtypes',{}).values())
    facts.update(truncation_observed='truncation' in kinds,normalization_candidate='normalization_candidate' in kinds,
                 field_drop_observed=bool(facts.get('dropped_fields')),time_change_observed='time_change' in kinds)
    if probe['family']=='EDGE-U' and probe.get('product')=='gitea' and probe.get('entity')=='organization' and probe.get('field')=='email':
        facts['same_email_value_pair_verified']=True
        facts['create_accepted_update_rejected']=200<=probe['create']['status']<300 and 400<=probe['update']['status']<500
        facts['update_status']=probe['update']['status']
    return dict(id=probe['id'],product=probe['product'],product_version=probe.get('product_version'),run_id=probe['run_id'],
                source=probe['source'],entity=probe.get('entity'),operation=probe.get('operation'),field=probe.get('field'),
                facts=facts,fact_basis='recomputed',status=probe.get('status'),producer='natchan-v005-trap-provider')


def analyze(document):
    schema=document.get('schema_version')
    if schema=='natchan-observations/1':return classify(document['observations'],ROOT/'catalogs')
    if schema=='natchan-analysis/1':
        # Isolate the preserved Library bridge's historic module names.
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'input.json';target=Path(temp)/'recomputed.json'
            source.write_text(json.dumps(document),encoding='utf-8')
            result=subprocess.run([sys.executable,str(ROOT.parent/'natchan-v003/classifier.py'),'--input',str(source),'--output',str(target)],capture_output=True,text=True)
            if result.returncode:raise ValueError('Library bridge rejected input: '+result.stderr)
            fresh=json.loads(target.read_text(encoding='utf-8'))
        return classify(fresh['observations'],ROOT/'catalogs')
    if schema!='natchan-measurements/1':raise ValueError('Unsupported input schema; a tool/product gateway is required')
    observations=[];evaluations=[]
    for probe in document['measurements']:
        for key in ['id','product','product_version','run_id','source']:
            if key not in probe:raise ValueError('Missing measurement metadata '+key)
        result=evaluate(probe);result['id']=probe['id'];evaluations.append(result)
        if result['status']!='evaluated':continue
        observations.append(make_observation(probe,result))
    report=classify(observations,ROOT/'catalogs')
    report['provider_evaluations']=evaluations
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    result=analyze(json.loads(a.input.read_text(encoding='utf-8-sig')))
    result['input_sha256']=hashlib.sha256(a.input.read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('NATCHAN_MEASUREMENTS_COMPLETE '+str(a.output.resolve()))
