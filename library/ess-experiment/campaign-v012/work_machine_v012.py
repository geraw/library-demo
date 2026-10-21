"""Prepare exact frozen study inputs from Git and run v011 with the local JAR."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(bundle_path,jar,runs):
    bundle=json.loads(bundle_path.read_text(encoding='utf-8'))
    decoded={}
    for name,entry in bundle['files'].items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise RuntimeError('Invalid frozen input path: '+name)
        data=base64.b64decode(entry['base64'],validate=True)
        if sha(data)!=entry['sha256']:raise RuntimeError('Frozen input digest mismatch: '+name)
        decoded[name]=data
    required={'sut_buggy_issta.py','openapi.json','model_profile.json','environment.home-original.json'}
    if not required.issubset(decoded) or not any(n.startswith('model/') for n in decoded):
        raise RuntimeError('Incomplete frozen input bundle')
    if not jar.is_file():raise RuntimeError('Local Provengo JAR not found: '+str(jar))
    original=json.loads(decoded['environment.home-original.json'])
    local_hash=sha(jar.read_bytes())
    runs.mkdir(parents=True,exist_ok=True)
    reference=Path(tempfile.mkdtemp(prefix='work-reference-v012-',dir=runs))
    for name,data in decoded.items():
        target=reference/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    environment={'version':'v012-work-reference','provengo_jar':str(jar),
        'jar_sha256':local_hash,'configuration':'New work-machine configuration using the installed local JAR',
        'original_jar_sha256':original['jar_sha256']}
    provenance={'version':'v012','source_archive':bundle['source_archive'],
        'source_archive_sha256':bundle['source_archive_sha256'],
        'bundle_sha256':sha(bundle_path.read_bytes()),'original_jar_sha256':original['jar_sha256'],
        'local_jar_sha256':local_hash,'same_jar_as_home':local_hash==original['jar_sha256'],
        'model_and_sut':'Exact source-archive bytes; restored from Base64 to avoid Git newline conversion',
        'python':sys.version,'reference_directory':str(reference)}
    for name,value in [('environment.json',environment),('work-provenance.json',provenance)]:
        (reference/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    manifest={str(p.relative_to(reference)).replace('\\','/'):sha(p.read_bytes()) for p in reference.rglob('*') if p.is_file()}
    (reference/'input_hashes.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('WORK_REFERENCE '+str(reference),flush=True)
    print('LOCAL_PROVENGO_SHA256 '+local_hash,flush=True)
    print('SAME_JAR_AS_HOME '+str(provenance['same_jar_as_home']),flush=True)
    return reference


def main(args):
    campaign=Path(__file__).resolve().parent
    repo=campaign.parents[2]
    jar=args.jar.resolve()
    reference=prepare(campaign/'frozen_inputs_v012.json',jar,repo/'library/ess-experiment/runs')
    if args.prepare_only:
        print('WORK_PREPARE_V012_COMPLETE',flush=True);return
    runner=campaign.parent/'campaign-v011/java_suite_v011.py'
    command=[sys.executable,str(runner),'--reference-campaign',str(reference),'--jar',str(jar),
        '--java',args.java,'--case-timeout',str(args.case_timeout),'--arm-timeout',str(args.arm_timeout)]
    result=subprocess.run(command,cwd=repo)
    if result.returncode:raise SystemExit(result.returncode)
    print('WORK_RUN_V012_COMPLETE',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--jar',type=Path,required=True)
    parser.add_argument('--java',default='java')
    parser.add_argument('--case-timeout',type=int,default=120)
    parser.add_argument('--arm-timeout',type=int,default=7200)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    if args.case_timeout<=0 or args.arm_timeout<=0:parser.error('Timeouts must be positive')
    main(args)
