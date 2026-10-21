"""Check generated report parity and unchanged original input/code/catalog/profile bytes."""
from collections import Counter
import argparse,hashlib,json
from pathlib import Path
from render import view
from engine import ROOT

def verify(analysis_path,root):
 raw=analysis_path.read_bytes();d=json.loads(raw);_,_,rows=view(d)
 for item in d['input_inventory']+d['code_inventory']:
  if hashlib.sha256((root/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Input/code changed: '+item['path'])
 if any(Path(x['path']).suffix.lower()=='.md' for x in d['input_inventory']):raise ValueError('Manual Markdown source')
 if hashlib.sha256((ROOT/'profiles.json').read_bytes()).hexdigest()!=d['profile_sha256']:raise ValueError('Profile changed')
 if hashlib.sha256((ROOT/'source-resolution.json').read_bytes()).hexdigest()!=d['repository_resolution']['resolution_sha256']:raise ValueError('Repository mapping changed')
 v=json.loads((analysis_path.parent/'report-view.json').read_text())
 if v['analysis_sha256']!=hashlib.sha256(raw).hexdigest() or v['rows']!=rows:raise ValueError('Report-view mismatch')
 pairs=[(x['catalog_id'],x['observation_id']) for x in d['finding_records']]
 if len(pairs)!=len(set(pairs)):raise ValueError('Duplicate finding occurrence')
 if dict(Counter(x[0] for x in pairs))!=d['rule_occurrences']:raise ValueError('Count mismatch')
 return dict(status='PASS',checks=['source_hashes','code_hashes','catalog_hashes','profile_hash','no_markdown_inputs','unique_findings','report_view_exact_parity'],finding_occurrences=len(pairs),rule_count=len(rows),new_sut_requests=d['new_sut_requests'])

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('analysis',type=Path);p.add_argument('--root',type=Path,required=True);a=p.parse_args();print(json.dumps(verify(a.analysis,a.root.resolve()),indent=2))
