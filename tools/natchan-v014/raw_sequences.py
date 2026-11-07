"""Recompute state and paired outcomes from raw HTTP, never producer verdicts."""
import json
import re
from providers import equal


def parsed(value):
    if isinstance(value, str):
        try:return json.loads(value)
        except ValueError:return value
    return value


def project(value, path):
    if not path:return value
    if isinstance(value, list):return [project(x, path) for x in value]
    if not isinstance(value, dict):return None
    key, _, rest = path.partition('.')
    return project(value.get(key), rest)


def update_state(before, write, after):
    """Consecutive raw HTTP records, same actor/resource and increasing clock."""
    if [before.get('method'), write.get('method'), after.get('method')] != ['GET', 'PATCH', 'GET']:return None
    if before.get('status') != 200 or after.get('status') != 200 or not 500 <= write.get('status', 0) < 600:return None
    if len({x.get('path') for x in (before, write, after)}) != 1:return None
    if not before.get('session') or len({x.get('session') for x in (before, write, after)}) != 1:return None
    clocks = [x.get('t_rel_ms') for x in (before, write, after)]
    if not all(type(x) in (int, float) for x in clocks) or not clocks[0] < clocks[1] < clocks[2]:return None
    b, w, a = parsed(before.get('response')), parsed(write.get('input')), parsed(after.get('response'))
    if not all(isinstance(x, dict) for x in (b, w, a)):return None
    if b.get('id') is None or not equal(b['id'], a.get('id')):return None
    fields = {}
    projections = {'assignee': 'assignee.login', 'assignees': 'assignees.login', 'milestone': 'milestone.id'}
    for key, desired in w.items():
        if key in ('id', 'content_version', 'updated_at', 'created_at') or key not in b or key not in a:continue
        old, new = project(b, projections.get(key, key)), project(a, projections.get(key, key))
        if equal(old, desired):continue
        fields[key] = 'applied' if equal(new, desired) else 'kept' if equal(new, old) else 'other'
    states = set(fields.values())
    verdict = ('partial' if states == {'applied', 'kept'} else 'committed_despite_error' if states == {'applied'}
               else 'rolled_back' if states == {'kept'} else 'unknown')
    return dict(atomicity=verdict, raw_changed_field_outcomes=fields,
                raw_same_resource_sequence=True, background_concurrency_excluded=False)


def augment(values, rows, plan):
    # Only original research entries are physical HTTP observations. Sequence
    # summaries duplicate them and must not create extra requests or findings.
    raw = [(i, row) for i, row in enumerate(rows) if row.get('category') == 'research']
    positions = {index: pos for pos, (index, _) in enumerate(raw)}
    by_record = {o['source']['record']: o for o in values}
    steps = {}; ambiguous = set()
    for position, (index, row) in enumerate(raw):
        o = by_record.get(index)
        if o is None:continue
        if 0 < position < len(raw)-1:
            state = update_state(raw[position-1][1], row, raw[position+1][1])
            if state:
                o['facts'].update(state)
                o.setdefault('witnesses', []).append(dict(raw_state_records=[raw[position-1][0], index, raw[position+1][0]]))
        if o.get('entity') == 'pullrequest' and o.get('operation') == 'create' and o.get('status') == 500:
            request = parsed(row.get('input'));actor = row.get('session')
            # Actor login comes from an earlier successful /user GET in the same session.
            actors = [parsed(r.get('response')) for _, r in raw[:position] if r.get('session') == actor and r.get('method') == 'GET' and r.get('path') == '/user' and r.get('status') == 200]
            actor_ids = {(r.get('id'), r.get('login')) for r in actors if isinstance(r, dict)}
            match = re.search(r"poster of pr can't be reviewer \[user_id: (\d+)", o.get('server_message', ''))
            if isinstance(request, dict) and isinstance(request.get('reviewers'), list) and len(actor_ids) == 1 and match and o.get('correlated_log'):
                uid, login = next(iter(actor_ids))
                if str(uid) == match[1] and login in request['reviewers']:
                    o['facts']['self_reviewer_error_verified'] = True
                    o['facts']['creation_atomicity'] = 'not_evaluable_no_created_resource_lookup'
        logical = row.get('logical_id', '')
        if re.fullmatch(r'G014_STEP_\d+', logical):
            step = int(logical.rsplit('_', 1)[1])
            if step in steps:ambiguous.add(step)
            steps[step] = (index, row, o)
    if not plan:return
    specifications = plan.get('steps', [])
    pairs = {};controls = {}
    for i, spec in enumerate(specifications):
        if spec.get('role') != 'probe' or i not in steps or i in ambiguous:continue
        index, row, o = steps[i];request = parsed(row.get('input'));field = spec.get('field')
        if not isinstance(request, dict) or field not in request:continue
        if row.get('method') != spec.get('method') or o.get('entity') != spec.get('entity', '').lower():continue
        phase = spec.get('phase');detail = dict(status=row['status'], sent=request[field], observation=o,
                                                actor=row.get('session'), position=positions[index])
        # The actual readback must be the next physical exchange and have a
        # matching nonzero identity returned by this operation.
        readspec = specifications[i+1] if i+1 < len(specifications) else {}
        read = steps.get(i+1)
        if read and i+1 not in ambiguous and readspec.get('role') == 'readback' and readspec.get('pair') == spec.get('pair'):
            _, rr, _ = read;writebody = parsed(row.get('response'));readbody = parsed(rr.get('response'))
            if positions.get(read[0]) == positions[index]+1 and rr.get('status') == 200 and isinstance(writebody, dict) and isinstance(readbody, dict) and writebody.get('id') is not None and equal(writebody['id'], readbody.get('id')) and row.get('session') == rr.get('session'):
                detail['stored'] = project(readbody, readspec.get('projection', field))
        pairs.setdefault(spec.get('pair'), {})[phase] = detail
        if spec.get('mode') == 'own':controls[(spec.get('entity'), field, phase)] = ('stored' in detail and 200 <= row['status'] < 300 and equal(detail['sent'], detail['stored']))
        if field in ('ref', 'target_commitish') and 'stored' in detail and equal(detail['stored'], detail['sent']):
            repo = re.match(r'(/repos/[^/]+/[^/]+)/', row.get('path', ''))
            absent = [steps[j] for j in range(i) if j in steps and j not in ambiguous and specifications[j].get('role') == 'absence-control' and repo and steps[j][1].get('path') == repo[1]+'/branches/'+str(detail['sent']) and steps[j][1].get('session') == row.get('session') and steps[j][1].get('method') == 'GET' and steps[j][1].get('status') == 404]
            last = absent[-1] if absent else None
            changed_branch = last and any(r.get('method') in ('POST','PUT','PATCH','DELETE') and (r.get('path','').startswith(repo[1]+'/branches') or r.get('path') == repo[1]) for _, r in raw[positions[last[0]]+1:positions[index]])
            if last and not changed_branch:
                o['facts']['stored_absent_branch_reference'] = True
                o['facts']['business_violation_established'] = False
    for pair, phases in pairs.items():
        if 'create' not in phases or 'update' not in phases:continue
        c, u = phases['create'], phases['update'];o = u['observation']
        spec = next(s for s in specifications if s.get('pair') == pair and s.get('phase') == 'update' and s.get('role') == 'probe')
        if not c['actor'] or c['actor'] != u['actor'] or c['position'] >= u['position']:continue
        if not equal(c['sent'], u['sent']) or not all(controls.get((spec['entity'], spec['field'], p)) for p in ('create', 'update')):continue
        difference = c['status']//100 != u['status']//100
        stored_difference = 'stored' in c and 'stored' in u and not equal(c['stored'], u['stored'])
        o['facts'].update(pair_qualified=True, create_update_diverge=bool(difference or stored_difference),
                          raw_create_status=c['status'], raw_update_status=u['status'],
                          raw_pair_id=pair, raw_pair_field=spec['field'], raw_pair_controls_verified=True)
        o.setdefault('witnesses', []).append(dict(paired_create_source=c['observation']['source']))
