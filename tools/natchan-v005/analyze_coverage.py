"""Extend v004 with original nested Vikunja evidence and complete conditional catalogs."""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v004'))
import analyze as baseline
from tse_gateways import digest, parsed
from coverage_classifier import classify
from providers import evaluate


def checked_zip(raw):
    archive=zipfile.ZipFile(io.BytesIO(raw))
    names=archive.namelist()
    if len(names)!=len(set(names)) or len(names)>20000 or sum(i.file_size for i in archive.infolist())>128*1024*1024:
        raise ValueError('Unsafe/oversized evidence archive')
    return archive


def member_bytes(archive,names):
    for name in names:
        raw=archive.read(name)
        if name != names[-1]:archive=checked_zip(raw)
    return raw


def scoped_lock_links(records,text):
    """A paired per-run log, with unique method/path/status in BOTH directions."""
    logs=[]
    for line_number,line in enumerate(text.splitlines(),1):
        m=re.search(r'method=(\w+) uri=/api/v1(\S+) status=(\d+).*err="([^"]+)"',line)
        if m and 'database is locked' in m[4]:logs.append((m[1],m[2],int(m[3]),line_number,line))
    links={}
    for i,row in enumerate(records):
        key=(row.get('method'),row.get('path'),row.get('status'))
        candidates=[l for l in logs if l[:3]==key]
        counterparts=[r for r in records if r.get('category')=='research' and (r.get('method'),r.get('path'),r.get('status'))==key]
        if len(candidates)==1 and len(counterparts)==1 and key[2]==500:
            links[i]={'line':candidates[0][3],'message':candidates[0][4],
                      'basis':'explicitly paired run log; unique method/path/status; temporal duration not inferred'}
    return links


def archive_observations(spec,path,contract):
    raw=path.read_bytes()
    if digest(raw)!=spec['sha256']:raise ValueError('Archive hash mismatch')
    outer=checked_zip(raw);member=spec['journal_members']
    journal=member_bytes(outer,member)
    rows=[json.loads(l) for l in journal.decode('utf-8-sig').splitlines() if l.strip()]
    # Retain original positions including non-HTTP records.
    transcript=[dict(row,method=row.get('method') or '',path=row.get('path') or '',body=row.get('input'),response=parsed(row.get('response'))) for row in rows]
    source={'file':str(path),'archive_sha256':digest(raw),'members':member,'sha256':digest(journal)}
    run=dict(id=spec['id'],product='vikunja',version=spec['version'],tool='provengo',seed=spec.get('seed'),source=source)
    observations,_=baseline.vikunja_observations(run,{'records':transcript},contract)
    ir=json.loads(member_bytes(outer,spec['ir_members']))
    if ir.get('source',{}).get('version','').lstrip('v')!=spec['version']:raise ValueError('IR version mismatch')
    links={}
    if spec.get('paired_log_members'):
        logs=member_bytes(outer,spec['paired_log_members'])
        links=scoped_lock_links(rows,logs.decode('utf-8-sig'))
    for i,(obs,row) in enumerate(zip(observations,rows)):
        if i in links:
            # F01 root-cause signature is the observed write/lock pair, not a causal timing claim.
            seen_task=any(r.get('method')=='PUT' and re.fullmatch('/projects/[^/]+/tasks',r.get('path','')) and baseline.successful(r.get('status')) for r in rows[:i])
            obs['facts'].update(correlated_lock=True,prior_task_create_seen=seen_task)
            obs['witnesses'].append(dict(links[i],members=spec['paired_log_members']))
        request=obs.get('request')
        if not isinstance(request,dict) or not baseline.successful(obs['status']):continue
        # The original 2.6.0 IR carries the exact external_id constraint.
        team=next((e for e in ir.get('entities',[]) if e.get('name')=='ModelsTeam'),{})
        bound=team.get('update_schema',{}).get('properties',{}).get('external_id',{}).get('maxLength')
        if obs['entity']=='teams' and isinstance(request.get('external_id'),str) and type(bound) is int and len(request['external_id'])>bound:
            obs['provider_checks']=[evaluate(dict(family='EDGE-1',source=obs['source'],status=obs['status'],
                                                value=request['external_id'],constraints={'maxLength':bound}))]
            next_row=rows[i+1] if i+1<len(rows) else {}
            back=parsed(next_row.get('response'))
            if next_row.get('method')=='GET' and next_row.get('path')==row.get('path') and next_row.get('session')==row.get('session') and next_row.get('status')==200 and isinstance(back,dict) and back.get('external_id')==request['external_id']:
                obs['facts'].update(external_id_bound_violated_and_persisted=True,external_id_maxlength=bound)
                obs['witnesses'].extend([{'readback_record':i+1},{'IR_members':spec['ir_members'],'maxLength':bound}])
    observations=[o for o,r in zip(observations,rows) if r.get('category')=='research' and r.get('method')]
    return observations


def parse_trap_context(logical_id):
    """Producer logical-name grammar supplies context, NEVER proves an input value."""
    m=re.fullmatch(r'(.+)_EDGE(U)?_(tag_name|target_commitish|email)_(.+)',logical_id or '')
    if not m:return None
    return {'entity':m[1].lower(),'operation':'update' if m[2] else 'create','field':m[3],'value_kind':m[4],
            'evidence_level':'producer_context_only; original request body absent'}


def augment_gitea(observations,records=None):
    for obs in observations:
        if obs['product']!='gitea':continue
        request=obs.get('request')
        if not isinstance(request,dict):continue
        if isinstance(request.get('tag_name'),str):
            obs['facts']['original_tag_input_verified']=True
            obs['facts']['original_tag_contains_nul']='\x00' in request['tag_name']
        if isinstance(request.get('target_commitish'),str):obs['facts']['original_target_input_verified']=True
    if records is None:return
    for obs in observations:
        if obs['entity']!='organization' or obs['operation']!='update' or obs['status']!=422:continue
        pos=obs['source']['record'];row=records[pos];request=obs.get('request')
        context=parse_trap_context(row.get('logical_id'))
        if not context or context['field']!='email' or not isinstance(request,dict) or not isinstance(request.get('email'),str):continue
        if not re.search('email',str(obs.get('response')),re.I):continue
        earlier=[(i,r) for i,r in enumerate(records[:pos]) if r.get('category')=='research']
        prior=earlier[-1][1] if earlier else {}
        if prior.get('method')!='GET' or prior.get('path')!=row.get('path') or prior.get('status')!=200 or prior.get('session')!=row.get('session'):continue
        creates=[]
        for candidate in observations:
            cp=candidate['source']['record']
            if cp>=pos or candidate['operation']!='create' or candidate['entity']!='organization' or not baseline.successful(candidate['status']):continue
            cr=records[cp];cc=parse_trap_context(cr.get('logical_id'));body=candidate.get('request')
            if cc and cc['field']=='email' and cc['value_kind']==context['value_kind'] and cr.get('session')==row.get('session') and isinstance(body,dict) and body.get('email')==request['email']:creates.append(candidate)
        if len(creates)==1:
            obs['facts'].update(same_email_value_pair_verified=True,create_accepted_update_rejected=True,update_status=422)
            obs.setdefault('witnesses',[]).extend([{'paired_create':creates[0]['source']},{'update_preimage':earlier[-1][0]}])


def cloud_candidates(spec,path,oracle_path):
    raw=path.read_bytes()
    if digest(raw)!=spec['sha256']:raise ValueError('Cloud summary hash mismatch')
    summary=json.loads(raw);oracles=[json.loads(s) for s in oracle_path.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    result=[]
    for record in summary.get('http_5xx',[]):
        context=parse_trap_context(record.get('logical_id'))
        if not context or context['entity']!='release':continue
        id=('GIT-C5' if context['field']=='tag_name' and context['value_kind']=='nul' else
            'GIT-C4' if context['field']=='tag_name' else 'GIT-C6' if context['field']=='target_commitish' and context['operation']=='create' else None)
        if id:result.append({'id':id,'status':'compatible_symptom_only','run_id':spec['id'],'context':context,
                             'observed':{k:record.get(k) for k in ['method','path','status','t_utc','index']},
                             'source':{'file':str(path),'sha256':digest(raw),'json_pointer':'/http_5xx/'+str(summary['http_5xx'].index(record))},
                             'missing':['original request body','correlated original server log'],
                             'confirmed_known_bug':False})
    for i,row in enumerate(oracles):
        if row.get('category')!='divergence-check':continue
        a,b=row.get('create',{}),row.get('update',{})
        ca,cb=parse_trap_context(a.get('logical_id')),parse_trap_context(b.get('logical_id'))
        if ca and cb and ca['entity']=='organization' and ca['field']=='email' and cb['field']=='email' and ca['value_kind']==cb['value_kind'] and baseline.successful(a.get('status')) and b.get('status')==422:
            result.append({'id':'GIT-C7','status':'compatible_symptom_only','run_id':spec['id'],'context':ca,
                           'observed':{'create_status':a['status'],'update_status':b['status']},
                           'source':{'file':str(oracle_path),'sha256':digest(oracle_path.read_bytes()),'record':i},
                           'missing':['original create/update request values and identity/precondition witnesses'],
                           'confirmed_known_bug':False})
    return result


def provider_audit(observations,oracles):
    from classify_measurements import make_observation
    counts={name:Counter() for name in ['RESPONSE','EDGE-1','RT-1','ATOM-1-2','EDGE-U','KNOWN','CASCADE-1','ADJ','IDEM','VIEW','LINK']}
    missing=Counter()
    provider_observations=[]
    exact_metadata={json.dumps(o['source'],sort_keys=True):o for o in observations}
    scopes={}
    for o in observations:
        group=scopes.setdefault(o['source']['file'],{k:set() for k in ['product','product_version','run_id']})
        for key in group:group[key].add(o.get(key))
    def add(probe):
        result=evaluate(probe)
        counts[probe['family']][result['status']]+=1
        if result['status']=='not_evaluable':
            for key in result['missing']:missing[probe['family']+': '+key]+=1
        elif result['status']=='evaluated':
            origin=exact_metadata.get(json.dumps(probe['source'],sort_keys=True))
            if origin is None:
                origin={k:next(iter(v)) for k,v in scopes.get(probe['source']['file'],{}).items() if len(v)==1}
            linked=dict(probe,id='provider-'+str(len(provider_observations)),product=origin.get('product','unknown'),
                        product_version=origin.get('product_version'),run_id=origin.get('run_id','source-'+digest(probe['source']['file'].encode())[:12]),
                        entity=origin.get('entity'))
            provider_observations.append(make_observation(linked,result))
    c={k:True for k in ['same_run','ordered','complete','same_resource','same_actor','no_intervening_write']}
    for o in observations:
        add(dict(family='RESPONSE',source=o['source'],status=o['status']))
        for existing in o.get('provider_checks',[]):
            counts[existing['family']][existing['status']]+=1
        for w in o.get('witnesses',[]):
            if all(k in w for k in ['field','sent','stored']):
                # A comparison over the retained compared-field measurement, not a new snapshot.
                add(dict(family='RT-1',source=o['source'],status=o['status'],sent={w['field']:w['sent']},
                         readback={w['field']:w['stored']},readable_fields=[w['field']],context=c,
                         field_formats=o.get('field_formats',{})))
        if o.get('action')=='cascade_verify':
            add(dict(family='CASCADE-1',source=o['source'],child_read_status=o['status']))
        if o.get('action')=='adjacency_probe':
            add(dict(family='ADJ',source=o['source'],status=o['status']))
    for oracle in oracles:
        row=oracle['payload'];category=oracle['category'];source=oracle['source']
        if category=='atomicity-check':
            p=dict(family='ATOM-1-2',source=source,status=row.get('first_status'),operation=row.get('kind'))
            for key in ['before','after','request','context']:
                if key in row:p[key]=row[key]
            add(p)
        elif category=='divergence-check':
            add(dict(family='EDGE-U',source=source,create=row.get('create',{}),update=row.get('update',{})))
        elif category=='link2-check' and row.get('mode')=='own' and row.get('readback_status')==200 and isinstance(row.get('listed'),list):
            actions={'link2_add':'add','link2_add_dup':'add_again','link2_remove':'remove'}
            if row.get('action') in actions and isinstance(row.get('sent'),list) and len(row['sent'])==1:
                add(dict(family='LINK',source=source,operation=actions[row['action']],target_id=row['sent'][0],actual_ids=row['listed'],context=c))
    provider_report=classify(provider_observations,ROOT/'catalogs')
    # The provider layer is supplementary. Do not sum its overlapping detections
    # with the primary event findings as independent bugs.
    return {'families':{k:dict(v) for k,v in counts.items()},'missing_measurements':dict(missing),
            'classification_groups':provider_report['groups'],
            'classifications':[a for a in provider_report['assessments'] if a.get('status')=='matched'],
            'zero_applications_means_no_adapted_measurement_not_zero_failures':True,
            'readback_basis':'retained compared-field values; original producer identity/order semantics',
            'independent_full_state_recheck':False}


def run(manifest,evidence_root):
    base_manifest=json.loads((ROOT.parent/'natchan-v004/manifest-tse-v004.json').read_text())
    base=baseline.analyze_manifest(base_manifest,evidence_root)
    contract_path=evidence_root/next(s['contract'] for s in base_manifest['runs'] if s.get('contract'))
    contract=json.loads(contract_path.read_text(encoding='utf-8-sig'))
    observations=list(base['observations']);runs=list(base['runs']);candidates=[]
    augment_gitea(observations)
    for spec in manifest.get('transcript_log_pairs',[]):
        document=json.loads((evidence_root/spec['path']).read_text(encoding='utf-8-sig'))
        rows=[dict(r,category='research') for r in document['transcript']]
        log_path=evidence_root/spec['log'];raw=log_path.read_bytes()
        if digest(raw)!=spec['log_sha256']:raise ValueError('Paired log hash mismatch')
        links=scoped_lock_links(rows,raw.decode('utf-8-sig'))
        for obs in observations:
            if obs['run_id']!=spec['run_id']:continue
            i=obs['source']['record']
            if i in links:
                seen=any(r.get('method')=='PUT' and re.fullmatch('/projects/[^/]+/tasks',r.get('path','')) and baseline.successful(r.get('status')) for r in rows[:i])
                obs['facts'].update(correlated_lock=True,prior_task_create_seen=seen)
                obs['witnesses'].append(dict(links[i],file=str(log_path),sha256=digest(raw)))
    for spec in manifest['archives']:
        extra=archive_observations(spec,evidence_root/spec['path'],contract)
        observations.extend(extra)
        runs.append({'id':spec['id'],'product':'vikunja','version':spec['version'],'tool':'provengo','http_records':len(extra),
                     'http_5xx':sum(o['status']==500 for o in extra),'source_sha256':spec['sha256']})
    for spec in manifest['cloud_summaries']:
        candidates.extend(cloud_candidates(spec,evidence_root/spec['path'],evidence_root/spec['oracles']))
    result=classify(observations,ROOT/'catalogs')
    result.update(schema_version='natchan-coverage-analysis/1',runs=runs,original_oracles=base['original_oracles'],
                  original_oracle_summary=base['original_oracle_summary'],candidate_known_signatures=candidates)
    result['known_signature_occurrences']=dict(sorted(Counter(a['catalog_id'] for a in result['assessments'] if a.get('kind')=='known_bug').items()))
    result['provider_audit']=provider_audit(observations,base['original_oracles'])
    result['coverage_scope']={'Gitea_C4_C7':'Executable complete conditions plus partial evidence candidates; no false confirmation from missing bodies/logs',
                             'Vikunja_F01':'Matched only against uniquely paired per-run lock logs; timing/handler causation not inferred',
                             'Vikunja_F03':'Recomputed from original 2.6.0 IR maxLength and immediate readback',
                             'trap_providers':'All 11 families implemented over explicit normalized measurements; missing raw snapshots stay unevaluable'}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence-root',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=ROOT/'manifest-coverage-v005.json')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    report=run(json.loads(a.manifest.read_text()),a.evidence_root)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('NATCHAN_V005_COMPLETE '+str(a.output.resolve()))


if __name__=='__main__':main()
