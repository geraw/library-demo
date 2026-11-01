"""Bounded diagnostic archive; complete evidence stays in the run directory."""
import argparse,json,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent

def pack(root, budget=32*1024*1024, per_file=512*1024):
 root=Path(root).resolve()
 output=root.with_name(root.name+'-compact-review.zip')
 inventory=[];used=0
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  files=sorted((p for p in root.rglob('*') if p.is_file()),key=lambda p:(p.name not in {'summary.json','failure.json','provenance.json'},str(p)))
  for p in files:
   rel=p.relative_to(root);size=p.stat().st_size
   row={'path':rel.as_posix(),'bytes':size,'included':'no'}
   eligible=p.suffix.lower() in {'.json','.log','.txt','.md','.yml','.yaml'} and not {'java-classes','products','node_modules','.venv-benchmark-v001','__pycache__'}.intersection(rel.parts)
   if eligible and used+min(size,per_file)<=budget:
    with p.open('rb') as f:
     if size>per_file:f.seek(-per_file,2)
     data=f.read(per_file)
    truncated=size>per_file
    name=rel.as_posix()+('.tail.txt' if truncated else '')
    z.writestr(name,data);used+=len(data);row['included']='tail' if truncated else 'full'
   inventory.append(row)
  z.writestr('COMPACT_MANIFEST.json',json.dumps({'scope':'DIAGNOSTIC_SUBSET_NOT_COMPLETE_EVIDENCE','source':str(root),'payload_budget_bytes':budget,'files':inventory},indent=2))
 print('COMPACT_REVIEW_ZIP '+str(output),flush=True)
 print('SIZE_MB '+str(round(output.stat().st_size/1024/1024,2)),flush=True)
 return output

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path);p.add_argument('--latest',action='store_true');a=p.parse_args()
 if a.latest:
  runs=[d for d in (HERE/'runs').glob('benchmark-v001-*') if d.is_dir()]
  if not runs:p.error('No benchmark run directories found')
  a.run=max(runs,key=lambda d:d.stat().st_mtime)
 if not a.run or not a.run.is_dir():p.error('Supply --latest or --run EXISTING_DIRECTORY')
 pack(a.run)
