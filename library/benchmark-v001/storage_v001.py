"""Bounded storage checks and lossless archival of closed Provengo databases."""
import gzip,hashlib,os,shutil
from pathlib import Path

def check_space(folder,minimum=2*1024**3):
 free=shutil.disk_usage(folder).free
 if free<minimum:raise RuntimeError('LOW_DISK_SPACE: '+str(free)+' bytes free; stopping before disk exhaustion')

def archive_database(model,output):
 # Caller must have waited for the owning JVM to exit.
 internal=Path(model)/'products/internal'
 if not internal.exists():return
 output=Path(output);output.mkdir(parents=True,exist_ok=True)
 for source in sorted(internal.glob('runs-db*')):
  if not source.is_file():continue
  target=output/(source.name+'.gz')
  if target.exists():raise RuntimeError('Refusing to overwrite database archive '+str(target))
  original=hashlib.sha256()
  with source.open('rb') as src,gzip.open(target,'wb',compresslevel=6) as dst:
   while chunk:=src.read(1024*1024):original.update(chunk);dst.write(chunk)
  restored=hashlib.sha256()
  with gzip.open(target,'rb') as src:
   while chunk:=src.read(1024*1024):restored.update(chunk)
  if original.digest()!=restored.digest():raise RuntimeError('Database archive verification failed')
  source.unlink()
  print('DATABASE_ARCHIVED '+str(target),flush=True)


def discard_database(model,folder,case):
 import json
 folder=Path(folder);stem='case-'+str(case).zfill(2)
 required=[folder/(stem+'.log'),folder/(stem+'-execution.json'),folder/'http.jsonl',folder/'case-progress.json']
 if not all(p.is_file() and p.stat().st_size for p in required):
  raise RuntimeError('Refusing database removal: required case evidence missing')
 log=(folder/(stem+'.log')).read_text(encoding='utf-8',errors='replace')
 rows=[]
 for source in sorted((Path(model)/'products/internal').glob('runs-db*')):
  if not source.is_file():continue
  h=hashlib.sha256()
  with source.open('rb') as stream:
   while chunk:=stream.read(1024*1024):h.update(chunk)
  rows.append({'name':source.name,'bytes':source.stat().st_size,'sha256':h.hexdigest()})
 record={'case':case,'policy':'discard_closed_database_after_external_evidence_capture',
         'native_result_lines':[line for line in log.splitlines() if 'Test Result:' in line or 'FAIL:' in line],
         'execution':json.loads((folder/(stem+'-execution.json')).read_text()),
         'retained_evidence':[p.name for p in required],'databases':rows,
         'limitation':'Internal Provengo database and native HTML report reconstruction are not retained.'}
 (folder/(stem+'-retention.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
 for row in rows:(Path(model)/'products/internal'/row['name']).unlink()
