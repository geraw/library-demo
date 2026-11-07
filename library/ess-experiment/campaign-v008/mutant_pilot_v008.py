"""Frozen unguided mutant pilot using the v007 contract and v007 control tool builds."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'campaign-v006'))
import pilot_v006 as baseline


def inputs(control):
    control=control.resolve()
    for name in ('openapi.json','sut_buggy_issta.py'):
        if not (control/name).is_file():raise RuntimeError('Missing control input: '+str(control/name))
    candidates=list(control.glob('baselines-all-v006-*/provenance.json'))
    if len(candidates)!=1:raise RuntimeError('Expected one native baseline provenance file in the v007 control directory')
    provenance=json.loads(candidates[0].read_text())
    if provenance['bugs']!='none':raise RuntimeError('Expected an unmutated v007 control campaign')
    for name,key in [('openapi.json','contract_sha256'),('sut_buggy_issta.py','sut_sha256')]:
        if baseline.core.sha(control/name)!=provenance[key]:raise RuntimeError('Control input hash changed: '+name)
    for key in ('evomaster','restler'):
        path=Path(provenance['evomaster_jar' if key=='evomaster' else 'restler'])
        if not path.is_file():raise RuntimeError('Frozen tool installation is missing: '+str(path))
        if baseline.core.sha(path)!=provenance[key+'_sha256']:raise RuntimeError('Frozen tool binary changed: '+str(path))
    config=json.loads((candidates[0].parent/'restler/Compile/config.json').read_text())
    if config.get('ResolveBodyDependencies') is not True or config.get('ResolveQueryDependencies') is not True:
        raise RuntimeError('Control did not enable automatic body/query dependency inference')
    if config.get('AnnotationFilePath'):
        raise RuntimeError('Unexpected RESTler annotation file in control configuration')
    contract=json.loads((control/'openapi.json').read_text())
    packaged=json.loads((Path(__file__).resolve().parents[1]/'campaign-v007/library_openapi_v007.json').read_text())
    packaged['servers']=[{'url':'http://127.0.0.1:23243'}]
    if contract!=packaged:raise RuntimeError('Control contract differs from the neutral v007 contract')
    def no_guidance(value):
        if isinstance(value,dict):
            for key,child in value.items():
                if key in ('links','example','examples') or key.lower().startswith('x-restler'):
                    raise RuntimeError('Guidance field in contract: '+key)
                no_guidance(child)
        elif isinstance(value,list):
            for child in value:no_guidance(child)
    no_guidance(contract)
    return control,provenance,candidates[0].parent


def main(args):
    control,provenance,native_control=inputs(args.control_campaign)
    root=control.parent/('mutants-neutral-v008-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
    root.mkdir()
    for name in ('openapi.json','sut_buggy_issta.py'):shutil.copy2(control/name,root/name)
    shutil.copy2(Path(__file__).parent/'AUTOMATIC_CONFIG_AUDIT_v008.md',root/'automatic-config-audit.md')
    baseline.core.write(root/'experiment.json',dict(
        version='v008',control_campaign=str(control),native_control=str(native_control),
        contract_sha256=baseline.core.sha(root/'openapi.json'),sut_sha256=baseline.core.sha(root/'sut_buggy_issta.py'),
        bugs=[1,2,3,4,5],seconds_per_tool=600,order=['restler','evomaster'],
        coverage_gate=False,manual_dependencies=False,tool_versions='Same binary hashes as v007 control',
        settings='Same native inference and fuzzing defaults as v007; only mutation activation and search duration change',
        findings='Native tool reports and campaign-global observer candidates must be reviewed separately'))
    baseline.BUGS='1,2,3,4,5'
    baseline.SECONDS=600
    print('V008_MUTANT_CAMPAIGN '+str(root),flush=True)
    print('V008_ALL_FIVE_BUGS_ENABLED; RESTLER_THEN_EVOMASTER; 600_SECONDS_EACH; NO_COVERAGE_GATE',flush=True)
    try:
        baseline.main(argparse.Namespace(campaign=root,evomaster_jar=Path(provenance['evomaster_jar']),
            restler=Path(provenance['restler']),tools='both',previous_pilot=None,install_local_tools=False))
    finally:
        target=root.with_name(root.name+'-review.zip')
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for path in root.rglob('*'):
                if path.is_file() and path.suffix!='.zip' and '__pycache__' not in path.parts:
                    z.write(path,path.relative_to(root))
        print('V008_REVIEW_ZIP '+str(target),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--control-campaign',type=Path,required=True)
    main(parser.parse_args())
