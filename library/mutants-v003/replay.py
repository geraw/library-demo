"""Fast projection of recorded original runs. Engine: Flask test_client, not Provengo.
Only original successful operations and GET 404 observations are retained.
Unexpected mutant 4xx are retained and reported, never filtered out.
"""
import argparse, hashlib, json, logging, random, shutil, time, zipfile
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode
from mutants import create
logging.disable(logging.CRITICAL)
ARMS=['original','baseline','B1','B2','B3','B4','B5','B6']

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024**2),b''):h.update(c)
    return h.hexdigest()

def replay(rows,mode,trace,seed):
    random.seed(seed);client=create(mode).test_client();client.post('/reset',json={})
    ids={kind:{} for kind in ['users','books','loans','holds']}
    def ident(kind,v):
        try: mapped=ids[kind].get(int(v),v)
        except (ValueError,TypeError):return v
        return str(mapped) if isinstance(v,str) else mapped
    def payload(v,entity):
        if isinstance(v,str):
            try:return payload(json.loads(v),entity)
            except (ValueError,TypeError):return v
        if isinstance(v,list):return [payload(x,entity) for x in v]
        if isinstance(v,dict):return {k:ident({'id':entity,'userId':'users','bookId':'books'}[k],x) if k in ['id','userId','bookId'] else x for k,x in v.items()}
        return v
    with trace.open('w',encoding='utf-8') as log:
        for index,row in enumerate(rows,1):
            url=urlsplit(row['url']);parts=url.path.strip('/').split('/');entity=parts[0]
            kinds=['users','books'] if entity=='loans' else [entity]
            path='/'+ '/'.join([entity]+[str(ident(kinds[i],v)) if i<len(kinds) else v for i,v in enumerate(parts[1:])])
            query=[]
            for k,v in parse_qsl(url.query,keep_blank_values=True):
                if k=='description':continue
                if k in ['userId','bookId']:v=ident({'userId':'users','bookId':'books'}[k],v)
                elif k=='q' and v.isdigit():
                    matches=[d[int(v)] for d in ids.values() if int(v) in d]
                    if len(matches)>1:raise ValueError('Ambiguous cross-resource q identifier; refusing unsafe projection')
                    if matches:v=str(matches[0])
                query.append((k,v))
            if query:path+='?'+urlencode(query)
            body=payload(row['input'],entity)
            started=time.perf_counter();r=client.open(path,method=row['method'],json=body) if body is not None else client.open(path,method=row['method'])
            actual=r.get_json(silent=True);expected=row['response']
            if row['method']=='POST' and row['status']==201 and r.status_code==201 and isinstance(expected,dict) and 'id' in expected:
                ids[entity][expected['id']]=actual['id']
            mapped=payload(expected,entity)
            passed=r.status_code==row['status'] and actual==mapped
            log.write(json.dumps({'projected_order':index,'source_order':row.get('order'), 'method':row['method'],'path':path,'input':body,'status':r.status_code,'response':actual,'expected_status':row['status'],'expected_response':mapped,'match':passed,'seconds':time.perf_counter()-started})+'\n')
            if not passed:return {'status':'DIFFERENT','first_difference':index,'source_order':row.get('order'),'http_requests':index}
    return {'status':'PASS','http_requests':len(rows)}

def main(a):
    a.work.mkdir(parents=True,exist_ok=True);a.output.mkdir(parents=True,exist_ok=True)
    if a.evidence.is_dir():
        paths=sorted(a.evidence.glob('case-*.jsonl'))
        if paths:
            source_names=[p.stem+'/original/http.jsonl' for p in paths]
            lookup={name:path for name,path in zip(source_names,paths)}
            read_source=lambda name: lookup[name].read_bytes()
            manifest_path=a.evidence/'manifest.json'
            if manifest_path.exists():
                manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
                for item in manifest.get('cases',[]):
                    path=a.evidence/(item['case']+'.jsonl')
                    if not path.is_file() or hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=item['sha256']:
                        raise ValueError('Changed or missing clean scenario: '+str(path))
        else:
            paths=sorted(a.evidence.glob('case-*/reference.jsonl')) or sorted(a.evidence.glob('case-*/original/http.jsonl'))
            lookup={p.parent.name+'/original/http.jsonl':p for p in paths if p.name=='reference.jsonl'}
            if not lookup:lookup={p.parent.parent.name+'/original/http.jsonl':p for p in paths}
            source_names=sorted(lookup)
            read_source=lambda name:lookup[name].read_bytes()
    else:
        z=zipfile.ZipFile(a.evidence)
        source_names=sorted(n for n in z.namelist() if n.endswith('/original/http.jsonl'))
        read_source=z.read
    if not source_names:raise ValueError('No original HTTP traces or clean case JSONL files found')
    print('AVAILABLE_CASES',len(source_names),flush=True)
    limit=a.limit or len(source_names)
    (a.output/'run.json').write_text(json.dumps({'mutation_version':'v003','engine':'Flask test_client projected replay','input':str(a.evidence.resolve()),'available_cases':len(source_names),'code_sha256':{n:digest(Path(__file__).with_name(n)) for n in ['mutants.py','original.py','replay.py']}},indent=2))
    summary={}
    for name in source_names[:limit]:
        case=name.split('/')[0];target=a.output/case
        if target.exists():raise FileExistsError(f'Use a new output directory: {target}')
        work=a.work/case;work.mkdir(exist_ok=False)
        source=read_source(name);rows=[r for l in source.splitlines() if (r:=json.loads(l)).get('role')=='tool']
        kept=[r for r in rows if 200<=r['status']<300 or (r['method']=='GET' and r['status']==404)]
        report={'mutation_version':'v003','engine':'flask-test-client-projected-replay','source_sha256':hashlib.sha256(source).hexdigest(),'source_requests':len(rows),'retained_requests':len(kept),'arms':{}}
        started=time.perf_counter()
        try:
            for mode in ARMS:
                result=replay(kept,mode,work/(mode+'.jsonl'),int(case.split('-')[-1]))
                report['arms'][mode]=result
                if mode in ['original','baseline'] and result['status']!='PASS':raise RuntimeError(f'{case} control failed: {mode}')
        finally:
            report['seconds']=time.perf_counter()-started
            (work/'summary.json').write_text(json.dumps(report,indent=2))
            shutil.copytree(work,target)
            hashes={p.name:digest(p) for p in work.iterdir() if p.is_file()}
            if any(digest(target/n)!=h for n,h in hashes.items()):raise RuntimeError('Archive hash mismatch; work retained')
            (target/'archive-verified.json').write_text(json.dumps(hashes,indent=2))
        summary[case]=report
        (a.output/'summary.json').write_text(json.dumps(summary,indent=2))
        shutil.rmtree(work)
        print(case,'retained',len(kept),'of',len(rows),{m:r['status'] for m,r in report['arms'].items()},flush=True)
    (a.output/'completed.json').write_text(json.dumps({'cases':len(summary),'replays':len(summary)*len(ARMS)},indent=2))
    print('RESULTS',a.output,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=10);main(p.parse_args())
