"""Bounded toolkit stories reader; producer checks are measurements, not raw proof."""
from collections import Counter, defaultdict
import hashlib
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from toolkit_formats import text, UnsupportedEvidence, InvalidEvidence

ROOT = Path(__file__).resolve().parent
STATUSES = {'COMPLETED', 'SETUP_FAILED', 'SETUP_OR_RUN_STOPPED', 'NOT_STARTED', 'NOT_APPLICABLE'}
ALIASES = json.loads((ROOT/'story_profiles.json').read_text())['product_aliases']


def parsed(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def number(value):
    if type(value) is bool or value is None:
        raise ValueError('Not a numeric measurement')
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValueError('Not a numeric measurement') from e
    if not n.is_finite():
        raise ValueError('Nonfinite numeric measurement')
    return n


def successful(row):
    return type(row.get('status')) is int and 200 <= row['status'] < 300


def identity(row):
    value = row.get('response')
    return value.get('id') if isinstance(value, dict) else None


def path(row):
    return urlsplit(row.get('path') or '').path.rstrip('/')


def group_id(row):
    m = re.fullmatch(r'(\S+)_(\d+) (.+)', row.get('logical_id') or '')
    return (m[1], int(m[2]), m[3]) if m else (None, None, None)


def annotate(observation, **facts):
    observation['facts'].update(facts)


def add_witnesses(observation, *rows):
    known = {json.dumps(w, sort_keys=True) for w in observation['witnesses']}
    for row in rows:
        source = row['source']
        key = json.dumps(source, sort_keys=True)
        if key not in known:
            observation['witnesses'].append(source)
            known.add(key)


def same_actor(a, b):
    return a.get('session') is not None and a.get('session') == b.get('session')


def raw_references(rows, observations, gap):
    """Delete -> observed 404 -> retained scalar foreign key, qualified by preimage."""
    by_index = {o['_position']: o for o in observations}
    for offset, deletion in enumerate(rows):
        if deletion.get('method') != 'DELETE' or not successful(deletion):
            continue
        sid = deletion['_story']
        if sid is None:
            continue
        target = path(deletion)
        before = [r for r in rows[:offset] if r['_story'] == sid and r.get('method') == 'GET'
                  and path(r) == target and successful(r) and same_actor(r, deletion)
                  and identity(r) is not None]
        if not before:
            continue
        pretarget = before[-1]
        tid = identity(pretarget)
        if target.rsplit('/', 1)[-1] != str(tid):
            # Routes such as recipe slugs may differ from body IDs; an exact successful
            # pre-read and DELETE path still bind that observed ID to this target.
            if not isinstance(pretarget.get('response'), dict) or not any(
                    str(v) == target.rsplit('/', 1)[-1] for v in pretarget['response'].values()
                    if type(v) in (str, int)):
                continue
        subsequent = [r for r in rows[offset+1:] if r['_story'] == sid]
        absence = next((r for r in subsequent if r.get('method') == 'GET' and path(r) == target
                        and r.get('status') == 404 and same_actor(r, deletion)), None)
        if absence is None:
            continue
        for read in subsequent:
            if read['_position'] <= absence['_position'] or read.get('method') != 'GET' or not successful(read):
                continue
            if not same_actor(read, deletion) or not isinstance(read.get('response'), dict):
                continue
            if any(r.get('method') != 'GET' and successful(r) and path(r) == target
                   and deletion['_position'] < r['_position'] < read['_position'] for r in subsequent):
                continue
            predecessors = [r for r in rows[:offset] if r['_story'] == sid and r.get('method') == 'GET'
                            and path(r) == path(read) and successful(r) and same_actor(r, read)
                            and isinstance(r.get('response'), dict)]
            if not predecessors:
                continue
            pre = predecessors[-1]
            fields = [f for f, v in read['response'].items() if f != 'id'
                      and re.search(r'(?:Id|_id)$', f) and type(v) in (str, int)
                      and type(v) is type(tid) and v == tid and pre['response'].get(f) == tid]
            for field in fields:
                obs = by_index[read['_position']]
                writes = [r for r in subsequent if deletion['_position'] < r['_position'] < read['_position']
                          and path(r) == path(read) and r.get('method') in ('PUT', 'PATCH')
                          and successful(r) and same_actor(r, read) and isinstance(r.get('input'), dict)
                          and r['input'].get(field) == tid]
                annotate(obs, story_dangling_reference=True, raw_story_state_verified=True,
                         reference_field=field, deleted_target_id=tid,
                         dangling_after_stale_write=bool(writes), story_dangling_delete_only=not writes)
                obs.update(field=field, evidence_tier='recorded_http_sequence')
                add_witnesses(obs, pretarget, pre, deletion, absence, *(writes[-1:] or []))
                obs.setdefault('story_checks_recomputed', []).append({
                    'family': 'STALE' if writes else 'DELREF', 'field': field,
                    'target_path': target, 'referrer_path': path(read), 'target_status': 404})
        # A rejected stale write can itself be a server error. It is not proof that
        # the missing reference was retained; keep it separate from the dangling row.
        for write in subsequent:
            if write.get('method') not in ('PUT', 'PATCH') or not (500 <= (write.get('status') or 0) < 600):
                continue
            if not same_actor(write, deletion) or not isinstance(write.get('input'), dict):
                continue
            fields = [f for f, v in write['input'].items() if re.search(r'(?:Id|_id)$', f)
                      and type(v) is type(tid) and v == tid]
            previous = [r for r in rows[:offset] if r['_story'] == sid and r.get('method') == 'GET'
                        and path(r) == path(write) and successful(r) and same_actor(r, write)]
            if fields and previous:
                obs = by_index[write['_position']]
                annotate(obs, story_missing_reference_write_5xx=True, raw_story_state_verified=True,
                         reference_field=fields[0], deleted_target_id=tid)
                add_witnesses(obs, pretarget, previous[-1], deletion, absence)


def raw_absent_errors(rows, observations):
    """A later GET 404 after a cascade witnesses absence; don't infer it from names."""
    for row, obs in zip(rows, observations):
        if not (500 <= (row.get('status') or 0) < 600) or row.get('method') not in ('PUT', 'PATCH', 'DELETE'):
            continue
        absence = [r for r in rows if r['_story'] == row['_story'] and same_actor(r, row)
                   and path(r) == path(row) and r.get('method') == 'GET' and r.get('status') == 404]
        before = [r for r in rows if r['_story'] == row['_story'] and same_actor(r, row)
                  and r['_position'] < row['_position'] and r.get('method') == 'GET'
                  and path(r) == path(row) and successful(r)]
        if not absence or not before:
            continue
        witness = min(absence, key=lambda r: abs(r['_position']-row['_position']))
        lo, hi = sorted([row['_position'], witness['_position']])
        if any(lo < r['_position'] < hi and r.get('method') != 'GET' and successful(r)
               and path(r) == path(row) for r in rows):
            continue
        annotate(obs, story_write_absent_resource_5xx=True, raw_story_state_verified=True)
        add_witnesses(obs, before[-1], witness)


def vector(row, fields):
    body = row.get('response')
    if not successful(row) or not isinstance(body, dict) or any(f not in body for f in fields):
        raise ValueError('Aggregate full response fields unavailable')
    return {f: Decimal(0) if body[f] is None else number(body[f]) for f in fields}


def close_vectors(a, b, n):
    return all(abs(a[f]-b[f]) <= Decimal('0.011')*(n+1)+Decimal('0.0001')*abs(b[f]) for f in a)


def raw_aggregates(rows, observations, gap):
    """Interpret generic AGG role labels, then verify identity, move and arithmetic in HTTP."""
    index = {o['_position']: o for o in observations}
    grouped = defaultdict(list)
    for r in rows:
        if r['_story'] and r['_story'].startswith('AGG_'):
            grouped[r['_story']].append(r)
    for sid, group in grouped.items():
        get = lambda label: [r for r in group if r['_label'] == label and r.get('method') == 'GET']
        p1s, p2s = get('read aggregate P1 baseline'), get('read aggregate P2 baseline')
        views = {v: get('read view '+v) for v in ('C1', 'C2')}
        moves = [r for r in group if r['_label'] == 'move C2 to P2' and r.get('method') in ('PATCH', 'PUT')]
        old = get('read aggregate P1 after moving C2 away')
        new = get('read aggregate P2 after moving C2 in')
        if not all(len(x) == 1 for x in (p1s, p2s, moves, old, new)) or not all(views.values()):
            continue
        p1, p2, move, oldread, newread = [x[0] for x in (p1s, p2s, moves, old, new)]
        if path(oldread)!=path(p1) or path(newread)!=path(p2) or path(p1)==path(p2):
            gap('STORY_AGGREGATE_RESOURCE_BINDING_FAILED',story=sid)
            continue
        c1, c2 = views['C1'][-1], views['C2'][-1]
        if not (p1['_position'] < c1['_position'] < move['_position'] < oldread['_position'] < newread['_position']
                and c2['_position'] < move['_position'] and p2['_position'] < move['_position']):
            continue
        if any(not same_actor(p1, r) for r in (p2, move, oldread, newread, c1, c2)):
            continue
        if not successful(move) or not isinstance(move.get('input'), dict) or not isinstance(move.get('response'), dict):
            continue
        child = identity(move)
        if child is None or path(move).rsplit('/', 1)[-1] != str(child):
            continue
        if not (path(c2).startswith(path(move)+'/') and path(c1) != path(c2)):
            continue
        p1creates = [r for r in group if r.get('method') == 'POST' and successful(r) and identity(r) is not None
                     and path(p1).startswith(path(r)+'/'+str(identity(r))+'/')]
        p2creates = [r for r in group if r.get('method') == 'POST' and successful(r) and identity(r) is not None
                     and path(p2).startswith(path(r)+'/'+str(identity(r))+'/')]
        ccreates = [r for r in group if r.get('method') == 'POST' and successful(r) and identity(r) == child]
        if not (len(p1creates) == len(p2creates) == len(ccreates) == 1):
            continue
        p1id, p2id = identity(p1creates[0]), identity(p2creates[0])
        fields_ref = [f for f, v in move['input'].items() if v == p2id and move['response'].get(f) == p2id
                      and isinstance(ccreates[0].get('input'), dict) and ccreates[0]['input'].get(f) == p1id]
        if p1id == p2id or len(fields_ref) != 1:
            continue
        if any(move['_position'] < r['_position'] < newread['_position'] and r.get('method') != 'GET' for r in group):
            continue
        first = get('read aggregate P1 after the first child')
        second = get('read aggregate P1 after the second child')
        if len(first) != 1 or len(second) != 1:
            continue
        if any(path(r)!=path(p1) or not same_actor(p1,r) for r in (first[0],second[0])):
            continue
        if not p1['_position']<first[0]['_position']<second[0]['_position']<move['_position']:
            continue
        fields = [f for f, v in (p1.get('response') or {}).items() if v is None or type(v) in (int, float)]
        if not fields:
            continue
        try:
            base, base2, va, vb = [vector(r, fields) for r in (p1, p2, c1, c2)]
            first_c1 = vector(views['C1'][0], fields)
            expected_first = {f: base[f]+first_c1[f] for f in fields}
            expected_second = {f: base[f]+first_c1[f]+vb[f] for f in fields}
            if not any(first_c1.values()) or not close_vectors(vector(first[0], fields), expected_first, 1):
                gap('STORY_AGGREGATION_HYPOTHESIS_NOT_QUALIFIED', story=sid)
                continue
            if not close_vectors(vector(second[0], fields), expected_second, 2):
                gap('STORY_AGGREGATION_CONTROL_FAILED', story=sid)
                continue
            exp, exp2 = {f: base[f]+va[f] for f in fields}, {f: base2[f]+vb[f] for f in fields}
            actual, actual2 = vector(oldread, fields), vector(newread, fields)
        except ValueError:
            gap('STORY_AGGREGATE_VALUES_NOT_EVALUABLE', story=sid)
            continue
        if not close_vectors(actual, exp, 1):
            obs = index[oldread['_position']]
            annotate(obs, story_aggregate_after_move_mismatch=True, raw_story_state_verified=True,
                     new_parent_aggregate_correct=close_vectors(actual2, exp2, 1),
                     aggregate_expected={k: float(v) for k, v in exp.items()},
                     aggregate_observed={k: float(v) for k, v in actual.items()})
            add_witnesses(obs, p1, p2, c1, c2, first[0], second[0], move, newread,
                          p1creates[0], p2creates[0], ccreates[0])


def native_measurements(checks, context, gap):
    values = []
    for c, source in checks:
        facts = {}
        name = c.get('check') or ''
        observed = c.get('observed')
        detail = c.get('detail') or {}
        try:
            if name.startswith(('add ', 'remove ')) and all(k in detail for k in ('previous', 'source_sum', 'scale')):
                computed = number(detail['previous']) + (1 if name.startswith('add ') else -1)*number(detail['source_sum'])*number(detail['scale'])
                if computed != number(c.get('expected')):
                    gap('STORY_PRODUCER_EXPECTATION_CONTRADICTED', source=source)
                    continue
                facts.update(story_contribution_mismatch_measured=abs(computed-number(observed)) > Decimal('1e-9'),
                             measured_expected=float(computed), measured_observed=observed)
            elif ' INTRA-REF ' in name and isinstance(detail.get('A'), list) and isinstance(detail.get('B'), list):
                bad = [v for v in detail['B'] if v not in detail['A']]
                if c.get('expected') != [] or bad != observed:
                    gap('STORY_PRODUCER_PROJECTION_CONTRADICTED', source=source)
                    continue
                facts.update(story_internal_reference_mismatch_measured=bool(bad), dangling_projection=bad)
            else:
                continue
        except (ValueError, TypeError, InvalidOperation):
            gap('STORY_NATIVE_MEASUREMENT_NOT_EVALUABLE', source=source)
            continue
        values.append(dict(context, id='native-measurement', source=source, facts=facts,
                           fact_basis='recomputed', evidence_tier='producer_story_measurements',
                           witnesses=[], producer_check_pass=c.get('pass'), story_id=c.get('story')))
    return values


def read(reader, files, chain, env, result_member='result_stories.json'):
    try:result = json.loads(text(files[result_member]))
    except (ValueError, UnicodeError) as e:raise InvalidEvidence('Invalid stories result JSON') from e
    if not isinstance(result,dict):raise InvalidEvidence('Stories result must be an object')
    if result.get('version') != 'stories-dev':
        raise UnsupportedEvidence('Unsupported stories version: '+str(result.get('version')))
    label = result.get('sut')
    if not isinstance(label, str) or not label:
        raise InvalidEvidence('Stories result.sut must identify the observed target label')
    runner = result.get('runner')
    if runner not in ('provengo', 'harness'):
        raise UnsupportedEvidence('Unsupported stories runner: '+str(runner))
    product = ALIASES.get(label, label)
    version = result.get('sut_version') or env.get('sut_version')
    if env.get('sut') and env['sut'] != label:
        raise InvalidEvidence('Stories ENV/result product conflict')
    if result.get('sut_version') and env.get('sut_version') and result['sut_version'] != env['sut_version']:
        raise InvalidEvidence('Stories ENV/result version conflict')
    if not version:
        reader.gap('STORIES_SUT_VERSION_NOT_RECORDED', product=product,
                   affects='No version-specific known bug confirmation; expected configuration is not observed version')
    stories = result.get('stories')
    if not isinstance(stories, list) or any(not isinstance(s, dict) or not isinstance(s.get('story'), str) for s in stories):
        raise InvalidEvidence('Stories result requires story descriptors')
    ids = [s['story'] for s in stories]
    if len(ids) != len(set(ids)):
        raise InvalidEvidence('Duplicate story IDs')
    for s in stories:
        if s.get('status') not in STATUSES:
            raise UnsupportedEvidence('Unsupported story status: '+str(s.get('status')))
    root = result_member[:-len('result_stories.json')]
    source = lambda name, record=None: reader.source(files, root+name, chain, record)
    run_id = '/'.join([reader.path.stem, *chain, root.rstrip('/')]).rstrip('/')
    context = dict(product=product, product_version=version, run_id=run_id,
                   tool='provengo' if runner == 'provengo' else 'story-harness', seed=result.get('seed'))
    reader.inputs.append(source('result_stories.json'))
    logs=[n for n in files if n.startswith(root) and n.endswith('sut.log')]
    for name in logs:reader.inputs.append(reader.source(files,name,chain))
    if not logs:reader.gap('STORIES_SERVER_LOG_NOT_CORRELATED',run=run_id,retained_log_members=logs,
               affects='No independent server-log cause or request-to-log attribution is claimed')
    native = []; native_logs = []
    for name in sorted(files):
        if not name.startswith(root) or not name.endswith('native.log'):
            continue
        raw = files[name]; native_logs.append(name);reader.inputs.append(reader.source(files, name, chain))
        for i, line in enumerate(text(raw).splitlines()):
            m = re.search(r'\bSTORY_CHECK (\{.*\})\s*$', line)
            if m:
                try:
                    c = json.loads(m[1])
                    if c.get('story') not in ids:
                        raise ValueError('Native check story not declared')
                except (ValueError, AttributeError):
                    reader.gap('STORY_NATIVE_CHECK_INVALID', source=reader.source(files, name, chain, i))
                    continue
                native.append((c, dict(reader.source(files, name, chain, i), line_1based=i+1)))
    if not native_logs:
        reader.gap('STORIES_NATIVE_LOGS_MISSING', run=run_id)
    for name in native_logs:
        content=text(files[name])
        if 'STORY_DONE' not in content or (runner=='provengo' and 'Test Result: SUCCESS' not in content):
            reader.gap('STORIES_NATIVE_COMPLETION_NOT_VERIFIED',source=reader.source(files,name,chain))
    for s in stories:
        if s.get('status') != 'COMPLETED' or s.get('exit') != 0:
            reader.gap('STORY_NOT_COMPLETED', story=s['story'], status=s.get('status'), exit=s.get('exit'))
    if runner == 'harness':
        reader.gap('STORIES_HARNESS_NOT_NATIVE_PROVENGO', run=run_id)
    manifests=[root+n for n in ('manifest_v1.json','manifest_stories.json','input_hashes.json') if root+n in files]
    if not manifests:
        reader.gap('STORIES_MANIFEST_MISSING', run=run_id)
    for name in manifests:
        try:hashes=json.loads(text(files[name]))
        except ValueError as e:raise InvalidEvidence('Invalid stories manifest JSON') from e
        if not isinstance(hashes,dict) or not hashes:
            raise InvalidEvidence('Stories hash manifest must be a nonempty path-to-SHA256 object')
        for member,h in hashes.items():
            member=member.replace('\\','/')
            if not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h):
                raise UnsupportedEvidence('Unsupported stories hash manifest format')
            if root+member not in files or hashlib.sha256(files[root+member]).hexdigest()!=h:
                raise InvalidEvidence('Stories manifest hash mismatch: '+member)
        reader.inputs.append(reader.source(files,name,chain))
    rows = []; values = []
    journal = root+'gateway-journal.jsonl'
    if journal in files:
        seen = set()
        for i, line in enumerate(text(files[journal]).splitlines()):
            if not line.strip():
                continue
            try:row = json.loads(line)
            except ValueError as e:raise InvalidEvidence('Invalid stories journal JSON') from e
            if not isinstance(row,dict):raise InvalidEvidence('Stories journal record must be an object')
            if row.get('category') != 'research':
                reader.gap('STORIES_JOURNAL_CATEGORY_NOT_EVALUATED', category=row.get('category'))
                continue
            if type(row.get('status')) is not int or not 100 <= row['status'] <= 599:
                raise InvalidEvidence('Invalid stories HTTP status')
            if 'index' in row:
                if type(row['index']) is not int or row['index'] in seen:
                    raise InvalidEvidence('Duplicate/invalid stories HTTP index')
                seen.add(row['index'])
            sid, step, desc = group_id(row)
            row.update(_story=sid, _step=step, _label=desc, _position=i,
                       input=parsed(row.get('input')), response=parsed(row.get('response')),
                       source=dict(source('gateway-journal.jsonl', i), line_1based=i+1))
            obs = dict(context, id=run_id+':'+str(i), source=row['source'],
                       method=row.get('method'), path=row.get('path'), status=row['status'],
                       request=row.get('input'), response=row.get('response'), entity=None,
                       operation=row.get('action'), facts={}, fact_basis='recomputed',
                       evidence_tier='recorded_http_sequence', witnesses=[], _position=i, story_id=sid)
            rows.append(row);values.append(obs)
        if type(result.get('requests')) is not int or result['requests'] != len(rows):
            raise InvalidEvidence('Stories raw/result request count mismatch')
        groups = defaultdict(list)
        for r in rows:
            if r['_story'] is not None:
                groups[r['_story']].append(r)
        usable = []
        for sid, group in groups.items():
            steps = [r['_step'] for r in group]
            if len(steps) != len(set(steps)) or steps != sorted(steps):
                reader.gap('STORY_RETRY_OR_STEP_ASSOCIATION_AMBIGUOUS', story=sid)
            else:
                usable.extend(group)
            preimages=[r for r in group if r.get('method')=='POST' and successful(r) and identity(r) is not None]
            first_delete=next((r['_position'] for r in group if r.get('method')=='DELETE'),-1)
            if sid.startswith('DELREF_'):
                preimages += [r for r in group if r['_position']<first_delete and r.get('method')=='GET'
                              and successful(r) and identity(r) is not None]
            seen_preimages=defaultdict(list)
            for r in preimages:seen_preimages[(path(r),str(identity(r)))].append(r['_label'])
            if any(len(labels)>1 for labels in seen_preimages.values()):
                reader.gap('STORY_REFERRER_FIXTURES_SHARE_IDENTITY',story=sid,
                           affects='Repeated checks do not establish distinct referrer resources')
        usable.sort(key=lambda r: r['_position'])
        usable_obs = [o for o in values if any(r['_position'] == o['_position'] for r in usable)]
        from story_semantic_rules import load_profile
        from shared_semantics import evaluate
        spec=load_profile(reader,files,chain,root,product,result)
        audit=evaluate(rows,values,spec,reader.gap)
        if not hasattr(reader,'semantic_audits'):reader.semantic_audits=[]
        reader.semantic_audits.append(dict(run_id=run_id,tool=context['tool'],product=product,**audit))
        reader.inputs.append(source('gateway-journal.jsonl'))
        if 'http_5xx' in result and (not isinstance(result['http_5xx'],list) or len(result['http_5xx']) != sum(r['status'] >= 500 for r in rows)):
            raise InvalidEvidence('Stories 5xx summary count mismatch')
    else:
        reader.gap('STORIES_HTTP_JOURNAL_MISSING', run=run_id,
                   reported_requests=result.get('requests'), affects='Only retained producer measurements can be compared')
    if rows and logs:
        from log_correlation import correlate
        config=(spec or {}).get('log_correlation',{}) if 'spec' in locals() else {}
        audit_logs=correlate(rows,values,[(text(files[n]),reader.source(files,n,chain)) for n in logs],config,reader.gap)
        if not hasattr(reader,'log_audits'):reader.log_audits=[]
        reader.log_audits.append(dict(run_id=run_id,**audit_logs))
    measured = native_measurements(native, context, reader.gap)
    if measured:
        reader.gap('STORIES_MEASUREMENTS_NOT_FULL_HTTP_PROOF', run=run_id,
                   affects='Native retained projections/arithmetic are not independently read HTTP bodies')
    values.extend(measured)
    for o in values:
        o.pop('_position', None)
    reader.gap('STORIES_SEMANTIC_SCOPE_LIMITED', run=run_id,
               supported_raw_families=['DELREF', 'STALE', 'AGG', 'PROJ-NEST/MOVE', 'OP-ENUM', 'CONTRIB', 'COPY/INTRA-REF'],
               retained_measurement_families=['CONTRIB', 'INTRA-REF'],
               producer_fail_flags_are_not_verification=True)
    audit = dict(run_id=run_id, format='stories-dev', target_label=label, canonical_product=product,
                 product_version=version, runner=runner, reported_requests=result.get('requests'),
                 reported_contract_sha256=result.get('contract_sha256'), reported_jar_sha256=result.get('jar_sha256'),
                 reported_families=result.get('families'),
                 retained_research_requests=len(rows) if journal in files else None,
                 retained_research_5xx=sum(r['status'] >= 500 for r in rows) if journal in files else None,
                 native_check_records=len(native), native_log_members=native_logs,
                 producer_story_summaries=stories, measured_observations=len(measured),
                 raw_http_semantic_occurrences=sum(bool(o.get('facts', {}).get('raw_story_state_verified')) for o in values))
    if not hasattr(reader, 'stories_audits'):
        reader.stories_audits = []
    reader.stories_audits.append(audit)
    summary = dict(id=run_id, product=product, version=version, tool=context['tool'], seed=context['seed'],
                   http_records=len(rows) if journal in files else None,
                   http_5xx=audit['retained_research_5xx'], evidence_format='stories-dev',
                   category_counts=dict(Counter(json.loads(l).get('category') for l in text(files[journal]).splitlines() if l.strip())) if journal in files else {},
                   native_status='PRODUCER_REPORTED_COMPLETED' if all(s['status'] == 'COMPLETED' for s in stories) else 'PARTIAL',
                   source=source('result_stories.json'))
    reader.summaries.append(summary)
    reader.parts.append((run_id, dict(observations=values, runs=[summary], original_oracles=[])))


def add_candidate_links(report):
    """Version-free behavior signatures are candidates, never exact known-bug credit."""
    profiles = json.loads((ROOT/'story_profiles.json').read_text())
    candidates = []
    for o in report.get('observations', []):
        for rule in profiles['known_bug_candidates']:
            if o['product'] != rule['product'] or not all(o.get('facts', {}).get(f) is True for f in rule['facts']):
                continue
            if any(o.get('facts',{}).get(k)!=v for k,v in rule.get('fact_equals',{}).items()):continue
            if rule.get('path_regex') and not re.fullmatch(rule['path_regex'], o.get('path') or ''):
                continue
            candidates.append(dict(observation_id=o['id'], candidate_id=rule['id'],
                status='behavior_signature_candidate', source=o['source'], evidence_tier=o['evidence_tier'],
                observed_version=o.get('product_version'), version_confirmed=False,
                root_cause_identity_proven=False, needs_human=True))
    report['story_known_bug_candidates'] = candidates
    return report
