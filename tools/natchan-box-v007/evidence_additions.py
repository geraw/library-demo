"""Offline verification of opt-in toolkit evidence formats. No SUT I/O.

Journal positions and producer indexes are deliberately different concepts.
Readback projections are compared measurements, never advertised as full HTTP bodies.
"""
import json
import re


def parsed(value):
    if isinstance(value, str):
        try: return json.loads(value)
        except (ValueError, TypeError): pass
    return value


def exact(a, b):
    """Typed JSON equality for bindings; bool must not impersonate an integer."""
    if type(a) is not type(b):
        return type(a) in (int, float) and type(b) in (int, float) and a == b
    if isinstance(a, dict): return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list): return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


class Missing(ValueError): pass
class Conflict(ValueError):
    def __init__(self, message, **details):
        super().__init__(message); self.details=details


def require(test, reason, conflict=False):
    if not test: raise (Conflict if conflict else Missing)(reason)


def route(template, path):
    if not isinstance(template, str) or not isinstance(path, str): return None
    names = re.findall(r'\{([^{}]+)\}', template)
    pattern = re.escape(template)
    for name in names: pattern = pattern.replace(re.escape('{'+name+'}'), '([^/?]+)', 1)
    match = re.fullmatch(pattern, path.split('?')[0])
    return dict(zip(names, match.groups())) if match else None


class Verifier:
    def __init__(self, rows, ir, context):
        self.rows, self.ir, self.context = rows, ir, context
        self.by_index = {}
        for pos, row in enumerate(rows):
            if type(row.get('index')) is int: self.by_index.setdefault(row['index'], []).append((pos, row))

    def source(self, pos): return dict(self.context['source'], record=pos)

    def at(self, index, category):
        require(type(index) is int, 'pointer_index_missing_or_invalid')
        found = self.by_index.get(index, [])
        require(len(found) == 1, 'pointer_index_missing_or_ambiguous')
        pos, row = found[0]
        require(row.get('category') == category, 'pointer_category_mismatch', True)
        return pos, row

    def observation(self, pos, row, facts, tier):
        return dict(id='evidence-addition-'+str(pos), product=self.context['product'],
            product_version=self.context.get('version'), run_id=self.context['id'], tool=self.context['tool'],
            source=self.source(pos), facts=facts, fact_basis='recomputed', evidence_tier=tier,
            entity=str(row.get('type', '')).lower() or None, operation=row.get('kind'), witnesses=[])

    def atomicity(self, pos, row):
        snap = row.get('snapshots')
        require(isinstance(snap, dict) and snap.get('format') == 'atom-snapshots/1', 'unsupported_atomicity_format')
        require(row.get('kind') == 'update', 'atomicity_kind_not_supported_by_snapshot_verifier')
        require(type(row.get('first_status')) is int and 500 <= row['first_status'] <= 599, 'failed_write_status_missing')
        require(row.get('method') in ('PATCH', 'PUT'), 'update_method_invalid')
        require(all(isinstance(row.get(k),str) and row[k] for k in ('logical_id','path')), 'write_binding_missing')
        candidates = [(i,r) for i,r in enumerate(self.rows) if r.get('category') == 'research'
            and all(r.get(k) == row.get(k) for k in ('logical_id','method','path'))]
        require(len(candidates) == 1, 'raw_write_missing_or_ambiguous')
        rp, raw = candidates[0]
        require(rp > pos, 'raw_write_not_after_atomicity_record')
        require(row.get('session') is not None and row.get('session') == raw.get('session'), 'raw_write_actor_unbound')
        require('input' in raw and 'request_body' in snap and exact(snap['request_body'],parsed(raw['input'])), 'raw_write_body_mismatch', True)
        require(raw.get('status') == row['first_status'], 'raw_write_status_mismatch', True)
        require('first_response_body' in snap and isinstance(snap['first_response_body'],str) and isinstance(raw.get('response'),str)
            and snap['first_response_body'] == raw['response'][:20000], 'first_response_mismatch', True)
        before, after, request = snap.get('before'), snap.get('after'), snap.get('request_body')
        require(isinstance(before,dict) and before.get('source') in ('last_2xx_representation','trap_read_before_write')
            and isinstance(before.get('body'),dict), 'before_snapshot_or_source_missing')
        require(isinstance(after,dict), 'after_snapshot_missing')
        require(after.get('method') == 'GET' and after.get('path') == row['path'].split('?')[0], 'after_resource_mismatch', True)
        require(type(after.get('status')) is int and after['status'] == 200 and isinstance(after.get('body'),dict), 'after_snapshot_not_readable_200_object')
        require(row.get('readback_status') == after['status'], 'readback_status_mismatch', True)
        require(isinstance(request,dict), 'request_body_not_object')
        image, back = before['body'], after['body']
        # Reproduce the published producer algorithm, including its skipped absent fields.
        fields = {k: ('applied' if back[k] == v else 'kept' if back[k] == image.get(k) else 'other')
                  for k,v in sorted(request.items()) if k in back and image.get(k) != v}
        collateral = sorted(k for k in back if k not in request and k in image and back[k] != image[k])
        states = set(fields.values())
        verdict = ('no_judged_field' if not fields else 'rolled_back' if states == {'kept'} else
                   'committed_despite_error' if states == {'applied'} else 'partial' if states == {'applied','kept'} else 'other')
        computed = dict(fields=fields, collateral_changed=collateral, verdict=verdict)
        disagreements = [k for k,v in computed.items() if k not in row or not exact(row[k],v)]
        if disagreements:
            raise Conflict('atomicity_measurement_mismatch:'+','.join(disagreements), computed=computed, reported={k:row.get(k) for k in computed})
        audit = dict(family='ATOM-1-2', source=self.source(pos), status='RAW_VERIFIED', computed=computed,
            witnesses=[self.source(rp)], before_source=before['source'],
            scope='Recorded snapshots and request; attribution excludes neither other writers nor stale preimages.',
            immediate_preimage_asserted=before['source']=='trap_read_before_write',
            before_request_identity_independently_bound=False, background_concurrency_excluded=False,
            skipped_absent_after_fields=sorted(k for k in request if k not in back))
        measured = 'unchanged' if verdict == 'rolled_back' else 'applied' if verdict == 'committed_despite_error' else verdict
        facts = dict(atomicity=verdict, measured_field_outcome=measured, measured_fields=fields,
            full_snapshots_verified=True, snapshot_fields=fields, collateral_changed=collateral,
            before_source=before['source'], background_concurrency_excluded=False)
        obs = self.observation(pos,row,facts,'recorded_atomicity_snapshots')
        obs['witnesses'] = [dict(failed_write_source=self.source(rp))]
        return audit, obs

    def write(self, summary, pos):
        write = summary.get('write')
        require(isinstance(write,dict), 'write_pointer_missing')
        rp, raw = self.at(write.get('research_index'),'research')
        require(rp < pos, 'write_not_before_divergence_summary')
        require(all(k in write and k in raw and exact(write[k],raw[k]) for k in ('method','path','input','status','response')), 'write_copy_differs_from_raw', True)
        require(isinstance(summary.get('logical_id'),str) and summary['logical_id'] == raw.get('logical_id'), 'write_logical_id_mismatch', True)
        require(type(raw.get('status')) is int and 100 <= raw['status'] <= 599, 'raw_write_status_invalid')
        require(summary.get('status') == raw['status'], 'summary_status_mismatch', True)
        require(isinstance(raw.get('input'),dict), 'write_input_not_object')
        return rp, raw

    def specification(self, create, update):
        matches = [];rejections=[]
        for entity in self.ir.get('entities',[]):
            if create.get('method','').lower()!=entity.get('create_method') or update.get('method','').lower()!=entity.get('update_method'): continue
            cp, up = route(entity.get('path'),create.get('path')), route(entity.get('detail'),update.get('path'))
            if cp is None or up is None: continue
            same_parent=all(cp[k]==up[k] for k in cp.keys() & up.keys())
            action = create.get('action')
            require((action,update.get('action')) in [('edge_create','edge_update'),('ref_create','ref_update')], 'write_actions_not_comparable')
            if action == 'edge_create':
                probes = self.ir.get('traps',{}).get('edge',{}).get('probes',[])
                probes = [p for p in probes if p.get('entity')==entity.get('name') and p.get('update') is True and 'value' in p]
            else:
                probes = self.ir.get('traps',{}).get('refs',{}).get('refs',[])
                probes = [p for p in probes if p.get('entity')==entity.get('name') and 'update' in p.get('paths',[])]
            for probe in probes:
                field = probe.get('field');c,u=create['input'],update['input']
                if field not in c or field not in u: continue
                if not exact(c[field],u[field]):
                    rejections.append('tested_field_values_differ');continue
                if not same_parent:
                    rejections.append('pair_parent_context_differs');continue
                if action == 'edge_create' and not exact(c[field],probe['value']): continue
                matches.append((entity['name'],field))
        unique = sorted(set(matches))
        require(len(unique)==1, rejections[0] if not unique and rejections else 'tested_field_not_unique_in_contract_traps')
        return unique[0]

    def readback(self, side, raw, summary_pos, field, entity):
        ptr = side.get('readback')
        require(isinstance(ptr,dict) and ptr.get('category') in ('roundtrip-check','reference-check'), 'readback_pointer_missing')
        p,r = self.at(ptr.get('record_index'),ptr['category'])
        raw_pos,_ = self.at(raw.get('index'),'research')
        require(raw_pos < p < summary_pos, 'readback_order_invalid')
        require(all(r.get(k)==raw.get(k) for k in ('logical_id','action','path','session')), 'readback_write_binding_mismatch', True)
        require(r.get('type') == entity, 'readback_entity_mismatch', True)
        require(r.get('readback_status') == 200, 'readback_not_200')
        if ptr['category']=='roundtrip-check':
            require(raw.get('action') in ('edge_create','edge_update'), 'readback_category_action_mismatch', True)
            require(field in r.get('fields',[]), 'tested_field_not_in_readback')
            mismatches=r.get('mismatches')
            require(isinstance(mismatches,dict), 'readback_measurements_missing')
            if field not in mismatches: return dict(outcome='equal_to_sent',value=raw['input'][field]),p
            m=mismatches[field]
            require(isinstance(m,dict) and 'sent' in m and exact(m['sent'],raw['input'][field]), 'readback_sent_value_mismatch', True)
            require(m.get('class') in ('changed','dropped'), 'readback_change_class_invalid')
            require(m['class']=='dropped' or 'stored' in m, 'readback_stored_value_missing')
            return dict(outcome=m['class'],**({'value':m['stored']} if m['class']=='changed' else {})),p
        require(raw.get('action') in ('ref_create','ref_update') and r.get('field')==field, 'reference_field_mismatch', True)
        require(r.get('status')==raw['status'], 'reference_status_mismatch', True)
        require(isinstance(r.get('sent'),list) and isinstance(r.get('stored'),list), 'reference_measurements_missing')
        sent=raw['input'][field];sent=sent if isinstance(sent,list) else [sent]
        require(exact(sent,r['sent']), 'reference_sent_value_mismatch', True)
        return dict(outcome='id_projection',value=r['stored']),p

    def divergence(self, pos, row):
        require(row.get('evidence_format')=='div-evidence/1', 'unsupported_divergence_format')
        require(isinstance(row.get('create'),dict) and isinstance(row.get('update'),dict), 'pair_sides_missing')
        cp,c=self.write(row['create'],pos);up,u=self.write(row['update'],pos)
        require(cp < up, 'pair_order_invalid')
        require(c.get('session') is not None and c['session']==u.get('session'), 'pair_actor_unbound')
        entity, field = self.specification(c,u)
        # A successful update fixture GET is retained in model runs. It is a control,
        # not proof that the tested extreme value should be accepted.
        control=[(i,r) for i,r in enumerate(self.rows[:up]) if r.get('category')=='research'
            and r.get('logical_id')==u.get('logical_id') and r.get('method')=='GET'
            and r.get('path')==u.get('path') and r.get('status')==200 and r.get('session')==u.get('session')
            and r.get('action') in ('edge_uread','ref_uread')]
        require(len(control)==1,'update_fixture_control_missing_or_ambiguous')
        classes_differ=c['status']//100!=u['status']//100
        verdict='class_diverge' if classes_differ else 'same';readbacks=[];stored_different=None
        tier='recorded_divergence_http_pair'
        if c['status']//100==2 and u['status']//100==2:
            cr,crp=self.readback(row['create'],c,pos,field,entity);ur,urp=self.readback(row['update'],u,pos,field,entity)
            stored_different=not exact(cr,ur);verdict='stored_diverge' if stored_different else 'same'
            readbacks=[self.source(crp),self.source(urp)];tier='paired_producer_readback_measurements'
        if row.get('verdict')!=verdict:
            raise Conflict('divergence_verdict_mismatch',computed_verdict=verdict,reported=row.get('verdict'))
        audit=dict(family='DIV-1',source=self.source(pos),status='PRODUCER_MEASUREMENT_COMPARED' if readbacks else 'RAW_VERIFIED',
            entity=entity,field=field,computed_verdict=verdict,response_classes_differ=classes_differ,
            raw_write_pair_verified=True,independent_raw_state_verified=False if readbacks else None,
            stored_outcomes_differ=stored_different,witnesses=[self.source(cp),self.source(up),self.source(control[0][0])],
            readback_measurement_sources=readbacks,controls_verified=True)
        # Attach classifications to the existing update HTTP event, not a second request.
        facts=dict(pair_qualified=True,create_update_diverge=verdict!='same',
            raw_create_status=c['status'],raw_update_status=u['status'],model_pair_field=field,
            model_pair_response_classes_differ=classes_differ,model_pair_stored_measurements=bool(readbacks),divergence_full_state_verified=False,
            divergence_comparison_basis=tier)
        return audit, (up,facts,tier,self.source(cp))

    def verify(self, values):
        audits=[];handled=set();new=[];gaps=[];positions={o['source']['record']:o for o in values}
        for pos,row in enumerate(self.rows):
            category=row.get('category')
            if not ((category=='atomicity-check' and 'snapshots' in row) or
                    (category=='divergence-check' and 'evidence_format' in row)): continue
            handled.add(pos);family='ATOM-1-2' if category=='atomicity-check' else 'DIV-1'
            try:
                if category=='atomicity-check':audit,obs=self.atomicity(pos,row);new.append(obs)
                else:
                    audit,change=self.divergence(pos,row);up,facts,tier,create_source=change
                    require(up in positions,'normalized_update_missing')
                    target=positions[up];target['facts'].update(facts);target['field']=audit['field']
                    target.setdefault('witnesses',[]).append(dict(paired_create_source=create_source,divergence_source=self.source(pos)))
                    target['divergence_evidence_tier']=tier
                    if audit['computed_verdict']=='stored_diverge':target['evidence_tier']=tier
                audits.append(audit)
            except (Missing,Conflict) as exc:
                gaps.append(dict(family=family,source=self.source(pos),reason=str(exc),
                    status='PRODUCER_EVIDENCE_CONTRADICTION' if isinstance(exc,Conflict) else 'UNRESOLVED',
                    reported_verdict=row.get('verdict'), **getattr(exc,'details',{})))
        values.extend(new)
        return dict(resolved_measurements=audits,unknown_evidence=gaps,handled_records=sorted(handled))


def verify(rows,ir,context,values): return Verifier(rows,ir,context).verify(values)

