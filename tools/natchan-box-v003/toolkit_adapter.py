"""Offline E1-E5 reader for toolkit/v1. Raw evidence is authoritative, never verdict labels."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v014'))
from coverage_engine import analyze
from providers import equal
from natchan import unpack

MAX_BYTES=1000000000

def digest(raw):return hashlib.sha256(raw).hexdigest()
def parsed(value):
    if isinstance(value,str):
        try:return json.loads(value)
        except ValueError:return value
    return value

def document(raw):return json.loads(raw.decode('utf-8-sig'))
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def members(raw,budget):
    """Read bounded normalized member names without extracting or losing provenance."""
    out={};seen=set()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.infolist())>20000:raise ValueError('Archive member budget exceeded')
        for info in z.infolist():
            name=info.filename.replace('\\','/')
            if name.startswith('/') or any(p=='..' or ':' in p for p in name.split('/')):raise ValueError('Unsafe archive member')
            if name.casefold() in seen:raise ValueError('Duplicate/colliding archive member')
            seen.add(name.casefold())
            if info.is_dir():continue
            budget[0]-=info.file_size
            if budget[0]<0:raise ValueError('Expanded evidence budget exceeded')
            out[name]=z.read(info)
    return out

def env_read(raw):
    out={}
    for line in raw.decode('utf-8-sig').splitlines():
        key,sep,value=line.partition('=')
        if not sep:continue
        key=key.strip()
        if key in out:raise ValueError('Duplicate ENV field: '+key)
        out[key]=value.strip()
    return out

def check_manifest(files):
    found=False
    for name in ['manifest_v1.json','input_hashes.json']:
        if name not in files:continue
        found=True
        hashes=document(files[name])
        if not isinstance(hashes,dict):raise ValueError('Invalid run hash manifest')
        for member,h in hashes.items():
            member=member.replace('\\','/')
            if member not in files or digest(files[member])!=h:raise ValueError('Run manifest hash mismatch: '+member)
    return found

class Reader:
    def __init__(self,path,sut_config=None,sut_config_sha256=None,toolkit_repo=None):
        self.path=path;self.raw=path.read_bytes();self.archive_sha=digest(self.raw)
        self.sut_config=sut_config;self.sut_config_sha256=sut_config_sha256;self.toolkit_repo=toolkit_repo
        self.embedded={};self.parts=[];self.gaps=[];self.packages=[];self.configurations=[];self.measurements=[];self.inputs=[];self.summaries=[]
    def gap(self,code,**kw):self.gaps.append(dict(code=code,**kw))
    def source(self,files,name,chain,record=None):
        result=dict(file=str(self.path),archive_sha256=self.archive_sha,members=chain+[name],sha256=digest(files[name]))
        if record is not None:result['record']=record
        return result
    def configuration(self,files,env,product,chain):
        candidates=[n for n in files if n=='sut.json' or n==f'configs/{product}/sut.json']
        raw=None;origin={}
        if len(candidates)>1:raise ValueError('Ambiguous embedded SUT configuration')
        if candidates:
            raw=files[candidates[0]];origin={'source':self.source(files,candidates[0],chain),'binding':'embedded_package_snapshot'}
        if self.sut_config:
            external=self.sut_config.read_bytes()
            if self.sut_config_sha256 and digest(external)!=self.sut_config_sha256:raise ValueError('SUT configuration SHA256 mismatch')
            if raw is not None and raw!=external:raise ValueError('Embedded/external SUT configuration conflict')
            raw=external;origin={'path':str(self.sut_config),'sha256':digest(raw),'binding':'external_pinned_snapshot' if self.sut_config_sha256 else 'external_snapshot_unverified_against_producer_commit'}
        if raw is None and product in self.embedded:
            raw,origin=self.embedded[product]
        head=env.get('git_head')
        if self.toolkit_repo and head:
            if not re.fullmatch(r'[0-9a-f]{40}',head) or not re.fullmatch('[a-zA-Z0-9_-]+',product):raise ValueError('Invalid producer Git identity')
            member=f'toolkit/v1/configs/{product}/sut.json'
            p=subprocess.run(['git','-C',str(self.toolkit_repo),'show',head+':'+member],capture_output=True,timeout=30)
            if p.returncode:raise ValueError('Producer configuration not available at recorded Git commit locally')
            if raw is not None and raw!=p.stdout:raise ValueError('SUT configuration differs from producer Git snapshot')
            raw=p.stdout;origin={'repository':str(self.toolkit_repo),'git_head':head,'path':member,'sha256':digest(raw),'binding':'verified_local_git_snapshot'}
        if raw is None:
            self.gap('SUT_CONFIGURATION_MISSING',product=product,git_head=head,affects='product log pattern counts; no online repository fetch is performed')
            return None
        if candidates:self.embedded[product]=(raw,dict(origin))
        config=document(raw)
        if config.get('name')!=product:raise ValueError('SUT configuration product conflicts with actual run')
        origin.update(product=product,sha256=digest(raw),producer_git_head=head)
        if head and origin['binding']=='external_snapshot_unverified_against_producer_commit':self.gap('SUT_CONFIGURATION_REVISION_UNVERIFIED',product=product,git_head=head)
        if origin not in self.configurations:self.configurations.append(origin)
        return config
    def log_counts(self,files,config,chain,ignore_case=False):
        if 'sut.log' not in files or not files['sut.log'].strip():self.gap('SERVER_LOG_MISSING',members=chain);return {}
        if not config:return {}
        lines=files['sut.log'].decode('utf-8-sig').splitlines();patterns=config.get('logs',{});counts={}
        for field,key in [('sut_log_E','error_pattern'),('sut_log_500','http500_pattern'),('sut_log_completed_requests','request_pattern')]:
            if patterns.get(key):counts[field]=sum((patterns[key].casefold() in l.casefold()) if ignore_case else (patterns[key] in l) for l in lines)
        if patterns.get('reach_regex'):counts['sut_log_reach']=sum(bool(re.search(patterns['reach_regex'],l,re.IGNORECASE if ignore_case else 0)) for l in lines)
        return counts
    def walk(self,raw,chain=None,inherited=None,depth=0,budget=None):
        chain=chain or [];inherited=inherited or {};budget=budget or [MAX_BYTES]
        if depth>5:raise ValueError('Nested evidence depth exceeded')
        files=members(raw,budget)
        envs=[n for n in files if re.fullmatch(r'ENV_v1_(model|campaign|baselines)\.txt',n)]
        if len(envs)>1:raise ValueError('Ambiguous package ENV files')
        env=dict(inherited)
        if envs:env.update(env_read(files[envs[0]]))
        if envs and env.get('sut') and any(n=='sut.json' or n==f"configs/{env['sut']}/sut.json" for n in files):self.configuration(files,env,env['sut'],chain)
        if envs:self.packages.append(dict(source=self.source(files,envs[0],chain),metadata=env))
        if env.get('result')=='STOPPED':self.gap('PACKAGE_STOPPED',members=chain,reason='No completed package is claimed; any actual retained runs are handled separately')
        if 'gateway-journal.jsonl' in files:
            self.run(files,chain,env);return
        if any(n.endswith('/run-meta.json') for n in files):
            self.baselines(raw,files,chain,env);return
        nested=[n for n in files if re.fullmatch(r'review_v1_s[0-9]+\.zip',n)]
        if 'GENERATION_g014.json' in files and not nested:self.gap('PREPARE_ONLY_NO_RUN',members=chain)
        if not nested:
            self.gap('NO_RUN_EVIDENCE',members=chain);return
        if 'seeds' in env:
            expected=set(re.findall(r'\d+',env['seeds']));actual={re.search(r'_s(\d+)\.zip$',n)[1] for n in nested}
            for seed in sorted(expected-actual):self.gap('SEED_ARCHIVE_MISSING',seed=seed,members=chain)
        for name in sorted(nested):
            seed=re.search(r'_s(\d+)\.zip$',name)[1]
            if f'result_v1_s{seed}.json' in files:
                inner=members(files[name],[MAX_BYTES])
                if 'result_v1.json' in inner and document(inner['result_v1.json'])!=document(files[f'result_v1_s{seed}.json']):raise ValueError('Outer/inner result copies disagree')
            self.walk(files[name],chain+[name],env,depth+1,budget)
    def run(self,files,chain,env):
        if 'result_v1.json' not in files:raise ValueError('Toolkit run lacks result_v1.json')
        result=document(files['result_v1.json']);product=result.get('sut');version=result.get('sut_version')
        if not isinstance(product,str) or not product:raise ValueError('Actual result.sut is required')
        if not version or version=='unknown':version=None;self.gap('SUT_VERSION_UNKNOWN',members=chain)
        for key,value in [('sut',product),('sut_version',version)]:
            if env.get(key) and value and env[key]!=value:raise ValueError('Outer/run metadata conflict: '+key)
        config=self.configuration(files,env,product,chain)
        if not check_manifest(files):self.gap('RUN_MANIFEST_MISSING',members=chain)
        ir=document(files.get('generated/contract-ir.json',b'{}'))
        if not ir:self.gap('CONTRACT_IR_MISSING',members=chain)
        raw=files['gateway-journal.jsonl'];rows=[json.loads(l) for l in raw.decode('utf-8-sig').splitlines() if l.strip()]
        positions=[i for i,r in enumerate(rows) if r.get('category')=='research'];count=len(positions)
        if result.get('requests') is not None and result['requests']!=count:raise ValueError('Raw/result request count mismatch')
        if 'seed' in result and chain:
            match=re.search(r'_s(\d+)\.zip$',chain[-1])
            if match and str(result['seed'])!=match[1]:raise ValueError('Seed filename/result mismatch')
        for i,row in enumerate(rows):
            if row.get('category')=='research' and (type(row.get('status')) is not int or not 100<=row['status']<=599):
                if row.get('status') is not None:raise ValueError('Invalid journal HTTP status')
        run_id='/'.join([self.path.stem,*chain])
        src=self.source(files,'gateway-journal.jsonl',chain)
        context=dict(id=run_id,product=product,version=version,tool='provengo',seed=result.get('seed'),source=src)
        plan=document(files['generated/plan.json']) if 'generated/plan.json' in files else None
        if product=='gitea':
            # Preserve the existing known-bug, RT, reference and raw sequence logic.
            sys.path.insert(0,str(ROOT.parent/'natchan-v005'));import analyze_coverage as old
            values,oracles=old.baseline.gitea_observations(context,dict(records=rows,ir=ir,sut_log=files.get('sut.log',b'').decode('utf-8-sig')))
            old.augment_gitea(values,rows)
            from raw_sequences import augment
            augment(values,rows,plan)
        else:
            values,oracles=self.generic(rows,ir,context)
            self.gap('PRODUCT_SPECIFIC_KNOWN_BUG_ADAPTER_NOT_AVAILABLE',product=product,members=chain)
        # Independently associate plan steps with exactly one physical exchange.
        sequence=self.sequence_rows(rows,plan)
        for o in values:
            idx=o['source']['record'];o['field']=o.get('field') or (sequence.get(idx) or {}).get('field')
        self.producer_measurements(rows,context)
        counts=self.log_counts(files,config,chain)
        if 'sut_log_errors' in result and 'sut_log_E' in counts and result['sut_log_errors']!=counts['sut_log_E']:raise ValueError('Raw/result server error count mismatch')
        self.summaries.append(dict(id=run_id,product=product,version=version,tool='provengo',seed=result.get('seed'),native_status=result.get('status'),native_exit=result.get('native_exit'),http_records=count,http_5xx=sum(type(rows[i].get('status')) is int and rows[i]['status']>=500 for i in positions),source=src,category_counts=dict(Counter(r.get('category') for r in rows)),log_pattern_counts=counts,completed_steps=result.get('completed_steps'),planned_steps=result.get('planned_steps')))
        if 'native.log' not in files:self.gap('NATIVE_LOG_MISSING',run=run_id)
        elif result.get('status')=='COMPLETED' and (result.get('native_exit') not in [None,0] or 'Test Result: SUCCESS' not in files['native.log'].decode('utf-8-sig')):self.gap('NATIVE_COMPLETION_NOT_VERIFIED',run=run_id)
        status=result.get('status')
        if status!='COMPLETED':self.gap('RUN_NOT_COMPLETED',run=run_id,status=status,observed_prefix_retained=True)
        if result.get('fixture_failures'):self.gap('FIXTURE_FAILURES',run=run_id,detail=result['fixture_failures'])
        if 'completed_steps' in result and result.get('completed_steps')!=result.get('planned_steps'):self.gap('CAMPAIGN_STEPS_INCOMPLETE',run=run_id)
        if plan is not None:
            steps=[r['step'] for r in rows if r.get('category')=='g014-sequence' and type(r.get('step')) is int]
            if len(steps)!=len(set(steps)):raise ValueError('Duplicate campaign sequence steps')
            if result.get('completed_steps') is not None and result['completed_steps']!=len(steps):raise ValueError('Raw/result campaign step count mismatch')
            if any(r.get('category')=='g014-sequence' for r in rows) and len(sequence)!=len(steps):self.gap('SEQUENCE_HTTP_ASSOCIATION_INCOMPLETE',run=run_id)
        for o in values:o['product_metadata_source']=self.source(files,'result_v1.json',chain)
        self.parts.append((run_id,dict(observations=values,runs=[self.summaries[-1]],original_oracles=oracles)))
        for name in ['gateway-journal.jsonl','result_v1.json','native.log','sut.log','generated/contract-ir.json','generated/plan.json','manifest_v1.json','input_hashes.json']:
            if name in files:self.inputs.append(self.source(files,name,chain))
    def generic(self,rows,ir,context):
        from tse_products import route_match
        values=[];oracles=[]
        for i,r in enumerate(rows):
            source=dict(context['source'],record=i)
            if r.get('category')!='research':oracles.append(dict(source=source,payload=r));continue
            entity=None;operation={'GET':'read','DELETE':'delete','PATCH':'update'}.get(r.get('method'),'unknown')
            for e in ir.get('entities',[]):
                for action,key,verb in [('create','path',e.get('create_method')),('update','detail',e.get('update_method')),('read','detail','get')]:
                    if e.get(key) and verb==r.get('method','').lower() and route_match(e[key],r.get('path','')):entity=e['name'].lower();operation=action
            values.append(dict(id=context['id']+':'+str(i),product=context['product'],product_version=context['version'],run_id=context['id'],tool='provengo',seed=context.get('seed'),source=source,method=r.get('method'),path=r.get('path'),status=r.get('status'),request=parsed(r.get('input')),response=parsed(r.get('response')),entity=entity,operation=operation,facts={'entity':entity,'operation':operation},fact_basis='recomputed',evidence_tier='recorded_http_sequence',witnesses=[]))
        return values,oracles
    def sequence_rows(self,rows,plan):
        """g014-sequence duplicates research HTTP. Never count it as another request."""
        if not plan:return {}
        result={};used=set();specs=plan.get('steps',[])
        for i,r in enumerate(rows):
            if r.get('category')!='g014-sequence':continue
            step=r.get('step')
            if type(step) is not int or not 0<=step<len(specs):raise ValueError('Invalid sequence plan step')
            spec=specs[step]
            if r.get('method')!=spec.get('method') or r.get('role')!=spec.get('role'):raise ValueError('Sequence/plan method or role conflict')
            # The physical record precedes its derived sequence receipt in this gateway.
            candidates=[j for j in range(i) if rows[j].get('category')=='research' and rows[j].get('logical_id')=='G014_STEP_'+str(step) and all(rows[j].get(k)==r.get(k) for k in ['method','path','status']) and equal(parsed(rows[j].get('input')),r.get('request')) and equal(parsed(rows[j].get('response')),r.get('response'))]
            if len(candidates)==1 and candidates[0] not in used:result[candidates[0]]=spec;used.add(candidates[0])
        return result
    def producer_measurements(self,rows,context):
        for i,row in enumerate(rows):
            category=row.get('category')
            if category=='research' or category=='g014-sequence':continue
            source=dict(context['source'],record=i);value=None
            if category=='atomicity-check':
                states=set(row.get('fields',{}).values());value='partial' if {'applied','kept'}<=states else 'rolled_back' if states=={'kept'} else 'committed_despite_error' if states=={'applied'} else 'unknown'
                self.gap('ATOMICITY_FULL_SNAPSHOTS_NOT_RETAINED',source=source)
            elif category=='roundtrip-check':
                changes=row.get('mismatches',{});qualified=all(isinstance(v,dict) and 'sent' in v and 'stored' in v for v in changes.values())
                value=('mismatch' if any(v['sent']!=v['stored'] for v in changes.values()) else 'no_difference_in_retained_fields') if qualified and row.get('readback_status')==200 else 'unknown'
            elif category in ['reference-check','link2-check']:
                actual=row.get('stored') if category=='reference-check' else row.get('listed')
                value='different_projection' if row.get('readback_status')==200 and 'sent' in row and actual!=row['sent'] else 'equal_projection' if row.get('readback_status')==200 and 'sent' in row else 'unknown'
            elif category=='divergence-check':
                c=row.get('create',{}).get('status');u=row.get('update',{}).get('status')
                value='different_response_classes_in_summary' if type(c) is int and type(u) is int and c//100!=u//100 else 'unknown_or_same_class'
            else:self.gap('UNSUPPORTED_JOURNAL_CATEGORY',category=category,source=source)
            self.measurements.append(dict(category=category,source=source,reported_verdict=row.get('verdict'),recomputed_from_retained_measurements=value,independent_raw_state_verified=False))
    def baselines(self,raw,files,chain,env):
        product=env.get('sut')
        if not product:raise ValueError('Baseline package requires actual ENV.sut')
        config=self.configuration(files,env,product,chain)
        with tempfile.TemporaryDirectory(prefix='natchan-toolkit-native-') as temp:
            folder=Path(temp)/'input';folder.mkdir();unpack(self.path if not chain else self.write_temp(raw,Path(temp)/'nested.zip'),folder)
            observations=[];runs=[];native_report=None
            for d in sorted(folder.iterdir()):
                if not d.is_dir() or not (d/'run-meta.json').exists():continue
                meta=json.loads((d/'run-meta.json').read_text(encoding='utf-8-sig'));version=meta.get('sut_version')
                if not version:raise ValueError('Generic run-meta.sut_version required')
                if env.get('sut_version') and env['sut_version']!=version:raise ValueError('Baseline ENV/run version conflict')
                if meta.get('gitea') is not None and meta['gitea']!=version:raise ValueError('Generic/legacy version aliases conflict')
                if 'sut_log_repo_path_2xx' in meta and meta.get('sut_log_reach')!=meta['sut_log_repo_path_2xx']:raise ValueError('Generic/legacy reach aliases conflict')
                counts=self.log_counts({'sut.log':(d/'sut.log').read_bytes()},config,chain+[d.name],ignore_case=True)
                for key,value in counts.items():
                    if key in meta and meta[key]!=value:raise ValueError('Baseline raw/metadata counter conflict: '+key)
                for k,alias in (config or {}).get('logs',{}).get('run_meta_aliases',{}).items():
                    if k=='note':continue
                    if k in meta and alias in meta and meta[k]!=meta[alias]:raise ValueError('Configured alias conflict')
                # Make legacy compatibility aliases only in a disposable copy. Originals are untouched.
                if product=='gitea':
                    meta['gitea']=version
                    if 'sut_log_reach' in meta:meta['sut_log_repo_path_2xx']=meta['sut_log_reach']
                    (d/'run-meta.json').write_text(json.dumps(meta),encoding='utf-8')
                else:
                    run_id=self.path.stem+':'+d.name;status=None
                    if meta['tool']=='evomaster':
                        sys.path.insert(0,str(ROOT.parent/'natchan-v015'));import native_analysis as native
                        state=native.lifecycle(d);status=state['process_status']
                        self.gap('GENERIC_NATIVE_REPORT_PARSER_NOT_AVAILABLE',run=run_id,tool=meta['tool'],process_status=status)
                    else:self.gap('GENERIC_NATIVE_REPORT_PARSER_NOT_AVAILABLE',run=run_id,tool=meta['tool'])
                    if meta['tool']=='schemathesis':
                        import xml.etree.ElementTree as ET
                        for junit in sorted(d.rglob('junit*.xml')):
                            tree=ET.fromstring(junit.read_bytes());cases=list(tree.iter('testcase'))
                            name=junit.relative_to(folder).as_posix();source=self.source(files,name,chain,record='native-report')
                            observations.append(dict(id=run_id+':'+name,product=product,product_version=version,tool='schemathesis',run_id=run_id,source=source,facts=dict(native_report_observed=True,native_testcases=len(cases),native_failed_testcases=sum(any(c.find(k) is not None for k in ['failure','error']) for c in cases)),fact_basis='recomputed',evidence_tier='native_tool_report'))
                    runs.append(dict(id=run_id,product=product,version=version,tool=meta['tool'],log_pattern_counts=counts,native_status=status))
            if product=='gitea':
                sys.path.insert(0,str(ROOT.parent/'natchan-v015'));import native_analysis as native
                native_report=native.run(folder,Path(temp)/'analysis');common=native_report['common_analysis']
                observations=common['observations'];runs=common['runs']
                for r in native_report['runs']:
                    state=r['lifecycle']
                    if r['tool']=='evomaster' and (state.get('native_fault_count') is None or state.get('process_status')!='complete'):self.gap('NATIVE_TOOL_INCOMPLETE_OR_FAULT_COUNT_UNKNOWN',run=r['run_id'],detail=state)
                # Keep signature evidence explicit; it is not an exact known-bug match.
                self.baseline_signatures=native_report['signature_counts']
                self.baseline_findings=[dict(f,tool=r['tool'],run_id=r['run_id'],product=product,product_version=r['version']) for r in native_report['runs'] for f in r['signatures']['findings']]
            def bind(value):
                if isinstance(value,dict):
                    if 'file' in value and isinstance(value['file'],str):
                        p=Path(value['file'])
                        if p.is_relative_to(folder):
                            name=p.relative_to(folder).as_posix();value.update(file=str(self.path),archive_sha256=self.archive_sha,members=chain+[name])
                            if name in files:value['sha256']=digest(files[name])
                    for v in value.values():bind(v)
                elif isinstance(value,list):
                    for v in value:bind(v)
            bind(observations);bind(runs)
            if hasattr(self,'baseline_findings'):bind(self.baseline_findings)
            self.parts.append((self.path.stem+':baselines',dict(observations=observations,runs=runs,original_oracles=[])))
            self.summaries.extend(runs)
        for n in files:
            if n.endswith(('run-meta.json','sut.log','tool-console.log','report.json','.xml','.ndjson')):self.inputs.append(self.source(files,n,chain))
    @staticmethod
    def write_temp(raw,path):path.write_bytes(raw);return path
    def finish(self):
        self.walk(self.raw)
        report=analyze(self.parts)
        report.update(schema_version='natchan-toolkit-analysis/1',toolkit_coverage_gaps=self.gaps,toolkit_packages=self.packages,toolkit_configurations=self.configurations,producer_measurements=self.measurements,input_inventory=self.inputs,toolkit_run_summaries=self.summaries,baseline_log_signature_counts=getattr(self,'baseline_signatures',{}),toolkit_log_findings=getattr(self,'baseline_findings',[]),new_sut_requests=0,analyst_narrative_used=False)
        return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sut-config',type=Path);p.add_argument('--sut-config-sha256');p.add_argument('--toolkit-repo',type=Path);a=p.parse_args()
    report=Reader(a.input,a.sut_config,a.sut_config_sha256,a.toolkit_repo).finish()
    a.output.mkdir(parents=True);(a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'toolkit_runs':len(report['runs']),'http_records':report['evidence_summary']['http_records'],'gaps':len(report['toolkit_coverage_gaps'])}))
if __name__=='__main__':main()
