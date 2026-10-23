"""Preserved historical workers + v003 coverage-aware composition. Offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v014'))
from run import collect
from coverage_engine import analyze
from render import write_report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output already exists')
    raw=a.manifest.read_bytes();manifest=json.loads(raw)
    if manifest.get('schema_version')!='natchan-corpus/1':raise ValueError('Unsupported corpus schema')
    with tempfile.TemporaryDirectory(prefix='natchan-history-') as temporary:parts=collect(manifest,a.root.resolve(),Path(temporary))
    report=analyze(parts);report['corpus_sha256']=hashlib.sha256(raw).hexdigest()
    a.output.mkdir(parents=True);target=a.output/'analysis.json';target.write_text(json.dumps(report,ensure_ascii=False)+'\n',encoding='utf-8')
    write_report(target,a.output,create_pdf=False)
if __name__=='__main__':main()
