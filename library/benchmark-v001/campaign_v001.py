"""Four configurations, original rules, isolated mutants, two independent evaluators."""
import argparse,hashlib,json,os,re,secrets,shutil,signal,socket,subprocess,sys,time,uuid,zipfile
from pathlib import Path
from storage_v001 import check_space,archive_database
from urllib.request import Request,urlopen
from analyze_v001 import freeze,analyze,write
HERE=Path(__file__).resolve().parent
TOOLS=['evomaster','restler','provengo-sample10','provengo-java']
ARMS=['none','B1','B2','B3','B4','B5','B6']
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as stream:
  while chunk:=stream.read(1024*1024):h.update(chunk)
 return h.hexdigest()
def terminate(proc):
 if proc.poll() is not None:return
 if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 else:
  try:os.killpg(proc.pid,signal.SIGTERM)
  except ProcessLookupError:pass
 try:proc.wait(timeout=10)
 except subprocess.TimeoutExpired:
  if os.name!='nt':os.killpg(proc.pid,signal.SIGKILL)
  else:proc.kill()
  proc.wait(timeout=10)

def launch(command,folder,name,timeout,env=None,expected=(0,)):
 command=list(map(str,command));started=time.monotonic();folder.mkdir(parents=True,exist_ok=True)
 check_space(folder)
 write(folder/(name+'-command.json'),command)
 with (folder/(name+'.log')).open('w',encoding='utf-8') as log:
  proc=subprocess.Popen(command,cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
  deadline=started+timeout;next_notice=started+30;timed=False
  try:
   while proc.poll() is None:
    try:proc.wait(timeout=min(1,max(.01,deadline-time.monotonic())))
    except subprocess.TimeoutExpired:pass
    check_space(folder)
    now=time.monotonic()
    if now>=next_notice:print('PROGRESS '+name+' elapsed='+str(int(now-started))+'s',flush=True);next_notice=now+30
    if now>=deadline and proc.poll() is None:timed=True;terminate(proc)
  except BaseException:terminate(proc);raise
 result={'command':command,'exit_code':proc.returncode,'watchdog_timeout':timed,'wall_seconds':time.monotonic()-started,'expected_exit':proc.returncode in expected and not timed}
 write(folder/(name+'-execution.json'),result);return result

def require(result,folder,name):
 if not result['expected_exit']:raise RuntimeError(name+' failed; inspect '+str(folder/(name+'.log')))

def call(url,token=None,body=None):
 headers={'Content-Type':'application/json'}
 if token:headers['X-Bench-Token']=token
 req=Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 with urlopen(req,timeout=20) as r:return json.load(r)

class Service:
 def __init__(self,folder,contract,mutant,port):self.folder,self.contract,self.mutant,self.port=folder,contract,mutant,port
 def __enter__(self):
  with socket.socket() as sock:
   if sock.connect_ex(('127.0.0.1',self.port))==0:raise RuntimeError('Port '+str(self.port)+' is occupied; no existing server was stopped')
  self.token=secrets.token_hex(32);self.base='http://127.0.0.1:'+str(self.port)
  self.env=dict(os.environ,BENCH_SERVICE_TOKEN=self.token,LIBRARY_MUTATIONS=self.mutant)
  self.log=(self.folder/'server.log').open('w',encoding='utf-8')
  sut=HERE/('sut_baseline_v001.py' if self.mutant=='none' else 'sut_mutants_v001.py')
  self.proc=subprocess.Popen([sys.executable,str(HERE/'server_v001.py'),'--sut',str(sut),'--trace',str(self.folder/'http.jsonl'),'--contract',str(self.contract),'--port',str(self.port)],env=self.env,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
  try:
   for _ in range(150):
    if self.proc.poll() is not None:raise RuntimeError('Managed server failed; inspect server.log')
    try:
     info=call(self.base+'/__bench__/health')
     if info.get('token')!=self.token:raise RuntimeError('Listener identity mismatch')
     return self
    except OSError:time.sleep(.1)
   raise RuntimeError('Managed server did not become ready')
  except BaseException:self.__exit__(None,None,None);raise
 def boundary(self,case):return call(self.base+'/__bench__/case',self.token,{'case':str(case)})
 def __exit__(self,*_):terminate(self.proc);self.log.close()

def tool_config(path):
 d=json.loads(path.read_text(encoding='utf-8-sig'))
 managed=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ISSTA-tools-v006/manifest.json'
 if managed.is_file():
  m=json.loads(managed.read_text())
  d['evomaster_jar']=d.get('evomaster_jar') or m.get('evo','')
  d['restler']=d.get('restler') or m.get('restler','')
  for key,target in [('java_bin','java'),('dotnet_bin','dotnet')]:
   if m.get(key):
    f=Path(m[key])/('java.exe' if target=='java' else 'dotnet.exe')
    if f.is_file():d[target]=str(f)
  if m.get('python_bin'):d['restler_python_bin']=m['python_bin']
 return d

def prepare(root,config,port,seed):
 model=root/'model';shutil.copytree(HERE/'model',model)
 (model/'data/00_endpoint.js').write_text('var host="127.0.0.1"; var port='+str(port)+'; var BENCH_SEED='+str(seed)+';\n',encoding='utf-8')
 p=model/'spec/js/lib_stories.js';p.write_text(p.read_text().replace('new java.util.Random();','new java.util.Random(BENCH_SEED);'),encoding='utf-8')
 c=json.loads((HERE/'openapi.json').read_text());c['servers']=[{'url':'http://127.0.0.1:'+str(port)}];write(root/'openapi.json',c)
 engine=Path(config.get('analyzer_home') or HERE/'vendor/natchan-box-v009').resolve()
 freeze(root/'openapi.json',engine,root/'frozen-analyzer')
 provenance=json.loads((HERE/'PROVENANCE.json').read_text());provenance.update({'python':sys.version,'configurations':TOOLS,'seed':seed,'port':port,'analyzer_engine':str(engine),'budget_note':'Engine-specific budgets; sample generation, Java catalog execution and fuzzing are reported separately. Not a matched-time comparison.','semantic_scoring':'Tool-origin requests only. No oracle probes injected. Flat fuzzer traces remain campaign diagnostics.'})
 write(root/'provenance.json',provenance)
 write(root/'input-hashes.json',{str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*') if p.is_file() and not {'runs','__pycache__','.venv','.venv-benchmark-v001','setup-logs'}.intersection(p.relative_to(HERE).parts)})
 return model,engine

def preflight(root,cfg,tools):
 folder=root/'preflight';folder.mkdir();result={};java=cfg.get('java','java')
 for tool in tools:
  if tool=='evomaster':
   jar=Path(cfg.get('evomaster_jar',''))
   if not jar.is_file():raise RuntimeError('Set EvoMasterJar in Setup-Library-Benchmark-v001.ps1 or tools.local.json')
   r=launch([java,'-jar',jar,'--help'],folder,'evomaster-help',90);require(r,folder,'evomaster-help')
   help_=(folder/'evomaster-help.log').read_text(errors='replace')
   schema='--schema' if re.search(r'--schema\b',help_) else '--bbSwaggerUrl' if '--bbSwaggerUrl' in help_ else None
   base='--base' if re.search(r'--base\b',help_) else '--bbTargetUrl' if '--bbTargetUrl' in help_ else None
   if not schema or not base or '--maxTime' not in help_:raise RuntimeError('Unsupported EvoMaster CLI; inspect preflight help')
   result[tool]={'jar':str(jar.resolve()),'sha256':sha(jar),'schema_flag':schema,'base_flag':base}
  elif tool=='restler':
   binary=Path(cfg.get('restler',''))
   if not binary.is_file():raise RuntimeError('Set RestlerPath or use Setup -InstallNativeTools')
   driver=[str(binary.resolve())] if binary.suffix.lower()=='.exe' else [cfg.get('dotnet','dotnet'),str(binary.resolve())]
   r=launch(driver+['--help'],folder,'restler-help',90)
   # Some builds use an informational nonzero help exit; save it, then let compilation validate.
   result[tool]={'driver':driver,'sha256':sha(binary),'help_exit_code':r['exit_code']}
  else:
   jar=Path(cfg.get('provengo_jar',''))
   if not jar.is_file():raise RuntimeError('Provengo JAR missing; pass -ProvengoJar to Setup')
   if 'provengo' not in result:
    r=launch([java,'-jar',jar,'sample','-h'],folder,'provengo-sample-help',90);require(r,folder,'provengo-sample-help')
    help_=(folder/'provengo-sample-help.log').read_text(errors='replace')
    length=next((f for f in ['--max-length','--max-depth'] if f in help_),None)
    if not length:raise RuntimeError('Unsupported Provengo sample length option')
    result['provengo']={'jar':str(jar.resolve()),'sha256':sha(jar),'length_flag':length,'seed_flag':'--seed' if '--seed' in help_ else None}
 write(root/'native-tools.json',result);return result

def reuse_samples(source,root,model,meta):
 source=Path(source).resolve()
 manifest=json.loads((source/'sample10/manifest.json').read_text(encoding='utf-8-sig'))
 samples=manifest['samples']
 if len(samples)!=10 or {x['case'] for x in samples}!=set(range(1,11)):
  raise RuntimeError('Expected original ten sample cases')
 old=json.loads((source/'native-tools.json').read_text())
 if old['provengo']['sha256']!=meta['sha256']:raise RuntimeError('Provengo binary changed since sampling')
 if json.loads((source/'openapi.json').read_text())!=json.loads((root/'openapi.json').read_text()):raise RuntimeError('Contract/port differs from original run')
 resolved=[]
 for item in samples:
  path=source/'sample10'/('sample-'+str(item['case']).zfill(2)+'.json')
  if not path.is_file() or sha(path)!=item['sha256']:raise RuntimeError('Sample missing or changed: '+str(path))
  resolved.append(dict(item,file=str(path)))
 # Reuse the original model inputs, excluding its mutable products database.
 for name in ['config','data','lib','spec']:
  if (model/name).exists():shutil.rmtree(model/name)
  shutil.copytree(source/'model'/name,model/name)
 write(root/'reused-samples.json',{'source_run':str(source),'samples':resolved,'sha256_verified':True})
 return resolved

def sampling(root,cfg,meta,model,args):
 folder=root/'sample10';folder.mkdir();manifest=[]
 for index in range(1,11):
  out=folder/('sample-'+str(index).zfill(2)+'.json')
  command=[cfg.get('java','java'),'-Xmx2g','-jar',meta['jar'],'sample','--overwrite','--size','1',meta['length_flag'],str(args.max_length),'-o',out,model]
  if meta['seed_flag']:command += [meta['seed_flag'],str(args.seed+index-1)]
  print('SAMPLE '+str(index)+'/10',flush=True)
  r=launch(command,folder,'sample-'+str(index).zfill(2),args.sample_timeout);require(r,folder,'sample-'+str(index).zfill(2))
  data=json.loads(out.read_text(encoding='utf-8-sig'))
  seq=data if isinstance(data,list) else next((data[k] for k in ['scenarios','runs','samples'] if isinstance(data.get(k),list)),None)
  if seq is None or len(seq)!=1:raise RuntimeError('Native sample must contain exactly one scenario')
  manifest.append({'case':index,'file':str(out),'sha256':sha(out),'run_id':1,'generation_seconds':r['wall_seconds']})
 write(folder/'manifest.json',{'sample_size':10,'native_batch_size':1,'deduplicated':False,'note':'Ten sampled scenarios; duplicates, if present, are retained and visible. The same files are replayed on every arm.','samples':manifest})
 return manifest

def compile_java(root,cfg,meta):
 classes=root/'java-classes';classes.mkdir();folder=root/'java-preflight';folder.mkdir()
 sources=[HERE/'java'/x for x in ['StrictGuidedRun.java','V011Actuation.java','BenchmarkJavaV001.java']]
 r=launch([cfg.get('java','java'),'-m','jdk.compiler/com.sun.tools.javac.Main','-cp',meta['jar'],'-d',classes,*sources],folder,'compile',180);require(r,folder,'compile')
 cp=str(classes)+os.pathsep+meta['jar'];r=launch([cfg.get('java','java'),'-cp',cp,'BenchmarkJavaV001','--list'],folder,'catalog',60);require(r,folder,'catalog')
 if 'SCENARIO_COUNT=542' not in (folder/'catalog.log').read_text():raise RuntimeError('Frozen Java catalog count differs from 542')
 return cp

def java_transport_checks(root,cfg,cp,model,args):
 for negative in [False,True]:
  folder=root/('java-transport-negative' if negative else 'java-transport-positive');folder.mkdir()
  selected=model
  if negative:
   selected=root/'negative-self-check-model';shutil.copytree(model,selected)
   p=selected/'spec/js/interfaces.library.js';text=p.read_text()
   if 'expectedResponseCodes: [201]' not in text:raise RuntimeError('Negative self-check anchor missing')
   p.write_text(text.replace('expectedResponseCodes: [201]','expectedResponseCodes: [202]'))
  with Service(folder,root/'openapi.json','none',args.port) as service:
   env=dict(os.environ,BENCH_SERVICE_TOKEN=service.token)
   command=[cfg.get('java','java'),'-Xmx2g','-Dbench.base='+service.base,'-cp',cp,'BenchmarkJavaV001',selected,folder/'native.jsonl',str(args.case_timeout),'--smoke']
   result=launch(command,folder,'transport',args.case_timeout+30,env);require(result,folder,'transport')
  rows=[json.loads(line) for line in (folder/'native.jsonl').read_text().splitlines() if line.strip()]
  if len(rows)!=1:raise RuntimeError('Incomplete native Java transport self-check')
  if negative:
   if rows[0]['native_pass'] or not rows[0]['actuator_errors']:raise RuntimeError('Wrong-status native assertion was not detected')
  else:
   raw=[json.loads(line) for line in (folder/'http.jsonl').read_text().splitlines() if line.strip()]
   loans=[r for r in raw if r.get('role')=='tool' and r['method']=='POST' and '/loans'==__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(r['url']).path and r['status']==201]
   if not rows[0]['native_pass'] or len(loans)!=1:raise RuntimeError('Positive native RTV/loan transport self-check failed')
   if '@{' in json.dumps(loans[0]['input']):raise RuntimeError('Unresolved runtime variable in native request')
  write(folder/'self-check.json',{'passed':True,'negative_control':negative,'included_in_research_score':False})

def main(a):
 cfg=tool_config(a.config);tools=a.tools.split(',')
 if any(t not in TOOLS for t in tools) or len(set(tools))!=len(tools):raise ValueError('Unknown/duplicate configuration')
 root=a.output or HERE/'runs'/('benchmark-v001-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);root=root.resolve();root.mkdir(parents=True,exist_ok=False)
 print('RUN_DIRECTORY '+str(root),flush=True);results={};native={};error=None
 try:
  model,engine=prepare(root,cfg,a.port,a.seed)
  if a.prepare_only:write(root/'prepared.json',{'status':'PREPARED_NO_TOOL_EXECUTION'});return
  native=preflight(root,cfg,tools)
  samples=(reuse_samples(a.reuse_run,root,model,native['provengo']) if a.reuse_run else sampling(root,cfg,native['provengo'],model,a)) if 'provengo-sample10' in tools else None
  cp=compile_java(root,cfg,native['provengo']) if 'provengo-java' in tools else None
  if cp:java_transport_checks(root,cfg,cp,model,a)
  for tool in tools:
   for arm in a.arms.split(','):
    if arm not in ARMS:raise ValueError('Unknown isolated mutation arm')
    folder=root/tool/arm;folder.mkdir(parents=True);print('START '+tool+' '+arm,flush=True)
    scope='sequence-local' if tool.startswith('provengo') else 'campaign-diagnostic';outcomes=[]
    # Environment changes are local to child tools and the owned server.
    env=dict(os.environ)
    if cfg.get('restler_python_bin'):env['PATH']=cfg['restler_python_bin']+os.pathsep+env.get('PATH','')
    command=None
    if tool=='restler':
     driver=native[tool]['driver'];r=launch(driver+['compile','--api_spec',root/'openapi.json'],folder,'compile',180,env);require(r,folder,'compile')
     grammar=folder/'Compile/grammar.py';dictionary=folder/'Compile/dict.json'
     if not grammar.is_file() or not dictionary.is_file():raise RuntimeError('RESTler compiler outputs missing')
     settings={'target_ip':'127.0.0.1','target_port':a.port,'host':'127.0.0.1:'+str(a.port),'no_ssl':True,'time_budget':a.seconds/3600,'fuzzing_mode':'bfs-cheap','random_seed':a.seed,'garbage_collector_cleanup_time':5,'max_request_execution_time':10}
     if (folder/'Compile/grammar.json').is_file():settings['grammar_schema']=str(folder/'Compile/grammar.json')
     write(folder/'settings.json',settings);command=driver+['fuzz','--grammar_file',grammar,'--dictionary_file',dictionary,'--settings',folder/'settings.json','--no_ssl']
    elif tool=='evomaster':
     n=native[tool];command=[cfg.get('java','java'),'-jar',n['jar'],'--blackBox','true',n['schema_flag'],root/'openapi.json',n['base_flag'],'http://127.0.0.1:'+str(a.port),'--maxTime',str(a.seconds)+'s','--seed',str(a.seed),'--outputFolder',folder/'generated-tests']
    with Service(folder,root/'openapi.json',arm,a.port) as service:
     if command:
      service.boundary('fuzzer-campaign');outcomes.append(launch(command,folder,'native',a.seconds+120,env))
     elif tool=='provengo-sample10':
      for sample in samples:
       service.boundary(sample['case']);outcomes.append(launch([cfg.get('java','java'),'-Xmx2g','-jar',native['provengo']['jar'],'run','-s',sample['file'],'--run-id','1',model],folder,'case-'+str(sample['case']).zfill(2),a.case_timeout,env,expected=(0,1)))
       write(folder/'case-progress.json',outcomes)
       archive_database(model,folder/('database-case-'+str(sample['case']).zfill(2)))
     else:
      env['BENCH_SERVICE_TOKEN']=service.token
      command=[cfg.get('java','java'),'-Xmx2g','-Dbench.base='+service.base,'-Dbench.java.limit='+str(a.java_limit),'-cp',cp,'BenchmarkJavaV001',model,folder/'native.jsonl',str(a.case_timeout)]
      outcomes.append(launch(command,folder,'native',a.java_timeout,env))
    raw_rows=[json.loads(line) for line in (folder/'http.jsonl').read_text().splitlines() if line.strip()]
    if not any(r.get('role')=='tool' for r in raw_rows):raise RuntimeError('No actual tool HTTP requests; cell cannot be scored')
    if tool=='provengo-java':
     native_path=folder/'native.jsonl'
     count=len(native_path.read_text().splitlines()) if native_path.is_file() else 0
     expected=min(a.java_limit,542) if a.java_limit else 542
     if count!=expected:raise RuntimeError('Incomplete Java catalog execution: '+str(count)+'/'+str(expected))
    oracle=analyze(folder,root/'openapi.json',engine,root/'frozen-analyzer',scope)
    coverage=json.loads((folder/'natchan-result/coverage.json').read_text())
    analysis_result=json.loads((folder/'natchan-result/result.json').read_text())
    case_results={}
    if tool=='provengo-sample10':
     case_results={str(i):{'execution_pass':r['exit_code']==0 and not r['watchdog_timeout']} for i,r in enumerate(outcomes,1)}
    elif tool=='provengo-java' and (folder/'native.jsonl').is_file():
     case_results={str(r['case']):{'execution_pass':r['native_pass'],'details':r} for r in [json.loads(line) for line in (folder/'native.jsonl').read_text().splitlines() if line.strip()]}
    clean=set(case_results)-{str(f['case_id']) for f in oracle['findings']}
    baseline=results.get(tool,{}).get('none',{})
    eligible=baseline.get('control_eligible_cases',[]) if arm!='none' else sorted(k for k,v in case_results.items() if v['execution_pass'] and k in clean)
    results.setdefault(tool,{})[arm]={'scope':scope,'execution':outcomes,'oracle_bug_ids':oracle['confirmed_bug_ids'],'oracle_server_errors':len(oracle['server_errors']),'natchan_classes':coverage.get('classes'),'natchan_status':analysis_result['status'],'natchan_version':analysis_result['analyzer_version'],'native_case_results':case_results,'control_eligible_cases':eligible,'native_failures_on_control_eligible_cases':[k for k,v in case_results.items() if not v['execution_pass'] and k in eligible],'native_findings':'REVIEW_RETAINED_NATIVE_REPORTS','complete_execution':not any(r['watchdog_timeout'] for r in outcomes),'state':'EVIDENCE_CAPTURED'}
    write(root/'summary.json',results);print('END '+tool+' '+arm+' ORACLE='+','.join(oracle['confirmed_bug_ids']),flush=True)
  write(root/'completed.json',{'status':'CAMPAIGN_CAPTURE_COMPLETE','configurations':tools,'arms':a.arms.split(','),'note':'Capture completion does not mean every case passed or every mutation was found.'})
 except Exception as exc:
  import traceback
  error=str(exc)
  try:write(root/'failure.json',{'status':'INCOMPLETE','error':error,'traceback':traceback.format_exc()})
  except OSError:print(traceback.format_exc(),flush=True)
  raise
 finally:
  try:
   write(root/'summary.json',results)
   from pack_review_v001 import pack
   pack(root)
  except OSError as archive_error:print('ARCHIVE_FAILED '+str(archive_error)+' RUN_DIRECTORY '+str(root),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=HERE/'tools.local.json');p.add_argument('--tools',default=','.join(TOOLS));p.add_argument('--arms',default=','.join(ARMS));p.add_argument('--seconds',type=int,default=60);p.add_argument('--seed',type=int,default=1);p.add_argument('--port',type=int,default=23443);p.add_argument('--max-length',type=int,default=500);p.add_argument('--case-timeout',type=int,default=120);p.add_argument('--java-timeout',type=int,default=7200);p.add_argument('--sample-timeout',type=int,default=240);p.add_argument('--java-limit',type=int,default=0);p.add_argument('--output',type=Path);p.add_argument('--prepare-only',action='store_true');p.add_argument('--reuse-run',type=Path);a=p.parse_args()
 if min(a.seconds,a.case_timeout,a.java_timeout,a.sample_timeout,a.max_length)<=0 or not 1024<=a.port<=65535:p.error('Invalid budget or port')
 main(a)
