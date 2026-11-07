"""Offline native-tool analysis: common v014 classifier plus explicit log signatures.

No generated test execution, server calls, or analyst narrative ingestion.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v014'))
import g015_gateway as prior
from engine import analyze

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source(path,line):return dict(file=str(path),sha256=digest(path),record=line)
def clean(text):return re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',text)

def lifecycle(folder):
    path=folder/'tool-console.log'
    text=clean(path.read_text(encoding='utf-8-sig')) if path.exists() else ''
    exits=[int(x) for x in re.findall(r'### exit (-?\d+)',text)]
    fatal=[dict(message=l,source=source(path,i)) for i,l in enumerate(text.splitlines(),1)
           if 'java.lang.IllegalStateException:' in l or 'process terminated abruptly' in l]
    present=(folder/'report.json').exists()
    status='failed' if fatal or any(x!=0 for x in exits) else 'complete' if exits and all(x==0 for x in exits) and present else 'unknown_or_incomplete'
    version=re.search(r'EvoMaster version: (\S+)',text)
    return dict(process_status=status,exit_codes=exits,tool_version=version[1] if version else None,
        native_report_present=present,native_fault_count=None,phase_durations=re.findall(r'Phase (\w+) lasted: ([^\n]+)',text),
        fatal_errors=fatal,search_completed=bool(re.search(r'Phase SEARCH lasted:',text)),
        security_started='Starting phase SECURITY' in text,
        fault_count_meaning='unknown_when_native_report_missing')

def signatures(path):
    catalog=json.loads((ROOT/'log-signatures.json').read_text())
    lines=path.read_text(encoding='utf-8-sig').splitlines();findings=[];unmatched=[]
    sha=digest(path)
    for i,line in enumerate(lines):
        if '[E]' not in line:continue
        rules=[r for r in catalog['rules'] if re.search(r['pattern'],line)]
        if not rules:
            unmatched.append(dict(source=dict(file=str(path),sha256=sha,record=i+1),text=line));continue
        for rule in rules:
            access=prior.access_line(lines[i+1]) if i+1<len(lines) else None
            stamp=re.match(r'\d{4}/\d\d/\d\d \d\d:\d\d:\d\d',line)
            paired=(access and stamp and lines[i+1].startswith(stamp[0]) and
                'method' in rule and re.fullmatch(rule['method'],access[0]) and
                re.fullmatch(rule['path'],urlsplit(access[1]).path) and access[2]>=500)
            row=dict(signature_id=rule['id'],kind=rule['kind'],known_bug_candidate=rule['known_bug'],
                exact_known_bug_confirmed=False,native_tool_reported=None,
                source=dict(file=str(path),sha256=sha,record=i+1),message=line,
                evidence_tier='server_log_signature',needs_human=True,
                missing_evidence=['request_payload','request_id_correlation','response_body','independent_readback'],
                partial_persistence='not_evaluable',causal_join=False)
            if paired:
                row['adjacent_response_candidate']=dict(method=access[0],path=urlsplit(access[1]).path,status=access[2],
                    source=dict(file=str(path),sha256=sha,record=i+2),association='immediately_adjacent_same_second_operation_compatible_not_request_id_correlated')
            findings.append(row)
    return dict(findings=findings,counts=dict(Counter(f['signature_id'] for f in findings)),unmatched_error_lines=unmatched)

def tool_reach(path):
    statuses=Counter();nested=Counter();patch=Counter()
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        a=prior.access_line(line);caller=re.search(r' for ([^,]+),',line)
        if not a or not caller or re.match(r'\d+\.\d+\.\d+\.1:',caller[1]):continue
        method,target,status=a;statuses[str(status)]+=1
        route=prior.repository_route(target)
        if route:
            nested[str(status//100)+'xx']+=1
            if method=='PATCH' and route[1]:patch[str(status)]+=1
    return dict(completed_requests=sum(statuses.values()),statuses=dict(statuses),nested_status_classes=dict(nested),
        issue_patch_statuses=dict(patch),caller_policy='campaign_host_gateway_dot_1_excluded_not_authentication_attribution')

def run(folder,output):
    if output.exists():raise ValueError('Use a fresh output directory')
    runs=[];parts=[];inventory=[]
    for directory in sorted(folder.iterdir()):
        if not directory.is_dir() or not (directory/'run-meta.json').exists():continue
        meta=json.loads((directory/'run-meta.json').read_text(encoding='utf-8-sig'))
        tool=meta['tool'];log=directory/'sut.log';logs,errors=prior.scan_logs(log)
        native=[]
        if tool=='evomaster':
            state=lifecycle(directory)
            if state['native_report_present']:
                native,claims=prior.evomaster(directory,meta['gitea'])
                state['native_fault_count']=claims['fault_entries'];state['native_claims']=claims
            native += [prior.observation(directory.name,tool,meta['gitea'],e['source'],
                method=e['method'],path=e['path'],status=e['status'],evidence_tier='server_access_status_without_payload') for e in errors]
        elif tool=='schemathesis':
            native,claims=prior.schemathesis(directory,meta['gitea'])
            state=dict(native_claims=claims,process_status='not_assessed_by_evomaster_lifecycle')
        else:raise ValueError('Unsupported native tool '+tool)
        reach=tool_reach(log)
        checks=dict(requests=logs['completed_requests']==meta['sut_log_completed_requests'],
            http_500=sum(1 for e in errors if e['status']==500)==meta['sut_log_500'])
        if 'sut_log_repo_path_2xx' in meta:checks['tool_repo_2xx']=reach['nested_status_classes'].get('2xx',0)==meta['sut_log_repo_path_2xx']
        runs.append(dict(run_id=directory.name,tool=tool,version=meta['gitea'],server=logs,
            lifecycle=state,signatures=signatures(log),tool_caller_reach=reach,metadata_checks=checks))
        parts.append((directory.name,dict(observations=native,runs=[dict(id=directory.name,product='gitea',version=meta['gitea'],tool=tool)])))
        inventory.extend(dict(path=str(p),sha256=digest(p)) for p in sorted(directory.rglob('*')) if p.is_file())
    if not runs:raise ValueError('No supported runs found')
    common=analyze(parts)
    report=dict(schema_version='natchan-native/15',runs=runs,common_analysis=common,
        signature_counts=dict(sum((Counter(r['signatures']['counts']) for r in runs),Counter())),
        input_inventory=inventory,code_inventory=[dict(path=str(p),sha256=digest(p)) for p in [Path(__file__),ROOT/'log-signatures.json']],
        new_sut_requests=0,analyst_narrative_used=False,
        policy=['Signature matches are separate from common exact known-bug matches.',
            'Error log counts are not additional HTTP failures; do not sum them.',
            'Adjacent response candidates are not causal correlation or state evidence.',
            'Unknown native fault count is not zero.'])
    output.mkdir(parents=True);(output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    render(report,output/'report.md')
    print(json.dumps(dict(runs=len(runs),http_5xx=sum(r['server']['http_5xx'] for r in runs),signature_counts=report['signature_counts'])))
    return report

def render(report,path):
    text=['# Natchan v015: Gitea native-tool evidence','',
        'Generated mechanically from retained artifacts. No manual finding narrative was consumed.','',
        '| Run | Requests (all callers) | HTTP 5xx | Tool nested 2xx | Process | Native faults |',
        '|---|---:|---:|---:|---|---:|']
    for r in report['runs']:
        state=r['lifecycle'];n=state.get('native_fault_count')
        text.append('|{}|{}|{}|{}|{}|{}|'.format(r['run_id'],r['server']['completed_requests'],r['server']['http_5xx'],r['tool_caller_reach']['nested_status_classes'].get('2xx',0),state['process_status'],n if n is not None else 'unknown'))
    text += ['','## Log-signature candidates','','These are descriptive/error signatures, not confirmed unique bugs.','',
        '| Signature | Log occurrences |','|---|---:|']
    text += ['|{}|{}|'.format(k,v) for k,v in report['signature_counts'].items()]
    text += ['','## Common classifier','','Rule occurrences: '+json.dumps(report['common_analysis']['rule_occurrences']),
        '', '## Evidence and limits','',*['- '+p for p in report['policy']]]
    for r in report['runs']:
        text += ['','## '+r['run_id'],'','Issue PATCH statuses: '+json.dumps(r['tool_caller_reach']['issue_patch_statuses']),
            '', 'Search complete: '+str(r['lifecycle'].get('search_completed'))+'. Process exit codes: '+str(r['lifecycle'].get('exit_codes'))+'.',
            '', 'Unmatched error lines: '+str(len(r['signatures']['unmatched_error_lines']))+'.']
        for f in r['signatures']['findings']:
            if f['kind'] in ('known_bug_signature_candidate','reference_error_candidate'):
                text += ['', '- '+f['signature_id']+' at sut.log:'+str(f['source']['record'])+
                    '; adjacent compatible response candidate: '+str(bool(f.get('adjacent_response_candidate')))+
                    '; exact bug confirmation: false; partial persistence: not evaluable.']
    path.write_text('\n'.join(text)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.input,args.output)
