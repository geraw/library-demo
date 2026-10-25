"""Reuse the legacy classifier; reconcile coverage only against its qualified raw witnesses.
No cached analysis is accepted as a new raw-input adapter.
"""
from copy import deepcopy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v014'))
import engine as legacy
from providers import equal

def source_key(source):
    return (source.get('sha256'),source.get('record'),tuple(source.get('members',[])),source.get('archive_sha256'))

def same_journal(a,b):
    return a.get('sha256')==b.get('sha256') and a.get('members',[])==b.get('members',[]) and a.get('archive_sha256')==b.get('archive_sha256')

def scalar(value):
    # None is an explicitly recorded null, not an absent key. Bool is not a reference ID.
    return value is None or type(value) in [str,int,float]

def raw_pair(summary, source, observations):
    """Require the existing control-qualified detector plus both original HTTP witnesses."""
    c=summary.get('create',{});u=summary.get('update',{})
    if not isinstance(c,dict) or not isinstance(u,dict) or type(summary.get('pair')) is not int:return None
    eligible=[]
    for update in observations:
        f=update.get('facts',{})
        if update.get('fact_basis')!='recomputed' or not same_journal(source,update['source']):continue
        if not (f.get('pair_qualified') is True and f.get('raw_pair_controls_verified') is True and f.get('raw_pair_id')==summary['pair']):continue
        field=f.get('raw_pair_field');request=update.get('request')
        if not isinstance(request,dict) or field not in request or update.get('method') not in ['PATCH','PUT']:continue
        if update.get('status')!=u.get('status') or update.get('status')!=f.get('raw_update_status'):continue
        if u.get('field') is not None and u['field']!=field:continue
        if 'sent' in u and not equal(u['sent'],request[field]):continue
        paired=[w['paired_create_source'] for w in update.get('witnesses',[]) if 'paired_create_source' in w]
        if len(paired)!=1:continue
        creates=[o for o in observations if source_key(o['source'])==source_key(paired[0])]
        if len(creates)!=1:continue
        create=creates[0];body=create.get('request')
        if not same_journal(create['source'],update['source']) or create['source']['record']>=update['source']['record']:continue
        if create.get('run_id')!=update.get('run_id') or create.get('product')!=update.get('product'):continue
        if create.get('method') not in ['POST','PUT'] or not isinstance(body,dict) or field not in body:continue
        if create.get('status')!=c.get('status') or create.get('status')!=f.get('raw_create_status'):continue
        if not equal(body[field],request[field]) or ('sent' in c and not equal(c['sent'],body[field])):continue
        eligible.append(dict(family='DIV-1',source=source,status='RAW_VERIFIED',pair=summary['pair'],field=field,
            response_classes_differ=create['status']//100!=update['status']//100,
            qualified_detector_difference=f.get('create_update_diverge'),
            witnesses=[create['source'],update['source']],controls_verified=True))
    return eligible[0] if len(eligible)==1 else None

def applicable_coverage(report):
    products={o.get('product') for o in report.get('observations',[])} | {r.get('product') for r in report.get('runs',[])}
    existing=report.get('rule_coverage',[]);kept=[];excluded=[]
    for rule in existing:
        # This is the only legacy rule-coverage row currently generated unconditionally.
        if rule.get('catalog_id')=='VIK-O09' and 'vikunja' not in products:
            excluded.append(dict(rule,applicability='NOT_APPLICABLE',reason='product_not_in_evidence'))
        else:kept.append(rule)
    report['rule_coverage']=kept
    audit=report.setdefault('coverage_audit',{})
    prior=audit.get('not_applicable_rules',[])
    audit['not_applicable_rules']=prior+[x for x in excluded if x not in prior]
    return report

def analyze(parts,catalogs=legacy.ROOT/'catalogs'):
    prepared=deepcopy(parts);resolved=[];all_originals=[];addition_gaps=[]
    for _,part in prepared:
        additions=part.get('evidence_additions',{})
        resolved.extend(additions.get('resolved_measurements',[]))
        addition_gaps.extend(additions.get('unknown_evidence',[]))
    for _,part in prepared:
        originals=part.get('original_oracles',[]);all_originals.extend(deepcopy(originals));remaining=[]
        for item in originals:
            row=item['payload'];category=row.get('category');source=item['source']
            accepted=type(row.get('status')) is int and 200<=row['status']<300
            if category=='reference-check' and accepted and row.get('readback_status')==200 and 'sent' in row and 'stored' in row and scalar(row['sent']) and scalar(row['stored']):
                contexts=[o for o in part.get('observations',[]) if same_journal(source,o['source'])]
                if not contexts:remaining.append(item);continue
                context=contexts[0]
                value=dict(id='scalar-reference',product=context['product'],product_version=context.get('product_version'),run_id=context['run_id'],tool=context.get('tool'),source=source,
                    facts=dict(measured_reference_difference=not equal(row['sent'],row['stored']),sent_value=row['sent'],observed_value=row['stored'],projection_shape='scalar',full_snapshots_verified=False),
                    fact_basis='recomputed',entity=str(row.get('entity') or row.get('type') or '').lower() or None,field=row.get('field'),evidence_tier='producer_id_projection')
                part['observations'].append(value)
                resolved.append(dict(family='REF-1',source=source,status='PRODUCER_MEASUREMENT_COMPARED',projection_shape='scalar',independent_raw_state_verified=False))
            else:remaining.append(item)
        part['original_oracles']=remaining
    from login_evidence import analyze_version_aliases
    report=analyze_version_aliases(legacy,prepared,catalogs)
    # Do not suppress missing evidence merely because another event has a divergence tag.
    resolution={}
    for item in all_originals:
        if item['payload'].get('category')=='divergence-check':
            checked=raw_pair(item['payload'],item['source'],report['observations'])
            if checked:resolution[source_key(item['source'])]=checked
    unresolved=[]
    for gap in report['unknown_evidence']:
        checked=resolution.get(source_key(gap['source'])) if gap.get('family')=='DIV-1' else None
        if checked:resolved.append(checked)
        else:unresolved.append(gap)
    unresolved.extend(addition_gaps)
    report['unknown_evidence']=unresolved
    report['evidence_summary']['unknown_evidence_records']=len(unresolved)
    report['coverage_audit']=dict(resolved_measurements=resolved,policy='Only evidence for this exact journal record resolves its coverage gap; raw classifications remain independent of producer verdict labels.')
    applicable_coverage(report)
    return report
