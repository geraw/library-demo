"""Prepare/verify a scientific configuration freeze; does not inspect run evidence."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
DEPENDENCIES=['natchan-v003','natchan-v004','natchan-v005','natchan-v006','natchan-v008','natchan-v011','natchan-v014','natchan-v015','natchan-v016',ROOT.name]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def engine_files():
    out=[]
    for name in DEPENDENCIES:
        for p in sorted((ROOT.parent/name).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and (p.suffix=='.py' or (p.suffix=='.json' and (p.parent.name in ('catalogs','semantics','profiles') or p.name in ('story_catalog.json','story_profiles.json')))):
                out.append(dict(path=p.relative_to(REPO).as_posix(),sha256=sha(p)))
    return out


def create(profiles=()):
    return dict(schema_version='natchan-evaluation-freeze/1',created_utc=datetime.now(timezone.utc).isoformat(),code=engine_files(),
        allowed_semantic_profiles=sorted({sha(p) for p in [*(ROOT/'semantics').glob('*.json'),*map(Path,profiles)]}),
        scope='Mechanical code/profile freeze only. This file neither proves chronological preregistration nor that evidence is unseen.',held_out_validation_performed=False)


def verify(manifest,profile_hashes=()):
    if manifest.get('schema_version')!='natchan-evaluation-freeze/1':raise ValueError('Unsupported evaluation freeze schema')
    current=engine_files()
    if current!=manifest.get('code'):raise ValueError('Evaluation freeze code/rule drift')
    allowed=manifest.get('allowed_semantic_profiles',[])
    if any(h not in allowed for h in profile_hashes):raise ValueError('Semantic profile was not registered in the evaluation freeze')
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--semantic-profile',type=Path,action='append',default=[]);a=p.parse_args()
    if a.output.exists():raise SystemExit('Freeze destination already exists')
    a.output.write_text(json.dumps(create(a.semantic_profile),indent=2)+'\n');print('EVALUATION_FREEZE '+str(a.output))

if __name__=='__main__':main()
