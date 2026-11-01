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
