"""Offline pinned evidence acceptance; no new SUT traffic or producer verdicts.
Counterfactual repairs are explicitly synthetic and never overwrite original files.
"""
import argparse,copy,hashlib,io,json
from collections import Counter
from pathlib import Path
from common import engine_hashes
from contract_context import derive
from judge import analyze
from traffic import exchanges
from relational_observations import walk,metrics


def inspect(rows,context):
    buf=io.StringIO();result=analyze(rows,context,buf,capture={})
    findings=[v for v in map(json.loads,buf.getvalue().splitlines()) if v['property'] in ('S4','S6') and v['value']=='policy_observation']
    return result,findings


def values(body,pointer):
    path=pointer.strip('/').split('/');items=[body]
    for part in path[:-1]:
        items=[x for item in items for x in (item if part=='*' and isinstance(item,list) else [item[part]] if isinstance(item,dict) and part in item else [])]
    return [(item,path[-1]) for item in items if isinstance(item,dict) and path[-1] in item]


def repair(rows,verdict):
    by_line={r['source']['line_1based']:r for r in rows}
    evidence=[by_line[e['line_1based']] for e in verdict['evidence']]
    reason=verdict['reason'];d=verdict['details']
    if reason=='REFERENCE_TO_OBSERVED_ABSENT_RESOURCE':
        evidence[1]['status']=200
    elif reason=='COPY_INTERNAL_REFERENCE_NOT_IN_COPIED_TARGETS':
        after,before=evidence
        old=values(before['response'],d['target_pointer']);new=values(after['response'],d['target_pointer'])
        mapping={a[k]:b[j] for (a,k),(b,j) in zip(old,new)}
        for obj,k in values(after['response'],d['reference_pointer']):obj[k]=mapping.get(obj[k],obj[k])
    elif reason=='SCALED_ACTION_NONLINEAR_DELTA':
        after,first_before,first_after,before=evidence;field=d['scale_field']
        a,b,c=metrics(first_before['response'],True),metrics(first_after['response'],True),metrics(before['response'],True)
        for pointer in d['metric_pointers']:
            wanted=c[pointer]+(b[pointer]-a[pointer])*(__import__('decimal').Decimal(str(after['input'][field]))/__import__('decimal').Decimal(str(first_after['input'][field])))
            pairs=values(after['response'],pointer);current=sum(__import__('decimal').Decimal(str(o[k])) for o,k in pairs)
            obj,k=pairs[0];obj[k]=float(__import__('decimal').Decimal(str(obj[k]))+wanted-current)
    elif reason=='MOVE_AGGREGATE_TRANSFER_MISMATCH':
        _,child,old,new,entity,write,old_after=evidence
        new_after=evidence[0]
        cm,om,nm=metrics(child['response']),metrics(old['response']),metrics(new['response'])
        for pointer in d['metric_pointers']:
            for target,wanted in [(old_after,om[pointer]-cm[pointer]),(new_after,nm[pointer]+cm[pointer])]:
                pairs=values(target['response'],pointer)
                if len(pairs)!=1:raise AssertionError('Control requires one scalar metric')
                obj,k=pairs[0];obj[k]=float(wanted)
    elif reason=='MOVED_ENTITY_REMAINS_UNDER_OTHER_PARENT':
        after,before,view,write=evidence;field=d['reference_field'];wanted=write['input'][field]
        for obj,_,parents in walk(after['response']):
            if obj.get('id')==before['response'].get('id') and field in obj:
                obj[field]=wanted
                for parent,_ in parents:
                    if 'id' in parent:parent['id']=wanted
    else:raise AssertionError(reason)


def run(root,mealie_contract,output):
    if output.exists():raise ValueError('Use a new output directory')
    manifest=json.loads((Path(__file__).parent/'tests/fixtures/step34-real-manifest.json').read_text())
    results=[]
    for case in manifest['cases']:
        path=root/case['journal'];cb=(mealie_contract if case['system']=='mealie' else root/case['contract']).read_bytes()
        raw=path.read_bytes()
        normalized=raw.replace(b'\r\n',b'\n').rstrip(b'\n')+b'\n'
        if hashlib.sha256(normalized).hexdigest()!=case['journal_lf_sha256']:raise ValueError('Journal content hash mismatch: '+case['journal'])
        document=json.loads(cb)
        canonical=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        if hashlib.sha256(canonical).hexdigest()!=case['contract_json_sha256']:raise ValueError('Contract content hash mismatch')
        context=derive(document,hashlib.sha256(cb).hexdigest())
        rows=list(exchanges(path,'journal-jsonl',hashlib.sha256(raw).hexdigest(),{}))
        result,findings=inspect(rows,context)
        observed=[{'reason':v['reason'],'lines':[e['line_1based'] for e in v['evidence']]} for v in findings]
        if observed!=case['witnesses']:raise AssertionError((case['system'],'Frozen witness mismatch',observed))
        for v in findings:
            needed={e['line_1based'] for e in v['evidence']}
            witness=[copy.deepcopy(r) for r in rows if r['source']['line_1based'] in needed]
            _,positive=inspect(witness,context)
            if not any(p['reason']==v['reason'] for p in positive):raise AssertionError(('Witness not self-contained',v['reason']))
            repair(witness,v);_,negative=inspect(witness,context)
            if any(p['reason']==v['reason'] for p in negative):raise AssertionError(('Repaired witness still flagged',v['reason']))
        results.append({'system':case['system'],'exchanges':result['exchanges'],'observations':dict(Counter(v['reason'] for v in findings)),
                        'counterfactual_controls_passed':len(findings),'proven_semantic_violations':result['finding_partitions']['semantic_candidate']['occurrences']})
    output.mkdir(parents=True)
    report={'status':'PASS','new_SUT_requests':0,'resampled':False,'producer_verdicts_used':False,'engine':engine_hashes(),
            'manifest_sha256':hashlib.sha256((Path(__file__).parent/'tests/fixtures/step34-real-manifest.json').read_bytes()).hexdigest(),
            'controls':'Synthetic repaired witnesses, not additional SUT runs','results':results}
    (output/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['results']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study-root',type=Path,required=True);p.add_argument('--mealie-contract',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.study_root,a.mealie_contract,a.output)
