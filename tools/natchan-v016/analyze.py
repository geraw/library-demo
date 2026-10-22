"""Offline native-HTTP adapter -> existing Natchan classifier/catalog -> event report.
No SUT execution, analyst verdict import, or LLM classification.
"""
import argparse,collections,hashlib,importlib.util,json,re
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parent
CORE=ROOT.parent/'natchan-v003/classifier.py'
if not CORE.exists():CORE=ROOT/'vendor/classifier.py'
CATALOGS=ROOT.parent/'natchan-v014/catalogs'
if not CATALOGS.exists():CATALOGS=ROOT/'vendor/catalogs'
spec=importlib.util.spec_from_file_location('natchan_v016_legacy_classifier',CORE)
classifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(classifier)

def digest(raw):return hashlib.sha256(raw).hexdigest()
def source(name,raw,line):return dict(file=name,sha256=digest(raw),record=line)
def record_id(s):return 'event-'+digest(json.dumps([s['sha256'],s['record']]).encode())[:28]

def parse_native(raw):
    records=[]
    for number,line in enumerate(raw.decode('utf-8-sig').splitlines(),1):
        if 'SHARED_EVIDENCE ' not in line:continue
        text=line.split('SHARED_EVIDENCE ',1)[1]
        row,end=json.JSONDecoder().raw_decode(text[text.index('{'):])
        if not isinstance(row,dict):raise ValueError('Invalid HTTP receipt')
        if type(row.get('status')) is not int or not 100<=row['status']<=599:raise ValueError('Invalid HTTP status')
        row['source']=source('native.log',raw,number);records.append(row)
    return records

def adapt(records,server_raw,profile,run_id):
    versions={r['response'].get('version') for r in records if r.get('role')=='version' and r['status']==200 and isinstance(r.get('response'),dict)}
    if len(versions)!=1:raise ValueError('A unique observed server version is required')
    version=versions.pop();observations=[];lines=server_raw.decode('utf-8-sig').splitlines()
    router=[]
    for number,line in enumerate(lines,1):
        m=re.search(r'router: completed (GET|POST|PUT|PATCH|DELETE) (\S+) .*?, (\d{3}) ',line)
        if m:router.append((number,m[1],m[2],int(m[3])))
    for i,row in enumerate(records):
        entity=next((s['entity'] for s in profile['entity_routes'] if re.fullmatch(s['pattern'],row['path'])),None)
        operation=profile['methods'].get(row['method']);facts={};witnesses=[]
        if entity:facts['entity']=entity
        if operation:facts['operation']=operation
        group=row.get('group');same=[r for r in records if r.get('group')==group]
        roots=[r for r in same if r.get('role')=='root_fixture' and r['status']==201 and isinstance(r.get('response'),dict)]
        root_id=roots[0]['response'].get('id') if len(roots)==1 else None
        before=next((r for r in reversed(records[:i]) if r.get('group')==group and r['method']=='GET' and r['path']==row['path'] and r.get('actor')==row.get('actor') and r['status']==200),None)
        if not before or classifier.get(before.get('response',{}),profile['item_root_identity'])!=root_id:root_id=None
        # Product log signature must match IDs from raw request/root evidence AND
        # the first subsequent router completion. Multiple eligible receipts/logs
        # remain ambiguous and do not establish a correlated error family.
        if 500<=row['status']<=599:
            for signature in profile['error_signatures']:
                request=row.get('request');field=signature['request_field']
                if entity!=signature['entity'] or not isinstance(request,dict) or type(request.get(field)) is not int or type(root_id) is not int:continue
                competitors=[r for r in records if r['method']==row['method'] and r['path']==row['path'] and r['status']==row['status'] and isinstance(r.get('request'),dict) and r['request'].get(field)==request[field]]
                hits=[]
                for number,line in enumerate(lines,1):
                    m=re.search(signature['pattern'],line)
                    if not m or int(m['target'])!=request[field] or int(m['root'])!=root_id:continue
                    following=next((r for r in router if r[0]>number),None)
                    if following and following[1:]==(row['method'],profile['api_prefix']+row['path'],row['status']):hits.append((number,line,following[0]))
                if len(competitors)==len(hits)==1:
                    facts['correlated_error_family']=signature['family']
                    witnesses += [dict(kind='error_log',source=source('sut.log',server_raw,hits[0][0]),message=hits[0][1]),dict(kind='router_completion',source=source('sut.log',server_raw,hits[0][2])),dict(kind='root_identity',source=roots[0]['source'],value=root_id),dict(kind='item_root_identity',source=before['source'],value=root_id)]
        # Raw readback evidence is attached to the SAME failed HTTP occurrence.
        afters=[]
        for later in records[i+1:]:
            if later.get('group')!=group or later['path']!=row['path']:continue
            if later['method'] not in ['GET','HEAD']:break
            if later['method']=='GET' and later['status']==200:afters.append(later)
        applied=[]
        if row['status']>=500 and before and isinstance(row.get('request'),dict) and isinstance(before.get('response'),dict):
            for field,value in row['request'].items():
                if field not in before['response'] or classifier.same(before['response'][field],value):continue
                readbacks=[r for r in afters if isinstance(r.get('response'),dict) and r['response'].get('id')==before['response'].get('id') and r['response'].get('id') is not None and field in r['response'] and classifier.same(r['response'][field],value)]
                if readbacks:
                    applied.append(field);witnesses += [dict(kind='before',field=field,value=before['response'][field],source=before['source'])]+[dict(kind='persisted_readback',field=field,value=value,source=r['source']) for r in readbacks]
        if applied:facts['field_persisted_despite_error']=True;facts['persisted_fields']=applied
        # Deleted-reference context is independently proved, never read from the
        # producer's observations.json or its candidate labels.
        if isinstance(row.get('request'),dict) and before:
            for prior in records[:i]:
                if prior.get('group')!=group or prior['method']!='DELETE' or not 200<=prior['status']<300:continue
                for signature in profile['error_signatures']:
                    field=signature['request_field'];target=row['request'].get(field)
                    base=(before.get('response') or {}).get(field)
                    reference=re.fullmatch(signature['reference_path'],prior['path'])
                    if records.index(prior)>records.index(before) and type(target) is int and reference and int(reference['target'])==target and prior['path'].rsplit('/',2)[0]==row['path'].rsplit('/',2)[0] and isinstance(base,dict) and base.get('id')==target:
                        facts['deleted_reference_context_verified']=True;witnesses.append(dict(kind='deleted_reference',source=prior['source'],value=target))
        s=row['source'];observations.append(dict(id=record_id(s),product=profile['product'],product_version=version,run_id=run_id,tool='provengo',source=s,
            entity=entity,operation=operation,field=next((s['request_field'] for s in profile['error_signatures'] if facts.get('correlated_error_family')==s['family']),None),
            method=row['method'],path=row['path'],status=row['status'],request=row.get('request'),response=row.get('response'),
            facts=facts,fact_basis='recomputed',witnesses=witnesses,group=group,role=row.get('role')))
    return observations

def analyze_archive(path,profile_path=ROOT/'profiles/gitea-lifecycle.json',catalogs=CATALOGS):
    with zipfile.ZipFile(path) as archive:
        # Validate exported members when a manifest exists. Cached verdicts are
        # neither used as facts nor accepted as proof of known-bug identity.
        manifests=[n for n in archive.namelist() if re.fullmatch(r'EXPORT_g\d+\.json',n)]
        for name in manifests:
            meta=json.loads(archive.read(name));hashes=meta.get('sha256',meta.get('hashes',{}))
            for n,h in hashes.items():
                if digest(archive.read(n))!=h:raise ValueError('Export hash mismatch: '+n)
        native=archive.read('native.log');server=archive.read('sut.log') if 'sut.log' in archive.namelist() else b''
    report=analyze_raw(native,server,path.stem,profile_path,catalogs)
    report['input_archive_sha256']=digest(path.read_bytes())
    return report

def analyze_raw(native,server,run_id,profile_path=ROOT/'profiles/gitea-lifecycle.json',catalogs=CATALOGS):
    records=parse_native(native);profile=json.loads(profile_path.read_text());observations=adapt(records,server,profile,run_id)
    report=classifier.classify(observations,catalogs)
    # Preserve the existing coverage classifier's conservative possible-match rule.
    for a in report['assessments']:
        a['possible_known_bugs']=[p for p in a.get('possible_known_bugs',[]) if all(c['satisfied'] or classifier.get(a['facts'],c['condition']['fact']) is classifier.MISSING for c in p['checks'])]
    findings=[]
    for o in observations:
        tags=[]
        if o['status']>=500:tags.append('SERVER_5XX')
        if o['facts'].get('field_persisted_despite_error'):tags.append('FIELD_PERSISTED_DESPITE_ERROR')
        matches=[a for a in report['assessments'] if a['observation_id']==o['id'] and a['status']=='matched' and a.get('kind')=='known_bug']
        if not tags and not matches:continue
        findings.append(dict(occurrence_id=o['id'],group=o['group'],known_bugs=sorted({a['catalog_id'] for a in matches}),tags=tags,
            match_qualification='known_bug_evidence_match' if matches else 'unmatched_observation',root_cause_identity_proven=False,
            checks=[dict(catalog_id=a['catalog_id'],predicates=a['checks']) for a in matches],facts=o['facts'],source=o['source'],witnesses=o['witnesses'],needs_human=True))
    report.update(schema_version='natchan-native-catalog-analysis/1',findings=findings,
        profile_sha256=digest(profile_path.read_bytes()),classifier_sha256=digest(CORE.read_bytes()),new_sut_requests=0,producer_verdicts_used=False,
        counts=dict(http_records=len(records),failure_occurrences=sum(o['status']>=500 for o in observations),known_bug_occurrences=sum(bool(f['known_bugs']) for f in findings),known_bug_ids=sorted({b for f in findings for b in f['known_bugs']})))
    return report

def markdown(report):
    lines=['# Native lifecycle evidence: known-bug matching','',
        'Offline raw-evidence analysis; no new SUT requests; no producer verdicts imported.',
        'A catalog signature match does not prove identical root cause.','',
        'Known bug IDs: '+(', '.join(report['counts']['known_bug_ids']) or 'none'),
        'Known-bug occurrences: '+str(report['counts']['known_bug_occurrences']),'']
    for f in report['findings']:
        lines+=['## '+f['occurrence_id'],'','Known bugs: '+(', '.join(f['known_bugs']) or 'unmatched'),
            'Group: '+str(f['group']),'Tags: '+', '.join(f['tags']),
            'Deleted-reference context verified: '+str(f['facts'].get('deleted_reference_context_verified',False)),
            'Primary source: '+json.dumps(f['source']), '','Witnesses:']
        lines += ['- '+json.dumps(w,ensure_ascii=False) for w in f['witnesses']]
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--catalogs',type=Path,default=CATALOGS);p.add_argument('--profile',type=Path,default=ROOT/'profiles/gitea-lifecycle.json');a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh output directory required')
    report=analyze_archive(a.input,a.profile,a.catalogs);a.output.mkdir(parents=True)
    (a.output/'analysis.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (a.output/'report.md').write_text(markdown(report),encoding='utf-8');print('NATCHAN_V016 '+json.dumps(report['counts']))
if __name__=='__main__':main()
