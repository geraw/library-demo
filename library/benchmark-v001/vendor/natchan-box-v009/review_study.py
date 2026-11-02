"""Replay available study packages with the public journal adapter and exact contract hashes.
System names select source contracts only, never semantic rules.
"""
import sys,json,hashlib
from pathlib import Path
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parent))
from review_stories import run
ap=argparse.ArgumentParser();ap.add_argument('--study-root',type=Path,required=True);ap.add_argument('--cycle5-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
root=args.study_root;c5=args.cycle5_root;out=args.output
if out.exists():raise SystemExit('Use a new output directory')
out.mkdir(parents=True)
contracts={'mealie':'mealie-contract.json','wger':'cycles/1-wger/config/contract.json','tandoor':'cycles/2-tandoor/config/tandoor-openapi.2.7.2.json','kimai':'cycles/3-kimai/config/kimai-openapi.2.70.0.json','dtrack':'cycles/4-dtrack/config/dtrack-openapi.5.2.1.json','vikunja':'toolkit/v2.7/configs/vikunja/contract.json','gitea':'toolkit/v2.7/configs/gitea/contract.json'}
cases=[(p.parent,root/contracts[p.parent.name.split('-')[0]]) for p in sorted((root/'results').glob('*/result_stories.json')) if p.parent.name.split('-')[0] in contracts and (p.parent/'gateway-journal.jsonl').is_file()]
cases +=[(p,c5/'config/labelstudio-openapi.json') for p in sorted(c5.glob('labelstudio-*')) if p.is_dir()]
reports=[]
for folder,contract in cases:
 try:
  result=json.loads((folder/'result_stories.json').read_text());cb=contract.read_bytes();expected=result.get('contract_sha256')
  if expected and hashlib.sha256(cb).hexdigest()!=expected:
   if hashlib.sha256(cb.rstrip(b'\n')).hexdigest()!=expected:raise ValueError('Contract mismatch')
   cp=out/(folder.name+'-contract.json');cp.write_bytes(cb.rstrip(b'\n'));contract=cp
  report=run(folder,contract,out/folder.name);coverage=json.loads((out/folder.name/'analysis/coverage.json').read_text())
  record={'run':folder.name,'journal_sha256':report['journal_sha256'],'contract_sha256':report['contract_sha256'],'exchanges':coverage['exchanges'],'ingestion':coverage['ingestion'],'partitions':coverage['finding_partitions'],'producer':report['producer']}
 except Exception as e:record={'run':folder.name,'error':str(e)}
 reports.append(record);print(folder.name,record.get('exchanges'),record.get('partitions'),record.get('error'),flush=True)
(out/'summary.json').write_text(json.dumps(reports,indent=2)+'\n')

raise SystemExit(1 if any("error" in r for r in reports) else 0)
