"""Provengo compact sampling + isolated fast replay of original/baseline/B1-B6.
Not native Provengo actuation. No callback deserialization. Fail fast on control errors.
"""
import argparse, hashlib, json, logging, os, re, shutil, subprocess, sys, time, uuid
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from mutants import create
from replay import ARMS, replay, digest
logging.disable(logging.CRITICAL)
HERE=Path(__file__).resolve().parent
TOKEN=re.compile(r'@\{((?:USER|BOOK|LOAN|HOLD)\d+)\}')

def write(p,v):
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(v,indent=2),encoding='utf-8');temp.replace(p)

def events_from(path, allow_negative=False):
    if path.stat().st_size>8*1024**2:raise ValueError('Compact sample exceeds 8 MiB; refusing oversized callback output')
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],list):raise ValueError('Expected exactly one sampled event sequence')
    events=data[0]
    if not events:raise ValueError('Sample contains no events')
    for e in events:
        d=e.get('data',{})
        if e.get('name') not in (['POST','GET','DELETE','PUT','PATCH'] if allow_negative else ['POST','GET','DELETE']) or d.get('callback') is not None:raise ValueError('Unexpected event or serialized callback')
        codes=d.get('expectedResponseCodes',[])
        if not codes or any(not(200<=int(c)<300 or (400<=int(c)<500 if allow_negative else (e['name']=='GET' and int(c)==404))) for c in codes):raise ValueError('Negative field/state check leaked into compact sample')
    return events

def materialize(events,seed, allow_negative=False):
    import random
    random.seed(seed);c=create('original').test_client();c.post('/reset',json={});rtv={};rows=[]
    def render(v):
        if isinstance(v,dict):return {k:render(x) for k,x in v.items()}
        if isinstance(v,list):return [render(x) for x in v]
        if not isinstance(v,str):return v
        def sub(m):
            if m[1] not in rtv:raise ValueError('Unbound symbolic ID '+m[1])
            return str(rtv[m[1]])
        return TOKEN.sub(sub,v)
    for index,e in enumerate(events,1):
        d=e['data'];method=e['name'];url=urlsplit(render(d['url']));path=url.path
        params=render(d.get('parameters',{}));params.pop('description',None)
        if url.query:path+='?'+url.query
        if params:path+=('&' if '?' in path else '?')+urlencode(params)
        body=d.get('body')
        if isinstance(body,str):body=json.loads(body)
        body=render(body)
        before=[c.get('/'+kind).get_json() for kind in ['users','books','loans','holds']] if allow_negative else None
        response=c.open(path,method=method,json=body) if body is not None else c.open(path,method=method)
        expected=[200 if method=='DELETE' and int(v)==204 else int(v) for v in d['expectedResponseCodes']]
        data=response.get_json(silent=True)
        rows.append({'role':'tool','method':method,'url':'http://127.0.0.1:23600'+path,'input':body,'status':response.status_code,'response':data,'order':index})
        if response.status_code not in expected:raise ValueError(f'Original reference rejected sampled event {index}: expected {expected}, got {response.status_code}: {data}')
        if allow_negative and response.status_code>=400:
            after=[c.get('/'+kind).get_json() for kind in ['users','books','loans','holds']]
            if before!=after:raise ValueError(f'Rejected event {index} changed state; refusing projection')
        if method=='POST' and response.status_code==201:
            entity=url.path.strip('/');kind={'users':'USER','books':'BOOK','loans':'LOAN','holds':'HOLD'}[entity]
            logical=d.get('parameters',{}).get('loanNumber' if entity=='loans' else 'id')
            if logical is None:raise ValueError('Create event lacks logical ID binding')
            rtv[kind+str(int(logical))]=data['id']
    return rows

def launch(command,folder,name,timeout):
    write(folder/(name+'-command.json'),list(map(str,command)))
    with (folder/(name+'.log')).open('w') as log:
        proc=subprocess.Popen(list(map(str,command)),stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
        started=time.monotonic();timed=False
        try:
            while proc.poll() is None:
                try:proc.wait(timeout=min(30,timeout))
                except subprocess.TimeoutExpired:
                    print(f'PROGRESS {name} elapsed={int(time.monotonic()-started)}s',flush=True)
                if proc.poll() is None and shutil.disk_usage(folder).free<2*1024**3:
                    raise RuntimeError('Less than 2 GiB free; stopping native process')
                candidate=folder/'sample.json'
                if proc.poll() is None and candidate.exists() and candidate.stat().st_size>8*1024**2:
                    raise RuntimeError('Oversized compact sample; stopping native process')
                if proc.poll() is None and time.monotonic()-started>=timeout:
                    timed=True;raise TimeoutError(name+' timed out')
        finally:
            if proc.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=log)
                else:
                    import signal
                    os.killpg(proc.pid,signal.SIGKILL)
                proc.wait()
            write(folder/(name+'-execution.json'),{'returncode':proc.returncode,'timeout':timed,'seconds':time.monotonic()-started})
    if proc.returncode:raise RuntimeError(f'{name} failed; inspect {folder/(name+".log")}')

def archive_case(work,target):
    if target.exists():raise FileExistsError(target)
    shutil.copytree(work,target)
    hashes={str(p.relative_to(work)):digest(p) for p in work.rglob('*') if p.is_file()}
    if any(digest(target/n)!=h for n,h in hashes.items()):raise RuntimeError('Archive mismatch; D: work retained')
    write(target/'archive-verified.json',hashes)

def main(a):
    source_hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and (p.suffix in ['.py','.js','.yml'] or p.name=='b2-plan.json') and '.venv' not in p.parts and '__pycache__' not in p.parts}
    if a.resume:
        root=a.resume.resolve();config=json.loads((root/'campaign.json').read_text())
        if config['code_sha256']!=source_hashes or config['jar_sha256']!=digest(a.jar):raise ValueError('Resume rejected: source code or Provengo binary changed')
        if config.get('model_kind','compact')!=a.model or config.get('b2_witness',False)!=a.b2_witness:raise ValueError('Resume model/diagnostic mode differs')
        if (config['count'],config['max_length'],config['seed'])!=(a.count,a.max_length,a.seed):raise ValueError('Resume parameters differ')
        work_root=Path(config['work_root'])
    else:
        tag='library-v003-sample-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        root=a.output_base/tag;work_root=a.work_base/tag;root.mkdir(parents=True);work_root.mkdir(parents=True)
        config={'count':a.count,'max_length':a.max_length,'seed':a.seed,'engine':'Provengo sample + Flask test_client replay','code_sha256':source_hashes,'jar_sha256':digest(a.jar),'work_root':str(work_root),'rarity_qualified':False,'model_kind':a.model,'b2_witness':a.b2_witness}
        write(root/'campaign.json',config)
    print('RESULT_DIRECTORY',root,flush=True);print('WORK_DIRECTORY',work_root,flush=True)
    preflight=work_root/'preflight';preflight.mkdir(exist_ok=True)
    launch([a.java,'-jar',a.jar,'sample','-h'],preflight,'help',90)
    helptext=(preflight/'help.log').read_text(errors='replace')
    length=next((v for v in ['--max-length','--max-depth'] if v in helptext),None)
    if not length:raise ValueError('Unsupported Provengo sample CLI; inspect help log')
    seedflag='--seed' if re.search(r'(?<![\w-])--seed(?:[\s=,]|$)',helptext) else None
    config['selection_seed_flag']=seedflag;write(root/'campaign.json',config)
    write(root/'preflight-help.json',{'text':helptext})
    model=work_root/'model'
    if model.exists():shutil.rmtree(model)
    shutil.copytree(HERE/(a.model+'-model'),model)
    if a.b2_witness:
        shutil.copyfile(HERE/'b2_reachability_guide.js',model/'spec/js/zz_b2_reachability_guide.js')
    summary={}
    for index in range(1,a.count+1):
        name=f'case-{index:03d}';target=root/name;work=work_root/name
        if (target/'completed.json').exists() and (target/'archive-verified.json').exists():
            hashes=json.loads((target/'archive-verified.json').read_text())
            if any(digest(target/n)!=h for n,h in hashes.items()):raise ValueError('Archived case changed: '+name)
            summary[name]=json.loads((target/'summary.json').read_text());continue
        if target.exists() or work.exists():
            if not a.resume:raise RuntimeError(f'Incomplete case retained: {name}')
            suffix=uuid.uuid4().hex[:6]
            for old,parent in [(target,root/'incomplete'),(work,work_root/'incomplete')]:
                if old.exists():
                    parent.mkdir(exist_ok=True);old.rename(parent/(name+'-'+suffix))
            print('PRESERVED_INCOMPLETE_AND_RETRYING',name,flush=True)
        if shutil.disk_usage(work_root).free<2*1024**3 or shutil.disk_usage(root).free<2*1024**3:raise RuntimeError('Less than 2 GiB free')
        work.mkdir();print(f'SAMPLE_AND_REPLAY {index}/{a.count}',flush=True)
        report={'engine':config['engine'],'arms':{}};start=time.perf_counter()
        try:
            (model/'data/00_compact_seed.js').write_text('var COMPACT_SEED = '+str(a.seed+index-1)+';\n')
            native=work/'sample.json'
            command=[a.java,'-Xmx2g','-jar',a.jar,'sample','--overwrite','--size','1',length,str(a.max_length),'-o',native,model]
            if seedflag:command += [seedflag,str(a.seed+index-1)]
            launch(command,work,'sample',a.timeout)
            events=events_from(native,allow_negative=a.model=='full')
            all_rows=materialize(events,a.seed+index-1,allow_negative=a.model=='full')
            rows=[r for r in all_rows if 200<=r['status']<300 or (r['method']=='GET' and r['status']==404)]
            if a.model=='full':
                (work/'full-reference.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in all_rows))
            if a.b2_witness:
                from check_b2_reachability import check_rows
                write(work/'b2-reachability.json',check_rows(rows))
                if (work/'sample.log').read_text(errors='replace').find('B2_GUIDE_COMPLETED')<0:raise ValueError('Native B2 guide did not complete')
            report.update(model_seed=a.seed+index-1,sampled_events=len(events),reference_requests=len(rows),removed_requests=len(all_rows)-len(rows),projection='original-rejected requests removed after state-equivalence check' if a.model=='full' else 'none',sample_sha256=digest(native))
            (work/'reference.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            for mode in ARMS:
                result=replay(rows,mode,work/(mode+'.jsonl'),a.seed+index-1)
                report['arms'][mode]=result
                if mode in ['original','baseline'] and result['status']!='PASS':raise RuntimeError(f'{name} control failed: {mode}')
            if a.b2_witness and report['arms']['B2']['status']!='DIFFERENT':raise ValueError('Native guided sequence did not expose B2')
            write(work/'completed.json',{'arms':len(ARMS),'sampled_events':len(events)})
        except BaseException as exc:
            write(work/'failure.json',{'error':str(exc)})
            raise
        finally:
            report['seconds']=time.perf_counter()-start;write(work/'summary.json',report)
            archive_case(work,target)
            summary[name]=report;write(root/'summary.json',summary)
        summary[name]=report;write(root/'summary.json',summary);shutil.rmtree(work)
        # Sample-only model products may contain a transient run database; no execution evidence is stored there.
        products=model/'products'
        if products.exists():shutil.rmtree(products)
        print('CASE_SAVED',index,report['arms'],flush=True)
        if index==1:print('FIRST_SAMPLE_CONTROL_GATE_PASSED',flush=True)
    write(root/'completed.json',{'cases':a.count,'replays':a.count*len(ARMS)})
    print('CAMPAIGN_COMPLETE',root,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--jar',type=Path,required=True);p.add_argument('--java',default='java');p.add_argument('--count',type=int,default=500);p.add_argument('--max-length',type=int,default=2000);p.add_argument('--seed',type=int,default=10001);p.add_argument('--timeout',type=int,default=300);p.add_argument('--work-base',type=Path,required=True);p.add_argument('--output-base',type=Path,required=True);p.add_argument('--resume',type=Path);p.add_argument('--model',choices=['compact','full'],default='compact');p.add_argument('--b2-witness',action='store_true')
    a=p.parse_args()
    if min(a.count,a.max_length,a.timeout)<1 or not a.jar.is_file():p.error('Invalid count/length/timeout or missing JAR')
    if a.b2_witness and (a.count!=1 or a.model!='full'):p.error('B2 diagnostic requires --count 1 --model full')
    a.jar=a.jar.resolve();a.work_base=a.work_base.resolve();a.output_base=a.output_base.resolve();main(a)
