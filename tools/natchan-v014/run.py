"""One command: original artifacts -> common rules -> JSON/Markdown/PDF report."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from engine import analyze,ROOT

def collect(manifest,root,work):
 for item in manifest.get('locked_sources',[]):
  path=root/item['path']
  if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Original input changed: '+item['path'])
 ids=[x['id'] for x in manifest['datasets']]
 if len(ids)!=len(set(ids)):raise ValueError('Duplicate dataset ID')
 def one(pair):
  i,task=pair;target=work/(str(i)+'.json')
  result=subprocess.run([sys.executable,str(ROOT/'worker.py'),json.dumps(task),str(root),str(target)],capture_output=True,text=True)
  if result.returncode:raise RuntimeError(task['id']+' gateway failed:\n'+result.stderr[-6000:])
  return task['id'],json.loads(target.read_text())
 with ThreadPoolExecutor(max_workers=3) as pool:return list(pool.map(one,enumerate(manifest['datasets'])))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,default=ROOT/'corpus-v014.json');p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--pdf',action='store_true');a=p.parse_args()
 if a.output.exists():p.error('Output already exists')
 raw=a.manifest.read_bytes();manifest=json.loads(raw)
 if manifest.get('schema_version')!='natchan-corpus/1':raise ValueError('Unsupported corpus schema')
 with tempfile.TemporaryDirectory(prefix='natchan-raw-') as temp:parts=collect(manifest,a.root.resolve(),Path(temp))
 report=analyze(parts);report['corpus_sha256']=hashlib.sha256(raw).hexdigest()
 report['code_inventory']=[dict(path=str(f.relative_to(ROOT.parent.parent)),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for folder in [ROOT,*(ROOT.parent/x for x in ['natchan-v003','natchan-v004','natchan-v005','natchan-v006','natchan-v008','natchan-v011'])] for f in sorted(folder.glob('*.py'))]
 a.output.mkdir(parents=True);target=a.output/'analysis.json';target.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+'\n')
 print('NATCHAN_ANALYSIS_COMPLETE',target)
 try:
  from render import write_report
  write_report(target,a.output,create_pdf=a.pdf)
 except ModuleNotFoundError as e:
  if e.name=='render':raise
  raise RuntimeError('Install report dependencies; JSON has been preserved: '+str(e)) from e
 print('NATCHAN_REPORT_COMPLETE',a.output)
if __name__=='__main__':main()
