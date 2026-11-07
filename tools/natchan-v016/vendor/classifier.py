"""Deterministic offline finding classification and conservative known-bug matching."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime

ROOT=Path(__file__).resolve().parent
MISSING=object()


def get(record,path):
    value=record
    for part in path.split('.'):
        if not isinstance(value,dict) or part not in value:return MISSING
        value=value[part]
    return value


def same(left,right):
    if type(left) is bool or type(right) is bool:return type(left) is type(right) and left==right
    if isinstance(left,(int,float)) and isinstance(right,(int,float)):return left==right
    if isinstance(left,dict) and isinstance(right,dict):return left.keys()==right.keys() and all(same(left[k],right[k]) for k in left)
    if isinstance(left,list) and isinstance(right,list):return len(left)==len(right) and all(same(a,b) for a,b in zip(left,right))
    return type(left) is type(right) and left==right


def match(facts,condition):
    value=get(facts,condition['fact']);op=condition['op'];expected=condition.get('value')
    if op=='present':return value is not MISSING
    if value is MISSING:return False
    if op=='eq':return same(value,expected)
    if op=='in':return any(same(value,e) for e in expected)
    if op=='gte':return type(value) in (int,float) and value>=expected
    raise ValueError('Unsupported operator: '+op)


def load_catalogs(directory):
    paths=sorted(Path(directory).glob('*.json'))
    if not paths:raise ValueError('No catalogs found')
    entries=[];ids=set();sources=[]
    for path in paths:
        raw=path.read_bytes();doc=json.loads(raw)
        if doc.get('schema_version')!='natchan-catalog/1':raise ValueError('Unsupported catalog version')
        sources.append(dict(name=path.name,sha256=hashlib.sha256(raw).hexdigest()))
        for entry in doc['entries']:
            for key in ['id','kind','title','status','product','versions','all','evidence_requirements','exclusions','provenance','severity','human_review']:
                if key not in entry:raise ValueError('Missing catalog field '+key)
            if entry['id'] in ids:raise ValueError('Duplicate catalog ID')
            ids.add(entry['id'])
            if entry['kind'] not in ('pattern','known_bug'):raise ValueError('Invalid entry kind')
            if entry['status'] not in ('active','draft'):raise ValueError('Invalid entry status')
            if not isinstance(entry['all'],list) or not entry['all']:raise ValueError('Unconditional rules are forbidden')
            for c in entry['all']+entry['exclusions']:
                if c.get('op') not in ('eq','in','gte','present') or not isinstance(c.get('fact'),str):raise ValueError('Invalid predicate')
            if entry['kind']=='known_bug' and entry['status']=='active' and (entry['product']=='*' or not entry['versions']):
                raise ValueError('Active known bugs need explicit product and versions')
            entries.append(entry)
    return entries,sources


def normalized_message(message):
    # Keep semantic numbers (e.g., maxLength 250). Strip only explicit instance identifiers.
    message=re.sub(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b','<uuid>',message)
    return re.sub(r'\b(id[=: ]+)\d+\b',r'\1<id>',message,flags=re.I)


def field_same(observation,key,left,right):
    if observation.get('field_formats',{}).get(key)=='date-time' and isinstance(left,str) and isinstance(right,str):
        try:
            a=datetime.fromisoformat(left.replace('Z','+00:00'));b=datetime.fromisoformat(right.replace('Z','+00:00'))
            if a.tzinfo is not None and b.tzinfo is not None:return a==b
        except ValueError:pass
    return same(left,right)


def derived(observation):
    facts=dict(observation.get('facts',{}))
    # Imported semantic facts remain claims unless a trusted adapter recomputed them.
    if facts and observation.get('fact_basis')!='recomputed':
        facts={}
    status=observation.get('status')
    if type(status) is int:facts['server_error']=500<=status<=599
    if observation.get('transport_error'):
        facts['transport_failure']=status is None
    before=observation.get('before');after=observation.get('after');request=observation.get('request')
    trusted=observation.get('state_evidence',{})
    qualified=(trusted.get('same_resource') is True and trusted.get('same_actor') is True and
               trusted.get('ordered') is True and trusted.get('no_intervening_write') is True and trusted.get('complete') is True)
    if qualified and isinstance(before,dict) and isinstance(after,dict) and isinstance(request,dict):
        keys=[k for k in request if k in before and not field_same(observation,k,before[k],request[k])]
        states=['applied' if k in after and field_same(observation,k,after[k],request[k]) else 'kept' if k in after and field_same(observation,k,after[k],before[k]) else 'other' for k in keys]
        if facts.get('server_error') and states:
            facts['atomicity']=('partial' if 'applied' in states and 'kept' in states and 'other' not in states else
                'committed_despite_error' if all(s=='applied' for s in states) else
                'rolled_back' if all(s=='kept' for s in states) else 'unknown')
    if qualified and type(status) is int and 200<=status<300 and isinstance(request,dict) and isinstance(after,dict):
        fields=observation.get('readable_writable_fields',[])
        changed=[];dropped=[]
        for key in fields:
            if key not in request:continue
            if isinstance(before,dict) and key in before and field_same(observation,key,request[key],before[key]):continue
            if key not in after:dropped.append(key)
            elif not field_same(observation,key,request[key],after[key]):changed.append(key)
        facts['changed_fields']=changed;facts['dropped_fields']=dropped
        facts['silent_change']=bool(changed or dropped)
    contract=observation.get('contract',{})
    value=get(observation,'request.'+str(observation.get('field','')))
    bound=contract.get('field_constraints',{})
    violated=False
    if isinstance(value,str):
        violated=('minLength' in bound and len(value)<bound['minLength']) or ('maxLength' in bound and len(value)>bound['maxLength'])
    if type(value) in (int,float):
        violated=('minimum' in bound and value<bound['minimum']) or ('maximum' in bound and value>bound['maximum'])
    if bound and value is not MISSING:
        facts['explicit_bound_violated']=bool(violated)
        facts['request_accepted']=type(status) is int and 200<=status<300
    log=observation.get('server_log',{})
    if (isinstance(observation.get('request_id'),str) and observation['request_id'] and
            log.get('request_id')==observation['request_id'] and log.get('run_id')==observation['run_id']):
        facts['log_correlation_verified']=True
        if re.search(r'database (?:table )?is locked|deadlock detected',str(log.get('message','')),re.I):
            facts['log_error_family']='database_lock'
    if 'field_constraints' in contract and isinstance(value,str) and type(status) is int and 400<=status<500:
        message=json.dumps(observation.get('response',''))
        if 'maxLength' not in bound and re.search(r'MaxSize|too long|maximum length',message,re.I):
            facts['restriction_observed']=True;facts['restriction_documented']=False
            if observation['product']=='gitea' and observation.get('entity')=='organizations' and observation.get('field')=='name':
                facts['organization_name_context_verified']=True
    if 'documented_statuses' in contract and type(status) is int:
        facts['response_documented']=str(status) in [str(v) for v in contract['documented_statuses']]
    return facts


def paired_facts(observations):
    derived_by_id={o['id']:derived(o) for o in observations}
    pairs={}
    for obs in observations:
        if obs.get('pair_id'):
            key=(obs['product'],obs.get('product_version'),obs['run_id'],obs['pair_id'])
            pairs.setdefault(key,[]).append(obs)
    for members in pairs.values():
        creates=[o for o in members if o.get('operation')=='create']
        updates=[o for o in members if o.get('operation')=='update']
        if len(creates)!=1 or len(updates)!=1:continue
        a,b=creates[0],updates[0];field=a.get('field')
        qualification=['same_schema_context','compatible_preconditions']
        if not field or b.get('field')!=field or a.get('entity')!=b.get('entity'):continue
        if not all(o.get('pair_evidence',{}).get(k) is True for o in [a,b] for k in qualification):continue
        left=get(a,'request.'+field);right=get(b,'request.'+field)
        if left is MISSING or right is MISSING or not same(left,right):continue
        x,y=a.get('status'),b.get('status')
        if type(x) is not int or type(y) is not int:continue
        facts=derived_by_id[b['id']];facts['pair_qualified']=True
        mismatch=(200<=x<300 and 400<=y<500) or (400<=x<500 and 200<=y<300)
        stored_a=get(a,'after.'+field);stored_b=get(b,'after.'+field)
        state_keys=['same_resource','same_actor','ordered','no_intervening_write','complete']
        observable=all(o.get('state_evidence',{}).get(k) is True for o in [a,b] for k in state_keys)
        if 200<=x<300 and 200<=y<300 and observable and stored_a is not MISSING and stored_b is not MISSING:
            mismatch=not field_same(a,field,stored_a,stored_b)
        facts['create_update_diverge']=mismatch
        facts['create_update_partial_compound']=(200<=x<300 and 500<=y<=599 and derived_by_id[a['id']].get('silent_change') is True and facts.get('atomicity')=='partial')
    return derived_by_id


def classify(observations,catalog_dir=ROOT/'catalogs'):
    entries,sources=load_catalogs(catalog_dir);results=[];seen=set()
    if any(not isinstance(o,dict) or any(k not in o for k in ['id','product','run_id','source']) for o in observations):
        raise ValueError('Every observation requires id, product, run_id and source')
    computed=paired_facts(observations)
    for obs in observations:
        for key in ['id','product','run_id','source']:
            if key not in obs:raise ValueError('Observation missing '+key)
        if obs['id'] in seen:raise ValueError('Duplicate observation ID')
        seen.add(obs['id']);facts=computed[obs['id']]
        matched=[];possible=[]
        for entry in entries:
            if entry['status']!='active' or entry['product'] not in ('*',obs['product']):continue
            if entry['versions'] and obs.get('product_version') not in entry['versions']:continue
            if any(match(facts,c) for c in entry['exclusions']):continue
            checks=[dict(condition=c,satisfied=match(facts,c)) for c in entry['all']]
            if all(c['satisfied'] for c in checks):matched.append((entry,checks))
            elif entry['kind']=='known_bug' and any(c['satisfied'] for c in checks):
                possible.append(dict(id=entry['id'],status='insufficient_evidence',checks=checks))
        if not matched:
            results.append(dict(observation_id=obs['id'],status='unclassified',source=obs['source'],facts=facts,
                                possible_known_bugs=possible,reason='No active rule has sufficient matching evidence'))
            continue
        patterns=[e['id'] for e,_ in matched if e['kind']=='pattern']
        known=[e['id'] for e,_ in matched if e['kind']=='known_bug']
        for entry,checks in matched:
            results.append(dict(observation_id=obs['id'],status='matched',catalog_id=entry['id'],kind=entry['kind'],
                product=obs['product'],product_version=obs.get('product_version'),run_id=obs['run_id'],
                tool=obs.get('tool'),seed=obs.get('seed'),entity=obs.get('entity'),operation=obs.get('operation'),field=obs.get('field'),
                patterns=patterns,known_bugs=known,checks=checks,source=obs['source'],facts=facts,
                primary_event=obs.get('primary_event'),consequence_events=obs.get('consequence_events',[]),
                qualification='known_bug_evidence_match' if entry['kind']=='known_bug' else 'pattern_observation',
                suggested_severity=entry['severity'],human_review=entry['human_review'],
                log_fingerprint=normalized_message(str(obs.get('server_message') or '')),
                possible_known_bugs=possible))
    groups={}
    for row in results:
        if row['status']!='matched':continue
        key=[row.get(k) for k in ['product','product_version','catalog_id','entity','operation','field','log_fingerprint']]
        gid='g-'+hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()[:16]
        group=groups.setdefault(gid,dict(id=gid,catalog_id=row['catalog_id'],kind=row['kind'],signature=key,occurrences=[],runs=[],tools=[],seeds=[]))
        if row['observation_id'] not in group['occurrences']:group['occurrences'].append(row['observation_id'])
        for singular,plural in [('run_id','runs'),('tool','tools'),('seed','seeds')]:
            value=row.get(singular)
            if value is not None and value not in group[plural]:group[plural].append(value)
    for group in groups.values():
        group['occurrence_count']=len(group['occurrences'])
        group['reproducibility']='not_measured; occurrence counts have no eligible-trial denominator'
    return dict(schema_version='natchan-classification/1',catalog_coverage=dict(active_known_bugs=[e['id'] for e in entries if e['kind']=='known_bug' and e['status']=='active'],draft_entries=[e['id'] for e in entries if e['status']=='draft']),catalogs=sources,observations=observations,assessments=results,
                groups=list(groups.values()),summary=dict(observation_count=len(observations),
                unclassified_count=sum(r['status']=='unclassified' for r in results),
                known_bug_ids=sorted({k for r in results for k in r.get('known_bugs',[])})),
                policy=dict(no_llm_required=True,no_replay=True,no_known_bug_suppression=True,
                            imported_oracle_claims_not_verified=True))


def markdown(report):
    def safe(value):return str(value).replace('|','\\|').replace('\n',' ')
    rows=['# Natchan classification', '',
          'Offline rule evaluation. A pattern or signature match is not a newly confirmed root cause.', '',
          'Known bug IDs matched: '+(', '.join(report['summary']['known_bug_ids']) or 'none'),
          'Observations: '+str(report['summary']['observation_count']), '',
          '| Catalog entry | Kind | Occurrences | Runs |', '|---|---|---:|---|']
    for group in report['groups']:
        rows.append('| '+safe(group['catalog_id'])+' | '+safe(group['kind'])+' | '+str(group['occurrence_count'])+' | '+safe(', '.join(group['runs']))+' |')
    rows += ['', '## Evidence and classification', '']
    for row in report['assessments']:
        rows.append('- '+safe(row['observation_id'])+': '+safe(row.get('catalog_id',row['status']))+'; source: '+safe(json.dumps(row['source'],sort_keys=True)))
    rows += ['', '## Pending catalog definitions', '', ', '.join(report['catalog_coverage']['draft_entries']) or 'none', '',
             'Occurrence groups are not summed as unique defects. Cross-run frequency does not establish deterministic reproduction.', '']
    return '\n'.join(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--catalogs',type=Path,default=ROOT/'catalogs')
    args=parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():parser.error('JSON or Markdown output exists')
    document=json.loads(args.input.read_text(encoding='utf-8-sig'))
    if document.get('schema_version')=='natchan-analysis/1':
        from library_adapter import observations_from_analysis
        observations=observations_from_analysis(document)
    elif document.get('schema_version')=='natchan-observations/1':observations=document['observations']
    else:raise ValueError('Unsupported input; a product/tool adapter is required')
    report=classify(observations,args.catalogs)
    report['input_sha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:json.dump(report,target,indent=2);target.write('\n')
    with args.output.with_suffix('.md').open('x',encoding='utf-8') as target:target.write(markdown(report))
    print('NATCHAN_CLASSIFICATION '+str(args.output.resolve()))


if __name__=='__main__':main()

