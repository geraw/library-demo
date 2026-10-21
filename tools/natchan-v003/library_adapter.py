"""Recompute Library observations through the preserved evaluator; never match stored labels."""
from pathlib import Path
import sys
from urllib.parse import urlsplit


def observations_from_analysis(document):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'natchan-v002'))
    from analyze import analyze_envelope
    fresh=analyze_envelope(document['evidence'])
    events={e['id']:e for e in fresh['evidence']['events']}
    runs={r['id']:r for r in fresh['evidence']['runs']}
    observations=[]
    for finding in fresh['findings']:
        run=runs[finding['run_id']]
        if run['product_gateway']!='library-issta-v006':continue
        event=events[finding['source_event_id']];raw=event['payload']
        violation=finding['evidence']['violation'];rule=violation['rule']
        state_witnesses=None
        facts={};entity=violation.get('entity');context=[events[i] for i in finding['context_event_ids']]
        if rule=='EXISTING_BOOK_READ':
            facts.update(known_existing_book=True,existing_read_404=raw['status']==404);entity='books'
        if rule=='VALID_LOAN_REJECTED':
            facts.update(legal_loan_rejected=True,active_for_user=violation['active_for_user'],prior_pair_loans=violation['prior_pair_loans']);entity='loans'
        missing=[]
        if rule=='STATE_MISMATCH' and raw['method']=='DELETE' and entity in ('holds','loans'):
            prior=[e['payload'] for e in context if e['source']['line']<event['source']['line'] and e['role']=='oracle' and urlsplit(e['payload'].get('path','')).path=='/'+entity and e['payload'].get('status')==200]
            next_tool=min((e['source']['line'] for e in context if e['source']['line']>event['source']['line'] and e['role']=='tool'),default=float('inf'))
            following=[e['payload'] for e in context if event['source']['line']<e['source']['line']<next_tool and e['role']=='oracle' and urlsplit(e['payload'].get('path','')).path=='/'+entity and e['payload'].get('status')==200]
            before=prior[-1]['response'] if prior else None
            actual=following[0]['response'] if following else None
            # Use immutable recorded readbacks. Some legacy emitted expected arrays
            # share Ledger state and can include appends from later operations.
            if isinstance(before,list) and isinstance(actual,list):
                actual_ids={v.get('id') for v in actual}
                if entity=='holds':
                    target_id=int(urlsplit(raw['path']).path.rsplit('/',1)[-1])
                    target=next((v for v in before if v.get('id')==target_id),None)
                    missing=[v for v in before if v.get('id')!=target_id and v.get('id') not in actual_ids]
                    facts['target_existed_before']=target is not None
                    facts['same_owner_non_target_removed']=bool(target and missing and all(v.get('userId')==target.get('userId') for v in missing))
                else:
                    parts=urlsplit(raw['path']).path.split('/')
                    owner,book=int(parts[2]),int(parts[3])
                    missing=[v for v in before if (v.get('userId'),v.get('bookId'))!=(owner,book) and v.get('id') not in actual_ids]
                    facts['same_owner_non_target_removed']=bool(missing) and all(v.get('userId')==owner for v in missing)
                facts['non_target_removed']=bool(missing)
                facts['resource']=entity
                state_witnesses=dict(before=before,after=actual,non_targets_removed=missing)
        consequences=[]
        missing_ids={v.get('id') for v in missing}
        for later in context:
            p=later['payload']
            if later['source']['line']<=event['source']['line'] or later['role']!='tool':continue
            if entity=='holds' and p.get('method')=='DELETE' and p.get('status')==404:
                try:identifier=int(urlsplit(p.get('path','')).path.rsplit('/',1)[-1])
                except ValueError:continue
                if identifier in missing_ids:consequences.append(later['id'])
        facts['later_delete_404']=bool(consequences)
        observations.append(dict(id='library-'+finding['id'],product='library',product_version='issta-v006',
            run_id=run['id'],tool=run['tool'],scope=dict(case=finding['case'],ordinal=finding['case_ordinal']),
            state_witnesses=state_witnesses,entity=entity,operation=raw['method'],status=raw['status'],source=dict(archive=fresh['evidence']['source'],member=next(a['locator'] for a in fresh['evidence']['artifacts'] if a['id']==event['source']['artifact_id']),**event['source']),
            primary_event=event['id'],consequence_events=consequences,facts=facts,fact_basis='recomputed'))
    return observations
