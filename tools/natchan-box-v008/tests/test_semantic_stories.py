import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_stories as fixture_module
files=fixture_module.files
from stories_evidence import group_id

HASH='a'*64


def entity(path,refs=()):return dict(path=path,detail=path+'/{id}',id_field='id',create_method='post',update='patch',refs=list(refs))


def metadata():
    return dict(schema_version='natchan-story-semantics/1',product='widget',contract_sha256=HASH,
        entities={'folder':entity('/folders'),'entry':entity('/entries',[dict(field='folder_id',target='folder',shape='scalar')])},
        projections=[dict(view_template='/folders/{id}/view',owner='folder',response_array=False,
            places=[dict(at='$.entries[]',parent_at='$',child='entry',parent_entity='folder',reference_field='folder_id')])],arithmetic=[])


def rows_from(steps,sid='PROJNEST_folder_view'):
    return [dict(category='research',index=i,session='A',method=m,path=p,input=b,status=s,response=json.dumps(r),logical_id=f'{sid}_{i+1} {label}') for i,(m,p,b,s,r,label) in enumerate(steps)]


def projection(mode='move',broken=True):
    child=dict(id=11,folder_id=101,name='old')
    old=dict(id=101,entries=[child]);new=dict(id=202,entries=[])
    steps=[('POST','/folders',{},201,{'id':101},'create folder'),('POST','/folders',{},201,{'id':202},'create folder'),
        ('POST','/entries',{'folder_id':101,'name':'old'},201,child,'create entry'),
        ('GET','/folders/101/view',None,200,old,'read old root view (cache)'),
        ('GET','/folders/202/view',None,200,new,'read new root view (cache)')]
    if mode=='move':
        steps += [('PATCH','/entries/11',{'folder_id':202},200,dict(child,folder_id=202),'move N1_0 to B1 (second root)'),
                  ('GET','/folders/101/view',None,200,old if broken else dict(id=101,entries=[]),'read old root view'),
                  ('GET','/folders/202/view',None,200,new if broken else dict(id=202,entries=[dict(child,folder_id=202)]),'read new root view')]
    elif mode=='update':
        steps += [('PATCH','/entries/11',{'name':'changed'},200,dict(child,name='changed'),'update N0_0'),
                  ('GET','/folders/101/view',None,200,old if broken else dict(id=101,entries=[dict(child,name='changed')]),'read view again')]
    else:
        steps += [('DELETE','/entries/11',None,204,{},'delete N0_1'),
                  ('GET','/folders/101/view',None,200,old if broken else dict(id=101,entries=[]),'read view again')]
    return rows_from(steps)


def packaged(rows,spec=None):
    f=files(rows);r=json.loads(f['result_stories.json']);r['contract_sha256']=HASH;r['stories']=[dict(story=sid,status='COMPLETED',exit=0,failed_checks=[]) for sid in sorted({group_id(row)[0] for row in rows})];f['result_stories.json']=json.dumps(r)
    f['story-semantics.json']=json.dumps(spec or metadata());return f


def arithmetic(broken=True,mode='percent'):
    spec=metadata();spec['projections']=[];spec['entities'].update(config=entity('/configs',[dict(field='entry',target='entry',shape='scalar')]))
    spec['arithmetic']=[dict(entity='config',parent_entity='entry',parent_field='entry',operator_field='op',operators={'set':'=','add':'+','sub':'-'},iteration_field='iteration',value_field='value',step_field='mode',modes={'percent':'percent','absolute':'absolute'},view_template='/folders/{id}/computed',items_at='$.items[]',item_parent_field='entry_id',output_field='quantity',rounding={'mode':'unspecified'})]
    plan=[(1,'set',10),(2,'add',10 if mode=='percent' else 2),(4,'sub',10 if mode=='percent' else 2),(5,'set',7)]
    steps=[]
    for it,op,val in plan:
        body=dict(entry=11,iteration=it,op=op,value=val,mode=mode)
        steps.append(('POST','/configs',body,201,dict(body,id=it),'create config'))
    expected=[10,11,11,9 if broken else 9.9,7,7] if mode=='percent' else [10,12,12,9 if broken else 10,7,7]
    view=[dict(iteration=i+1,items=[dict(entry_id=11,quantity=v)]) for i,v in enumerate(expected)]
    steps.append(('GET','/folders/101/computed',None,200,view,'read arithmetic view'))
    return rows_from(steps,'OPENUM_config_percent'),spec


def stale_context(empty=False):
    spec=metadata();spec['projections']=[];spec['entities']['tag']=entity('/tags')
    spec['entities']['entry']['refs']=[dict(field='tags',target='tag',shape='array')]
    steps=[('GET','/tags/6',None,200,dict(id=6),'read tag'),
        ('GET','/entries/11',None,200,dict(id=11,tags=[] if empty else [dict(id=6)],assignee=None),'read entry (snapshot)'),
        ('DELETE','/tags/6',None,204,{},'delete tag'),
        ('PATCH','/entries/11',dict(tags=[] if empty else [6],assignee='other'),500,{},'stale write entry'),
        ('GET','/tags/6',None,404,{},'read tag')]
    return rows_from(steps,'STALE_entry_tags'),spec


def nested_projection(broken=True):
    rows=projection(broken=broken);spec=metadata()
    spec['entities']['branch']=entity('/branches',[dict(field='folder_id',target='folder',shape='scalar')])
    spec['entities']['entry']['refs']=[dict(field='branch_id',target='branch',shape='scalar')]
    spec['projections'][0]['places']=[dict(at='$.branches[].entries[]',parent_at='$.branches[]',child='entry',parent_entity='branch',reference_field='branch_id')]
    for r in rows:
        if isinstance(r.get('input'),dict) and 'folder_id' in r['input']:r['input']['branch_id']=r['input'].pop('folder_id')+1000
        b=json.loads(r['response'])
        if r['path'].startswith('/entries') and isinstance(b,dict) and 'folder_id' in b:b['branch_id']=b.pop('folder_id')+1000
        if r['method']=='GET' and isinstance(b,dict) and 'entries' in b:
            kids=b.pop('entries');branch=b['id']+1000
            for k in kids:k['branch_id']=k.pop('folder_id')+1000
            b['branches']=[dict(id=branch,entries=kids)]
        r['response']=json.dumps(b)
    for pos,pid in enumerate((101,202)):
        rows.insert(2+pos,dict(category='research',index=80+pos,session='A',method='POST',path='/branches',input=dict(folder_id=pid),status=201,response=json.dumps(dict(id=pid+1000,folder_id=pid)),logical_id=''))
    for i,r in enumerate(rows):r['logical_id']=f'PROJNEST_folder_view_{i+1} operation'
    return rows,spec


class SemanticStoriesTests(unittest.TestCase):
    setUp=fixture_module.StoriesTests.setUp
    read=fixture_module.StoriesTests.read
    cli=fixture_module.StoriesTests.cli
    def test_step_parser_does_not_consume_description_underscores(self):
        self.assertEqual(group_id({'logical_id':'PROJNEST_folder_view_42 move N1_0 to B1'}),('PROJNEST_folder_view',42,'move N1_0 to B1'))
    def test_move_both_projections_fail(self):
        a=self.read(packaged(projection()));self.assertEqual(a['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_correct_move_has_no_semantic_findings(self):
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(projection(broken=False)))['rule_occurrences'])
    def test_rejected_move_does_not_prove_projected_relation(self):
        rows=projection();rows[5]['status']=409
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_acknowledgement_must_name_new_parent(self):
        rows=projection();rows[5]['response']=json.dumps(dict(id=11,folder_id=101))
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_old_parent_baseline_must_contain_child(self):
        rows=projection();rows[3]['response']=json.dumps(dict(id=101,entries=[]))
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_destination_preimage_required(self):
        rows=projection();rows[4]['status']=403
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_destination_already_contains_child_not_exclusive_move(self):
        rows=projection();rows[4]['response']=json.dumps(dict(id=202,entries=[dict(id=11,folder_id=202)]))
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_actor_mismatch_is_not_a_move_comparison(self):
        rows=projection();rows[3]['session']='B'
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_preimage_from_another_entity_with_same_numeric_id_is_not_used(self):
        rows=projection();rows[3]['response']=json.dumps(dict(id=101,other_entities=[dict(id=11)]))
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_other_write_ends_comparison_window(self):
        rows=projection();rows.insert(6,dict(rows[5],index=99,logical_id='PROJNEST_folder_view_7 other update'))
        for i,r in enumerate(rows):r['logical_id']=f'PROJNEST_folder_view_{i+1} operation'
        # The second write is no actual move, so no postimage is attributed to the first.
        rows[6]['input']={'name':'changed'};rows[6]['response']=json.dumps(dict(id=11,folder_id=202,name='changed'))
        self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows))['rule_occurrences'])
    def test_update_stale_projection(self):
        self.assertEqual(self.read(packaged(projection('update')))['rule_occurrences']['STORY-PROJECTION-UPDATE'],1)
    def test_correct_update_projection(self):
        self.assertNotIn('STORY-PROJECTION-UPDATE',self.read(packaged(projection('update',False)))['rule_occurrences'])
    def test_delete_stale_projection(self):
        self.assertEqual(self.read(packaged(projection('delete')))['rule_occurrences']['STORY-PROJECTION-DELETE'],1)
    def test_correct_delete_projection(self):
        self.assertNotIn('STORY-PROJECTION-DELETE',self.read(packaged(projection('delete',False)))['rule_occurrences'])
    def test_arithmetic_discrepancy_is_recomputed(self):
        rows,spec=arithmetic();a=self.read(packaged(rows,spec));self.assertEqual(a['rule_occurrences']['STORY-ARITHMETIC-DISCREPANCY'],1)
        o=next(o for o in a['observations'] if o.get('story_semantic_checks'));self.assertEqual(o['story_semantic_checks'][0]['differences'],[dict(iteration=4,expected=9.9,observed=9.0)])
    def test_correct_percent_arithmetic(self):
        rows,spec=arithmetic(False);self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_correct_absolute_arithmetic(self):
        rows,spec=arithmetic(False,'absolute');self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_explicit_floor_policy_is_not_called_a_bug(self):
        rows,spec=arithmetic();spec['arithmetic'][0]['rounding']={'mode':'floor','quantum':1}
        self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_explicit_display_rounding_is_retained_as_observation(self):
        rows,spec=arithmetic();body=json.loads(rows[-1]['response']);body[3]['items'][0]['quantity']=10;rows[-1]['response']=json.dumps(body);spec['arithmetic'][0]['rounding']['display_steps']=[1]
        a=self.read(packaged(rows,spec));self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',a['rule_occurrences'])
        self.assertIn('STORY_ARITHMETIC_DISPLAY_ROUNDING_COMPATIBLE',[g['code'] for g in a['toolkit_coverage_gaps']])
    def test_unknown_operator_not_guessed(self):
        rows,spec=arithmetic();rows[1]['input']['op']='multiply';rows[1]['response']=json.dumps(dict(rows[1]['input'],id=2))
        self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_failed_creation_is_not_an_operand(self):
        rows,spec=arithmetic();rows[1]['status']=400
        # With the plus refused, remove its effect from the view; the remaining accepted plan is consistent.
        body=json.loads(rows[-1]['response']);body[1]['items'][0]['quantity']=10;body[2]['items'][0]['quantity']=10;body[3]['items'][0]['quantity']=9;rows[-1]['response']=json.dumps(body)
        self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_duplicate_iteration_is_ambiguous(self):
        rows,spec=arithmetic();rows[1]['input']['iteration']=1;rows[1]['response']=json.dumps(dict(rows[1]['input'],id=2))
        self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_missing_parent_in_view_is_not_arithmetic_failure(self):
        rows,spec=arithmetic();body=json.loads(rows[-1]['response']);body[3]['items'][0]['entry_id']=999;rows[-1]['response']=json.dumps(body)
        self.assertNotIn('STORY-ARITHMETIC-DISCREPANCY',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_contract_mismatch_disables_semantic_promotion(self):
        spec=metadata();spec['contract_sha256']='b'*64
        a=self.read(packaged(projection(),spec));self.assertNotIn('STORY-MOVE-PROJECTION',a['rule_occurrences'])
        self.assertIn('STORY_SEMANTICS_CONTRACT_BINDING_MISMATCH',[g['code'] for g in a['toolkit_coverage_gaps']])
    def test_product_mismatch_is_invalid(self):
        spec=metadata();spec['product']='other'
        p,r=self.cli(packaged(projection(),spec));self.assertEqual(p.returncode,2)
    def test_unknown_semantic_schema_is_unsupported(self):
        spec=metadata();spec['schema_version']='future'
        p,r=self.cli(packaged(projection(),spec));self.assertEqual(p.returncode,3)
    def test_native_summary_verdicts_do_not_determine_move_findings(self):
        f=packaged(projection());r=json.loads(f['result_stories.json']);r['stories'][0]['failed_checks']=[];r['stories'][0]['checks']=0;f['result_stories.json']=json.dumps(r)
        self.assertEqual(self.read(f)['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_cli_emits_comparisons_and_never_version_confirms_toy_bug(self):
        p,r=self.cli(packaged(projection()));self.assertEqual(p.returncode,0)
        f=json.loads((self.base/'output/findings.json').read_text())['findings'];self.assertEqual(len(f),2);self.assertTrue(f[0]['semantic_checks']);self.assertEqual(r['counts']['known_bug_occurrences'],0)


    def test_unknown_projection_language_is_invalid_input(self):
        spec=metadata();spec['projections'][0]['places'][0]['at']='$.entries[?(@.id)]'
        p,r=self.cli(packaged(projection(),spec));self.assertEqual(p.returncode,2)
    def test_unknown_rounding_policy_is_unsupported(self):
        rows,spec=arithmetic();spec['arithmetic'][0]['rounding']['mode']='magic'
        p,r=self.cli(packaged(rows,spec));self.assertEqual(p.returncode,3)
    def test_generic_array_reference_context_is_qualified(self):
        rows,spec=stale_context()
        a=self.read(packaged(rows,spec));self.assertEqual(a['rule_occurrences']['STORY-MISSING-REFERENCE-5XX'],1)
        o=next(o for o in a['observations'] if o.get('facts',{}).get('story_stale_reference_context_verified'))
        self.assertEqual(o['facts']['reference_shape'],'array')
        self.assertEqual(o['facts']['non_reference_changed_fields'],['assignee'])
        self.assertFalse(o['story_semantic_checks'][0]['causality_proven'])
    def test_empty_snapshot_and_request_do_not_establish_deleted_reference(self):
        rows,spec=stale_context(empty=True);a=self.read(packaged(rows,spec))
        self.assertNotIn('STORY-MISSING-REFERENCE-5XX',a['rule_occurrences'])
        self.assertEqual(a['rule_occurrences']['STORY-REFERENCE-PRECONDITION-FAILED'],1)
    def test_another_actor_does_not_prove_reference_context(self):
        rows,spec=stale_context();rows[0]['session']='B'
        self.assertNotIn('STORY-MISSING-REFERENCE-5XX',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_forbidden_target_read_is_not_target_absence(self):
        rows,spec=stale_context();rows[-1]['status']=403
        self.assertNotIn('STORY-MISSING-REFERENCE-5XX',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_nested_projection_move_is_not_limited_to_product_names(self):
        rows,spec=nested_projection();self.assertEqual(self.read(packaged(rows,spec))['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_correct_nested_projection_move(self):
        rows,spec=nested_projection(False);self.assertNotIn('STORY-MOVE-PROJECTION',self.read(packaged(rows,spec))['rule_occurrences'])
    def test_grouped_array_root_projection(self):
        rows=projection();spec=metadata();spec['projections'][0]['response_array']=True;spec['projections'][0]['places'][0]['at']='$[].entries[]'
        for r in rows:
            if r['method']=='GET':r['response']=json.dumps([json.loads(r['response'])])
        self.assertEqual(self.read(packaged(rows,spec))['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_new_product_name_and_routes_do_not_change_rule(self):
        rows=projection();spec=metadata();spec['product']='unseen-product'
        for r in rows:r['path']=r['path'].replace('/folders','/collections').replace('/entries','/items')
        for e in spec['entities'].values():
            e['path']=e['path'].replace('/folders','/collections').replace('/entries','/items');e['detail']=e['detail'].replace('/folders','/collections').replace('/entries','/items')
        spec['projections'][0]['view_template']='/collections/{id}/view'
        f=packaged(rows,spec);d=json.loads(f['result_stories.json']);d['sut']='unseen-product';f['result_stories.json']=json.dumps(d)
        self.assertEqual(self.read(f)['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_repeated_read_does_not_inflate_one_move_check(self):
        rows=projection();rows.append(dict(rows[-2],index=99,logical_id='PROJNEST_folder_view_9 another cached read'))
        self.assertEqual(self.read(packaged(rows))['rule_occurrences']['STORY-MOVE-PROJECTION'],2)
    def test_external_semantic_configuration_cli(self):
        f=packaged(projection());profile=self.base/'external.json';profile.write_text(f.pop('story-semantics.json'))
        import subprocess
        archive=self.base/'external.zip';archive.write_bytes(fixture_module.pack(f))
        request=self.base/'external.request.json';request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='external',tool='provengo',product='widget',product_version='unknown'),evidence=dict(adapter='toolkit-v1',archive=str(archive)),configuration=dict(story_semantics=str(profile)))))
        p=subprocess.run([sys.executable,str(ROOT/'natchan.py'),'--request',str(request),'--output',str(self.base/'external-output')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        r=json.loads((self.base/'external-output/result.json').read_text());self.assertEqual(r['counts']['finding_occurrences'],2)

    def test_isolated_python_cli_reads_owned_modules(self):
        import subprocess
        f=packaged(projection());archive=self.base/'isolated.zip';archive.write_bytes(fixture_module.pack(f));request=self.base/'isolated.request.json'
        request.write_text(json.dumps(dict(schema_version='natchan-request/1',run=dict(id='isolated',tool='provengo',product='widget',product_version='unknown'),evidence=dict(adapter='toolkit-v1',archive=str(archive)))))
        p=subprocess.run([sys.executable,'-I',str(ROOT/'natchan.py'),'--request',str(request),'--output',str(self.base/'isolated-output')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
    def test_failed_precondition_is_separate_from_a_confirmed_product_bug(self):
        rows,spec=stale_context(True);p,r=self.cli(packaged(rows,spec));self.assertEqual(p.returncode,0)
        findings=json.loads((self.base/'output/findings.json').read_text())['findings']
        self.assertEqual(findings[0]['classification_role'],'test_precondition_failure')
        self.assertEqual(r['counts']['known_bug_occurrences'],0)

    def test_rounding_stage_is_not_silently_ignored(self):
        rows,spec=arithmetic();spec['arithmetic'][0]['rounding']['stage']='after_all_operations'
        p,r=self.cli(packaged(rows,spec));self.assertEqual(p.returncode,3)
    def test_display_steps_must_be_a_list(self):
        rows,spec=arithmetic();spec['arithmetic'][0]['rounding']['display_steps']='1'
        p,r=self.cli(packaged(rows,spec));self.assertEqual(p.returncode,2)
    def test_preimages_are_not_borrowed_from_an_earlier_attempt(self):
        rows=projection();prefix=rows[:5];tail=rows[5:]
        restart=dict(rows[0],status=400,index=77,logical_id='PROJNEST_folder_view_1 create folder')
        for i,r in enumerate(tail):r['index']=80+i;r['logical_id']=f'PROJNEST_folder_view_{i+2} operation'
        a=self.read(packaged(prefix+[restart]+tail))
        self.assertNotIn('STORY-MOVE-PROJECTION',a['rule_occurrences'])
        self.assertIn('STORY_ATTEMPTS_SEPARATED',[g['code'] for g in a['toolkit_coverage_gaps']])

if __name__=='__main__':unittest.main()
