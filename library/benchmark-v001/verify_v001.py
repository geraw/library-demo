"""Directed real-HTTP ground truth checks, explicitly separate from tool discovery."""
import argparse,json,sys,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from types import SimpleNamespace
from campaign_v001 import Service
from analyze_v001 import freeze,analyze,write
sys.path.insert(0,str(Path(__file__).resolve().parent/'tests'))
from test_benchmark_v001 import scenario
HERE=Path(__file__).resolve().parent
class Client:
 def __init__(self,base):self.base=base
 def open(self,path,method='GET',json=None):
  payload=__import__('json').dumps(json).encode() if json is not None else None
  try:r=urlopen(Request(self.base+path,data=payload,method=method,headers={'Content-Type':'application/json'}),timeout=20)
  except HTTPError as e:r=e
  with r:
   raw=r.read()
   try:body=__import__('json').loads(raw)
   except ValueError:body=None
   return SimpleNamespace(status_code=r.status,json=body,data=raw)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=23443);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 engine=HERE/'vendor/natchan-box-v009';f=a.output/'frozen';freeze(HERE/'openapi.json',engine,f);checks=[]
 for bug in ['B1','B2','B3','B4','B5','B6']:
  for arm in ['none',bug]:
   cell=a.output/(bug+'-'+arm);cell.mkdir()
   with Service(cell,HERE/'openapi.json',arm,a.port) as service:
    service.boundary('directed-validation');scenario(bug,Client(service.base))
   oracle=analyze(cell,HERE/'openapi.json',engine,f,'sequence-local');actual=oracle['confirmed_bug_ids'];passed=(not actual if arm=='none' else bug in actual)
   coverage=json.loads((cell/'natchan-result/coverage.json').read_text())
   checks.append({'target':bug,'arm':arm,'oracle_ids':actual,'passed':passed,'natchan_status':'PARTIAL','natchan_classes':coverage['classes']})
   print('DIRECTED_VERIFICATION '+bug+' '+arm+' '+str(passed),flush=True)
 report={'status':'PASS' if all(c['passed'] for c in checks) else 'FAIL','kind':'DIRECTED_GROUND_TRUTH_ONLY_NOT_TOOL_DISCOVERY','cells':len(checks),'checks':checks,'native_configurations_executed':[]}
 write(a.output/'verification.json',report)
 if report['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
