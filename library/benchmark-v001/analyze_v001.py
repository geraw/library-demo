"""Run a separate Library oracle and a frozen independent Natchan >=009 engine."""
import argparse,json,re,subprocess,sys
from pathlib import Path
from oracle_v001 import evaluate,read_trace
HERE=Path(__file__).resolve().parent

def write(path,data):Path(path).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def checked(command,folder,name):
 p=subprocess.run(list(map(str,command)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (folder/(name+'.log')).write_text(p.stdout,encoding='utf-8')
 if p.returncode:raise RuntimeError(name+' failed: '+p.stdout[-1000:])

def freeze(contract,engine,out):
 out.mkdir(parents=True,exist_ok=True)
 common=(engine/'common.py').read_text(encoding='utf-8');m=re.search(r"VERSION\s*=\s*['\"]([^'\"]+)",common)
 if not m or not re.match(r'0*(9|[1-9][0-9]+)(?:[-.]|$)',m[1]):raise RuntimeError('Natchan version >=009 required')
 checked([sys.executable,engine/'natchan.py','derive','--contract',contract,'--output',out/'knowledge.json'],out,'derive')
 checked([sys.executable,engine/'natchan.py','freeze','--contract',contract,'--knowledge',out/'knowledge.json','--output',out/'freeze.json'],out,'freeze')
 write(out/'engine-version.json',{'version':m[1],'path':str(engine)})

def analyze(folder,contract,engine,frozen,scope):
 rows=read_trace(folder/'http.jsonl');oracle=evaluate(rows,scope);write(folder/'oracle.json',oracle)
 # Whitelist raw exchanges only; no boundary flags, native outcomes or oracle outputs.
 traffic=folder/'natchan-traffic.jsonl'
 allowed={'method','url','status','input','response','request_id','case_id','epoch','actor','started_utc','ended_utc','observed_utc','request_headers','response_headers'}
 with traffic.open('w',encoding='utf-8') as f:
  for row in rows:
   if row.get('role')=='tool':f.write(json.dumps({k:row[k] for k in allowed if k in row})+'\n')
 request={'schema_version':'natchan-semantic-request/1','run':{'id':'library-observation','product':'library-benchmark','product_version':'v001','tool':'captured-http','start_state':'fresh_snapshot'},'contract':str(contract.resolve()),'knowledge':str((frozen/'knowledge.json').resolve()),'freeze':str((frozen/'freeze.json').resolve()),'evidence':{'format':'http-jsonl','traffic':str(traffic.resolve()),'capture':{'complete':True,'exclusive':True,'ordering':'serial'}}}
 write(folder/'natchan-request.json',request)
 checked([sys.executable,engine/'natchan.py','analyze','--request',folder/'natchan-request.json','--output',folder/'natchan-result'],folder,'natchan')
 return oracle

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--contract',type=Path,default=HERE/'openapi.json');p.add_argument('--engine',type=Path,default=HERE/'vendor/natchan-box-v009');p.add_argument('--scope',choices=['sequence-local','campaign-diagnostic'],default='sequence-local');a=p.parse_args()
 f=a.folder/'analysis-freeze';freeze(a.contract,a.engine,f);analyze(a.folder,a.contract,a.engine,f,a.scope)
