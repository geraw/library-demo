"""Owned localhost gateway, serialized tool HTTP, complete raw exchange capture."""
import argparse,importlib.util,json,os,threading,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from flask import Flask,request,jsonify,Response
from werkzeug.serving import make_server

def stamp():return datetime.now(timezone.utc).isoformat()
def load_sut(path):
 spec=importlib.util.spec_from_file_location('managed_library',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.app.testing=False;return m

def app_factory(sut,trace,contract,token):
 m=load_sut(sut);client=m.app.test_client();gateway=Flask('library-benchmark');state={'case':None,'epoch':None,'order':0};lock=threading.RLock()
 def write(row):
  with open(trace,'a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=True)+'\n')
 @gateway.route('/__bench__/health')
 def health():return jsonify({'token':token,'version':'v001','pid':os.getpid()})
 @gateway.route('/__bench__/case',methods=['POST'])
 @gateway.route('/__campaign__/case',methods=['POST'])
 def boundary():
  # Control route: not in OpenAPI; harness owns and records all resets.
  if request.headers.get('X-Bench-Token')!=token:return '',403
  data=request.get_json(silent=True) or {};case=str(data.get('case',uuid.uuid4().hex))
  with lock:
   r=client.post('/reset',json={});empty=r.status_code==200 and all(client.get('/'+e).json==[] for e in ['users','books','loans','holds'])
   if not empty:return jsonify({'error':'Reset verification failed'}),500
   state.update(case=case,epoch=uuid.uuid4().hex,order=0)
   write({'role':'boundary','case_id':case,'epoch':state['epoch'],'empty_verified':True,'t_utc':stamp()})
  return jsonify({'case_id':case,'epoch':state['epoch'],'empty_verified':True})
 @gateway.route('/openapi.json')
 def schema():return Response(Path(contract).read_text(),content_type='application/json')
 @gateway.route('/',defaults={'path':''},methods=['GET','POST','DELETE','PUT','PATCH','OPTIONS','HEAD'])
 @gateway.route('/<path:path>',methods=['GET','POST','DELETE','PUT','PATCH','OPTIONS','HEAD'])
 def forward(path):
  if path=='reset' or path.startswith('__'):return '',403
  with lock:
   if state['case'] is None:return jsonify({'error':'Case not initialized'}),503
   state['order']+=1;rid='r'+str(state['order'])+'-'+uuid.uuid4().hex[:12];started=stamp()
   raw=request.get_data();headers={k:v for k,v in request.headers if k.lower() not in ['host','content-length','connection']}
   target='/'+path+('?' + request.query_string.decode('latin1') if request.query_string else '')
   r=client.open(target,method=request.method,data=raw,headers=headers)
   ended=stamp();response=r.get_json(silent=True)
   if response is None and r.data:response=r.data.decode('utf-8',errors='replace')
   payload=request.get_json(silent=True)
   if payload is None and raw:payload=raw.decode('utf-8',errors='replace')
   write({'role':'tool','method':request.method,'url':request.url,'status':r.status_code,'input':payload,'response':response,'request_id':rid,'case_id':state['case'],'epoch':state['epoch'],'actor':'single-test-client','order':state['order'],'started_utc':started,'ended_utc':ended,'observed_utc':ended,'request_headers':{'content-type':request.content_type or ''},'response_headers':{k.lower():v for k,v in r.headers if k.lower() in ['content-type','location']}})
   out=Response(r.data,status=r.status_code)
   for k,v in r.headers:
    if k.lower() not in ['content-length','connection','transfer-encoding']:out.headers[k]=v
   return out
 return gateway

def main():
 p=argparse.ArgumentParser();p.add_argument('--sut',type=Path,required=True);p.add_argument('--trace',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--port',type=int,default=23443);a=p.parse_args()
 token=os.environ['BENCH_SERVICE_TOKEN'];a.trace.parent.mkdir(parents=True,exist_ok=True)
 if a.trace.exists():raise RuntimeError('Trace already exists')
 make_server('127.0.0.1',a.port,app_factory(a.sut,a.trace,a.contract,token),threaded=False).serve_forever()
if __name__=='__main__':main()
