import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('unified',Path(__file__).parents[1]/'checker.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def boundary(case='1',empty=True):return {'role':'boundary','case':case,'empty_verified':empty}
def event(method,path,response=None,body=None,status=201,role='tool',case='1'):
    return {'role':role,'case':case,'method':method,'path':path,'status':status,'request':body,'response':response}
def evaluate(tmp_path,rows,profile='library-issta-v006',**kwargs):
    path=tmp_path/'trace.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return m.evaluate_trace(path,profile,**kwargs)
def book_prefix():
    book={'id':101,'title':'book'}
    return [boundary(),event('POST','/books',book,{'title':'book'}),event('GET','/books',[book],status=200,role='oracle')]


def test_current_book_context_and_forged_verdict_ignored(tmp_path):
    rows=book_prefix()+[event('GET','/books/101',{'error':'missing'},status=404)]
    result=evaluate(tmp_path,rows)
    assert result['external_evaluator']['candidate_classes_in_evaluable_cases']==['bug-4']
    assert result['native_tool_faults']['status']=='not_supplied'
    # Remove the actual violation, keep a forged verdict: the evaluator must not trust it.
    result=evaluate(tmp_path,book_prefix()+[{'role':'verdict','violations':[{'rule':'EXISTING_BOOK_READ'}]}])
    assert result['external_evaluator']['candidate_classes_in_evaluable_cases']==[]


def test_missing_readback_is_unknown_not_zero(tmp_path):
    result=evaluate(tmp_path,book_prefix()[:2])
    assert result['status']=='NOT_FULLY_EVALUABLE'
    assert result['evaluable_case_count']==0


def test_empty_boundary_required(tmp_path):
    rows=book_prefix();rows[0]['empty_verified']=False
    result=evaluate(tmp_path,rows)
    assert result['status']=='NOT_FULLY_EVALUABLE'


def test_no_cross_case_book_stitching_even_reused_case_label(tmp_path):
    result=evaluate(tmp_path,book_prefix()+[boundary(),event('GET','/books/101',{},status=404)])
    assert result['case_count']==2
    assert result['external_evaluator']['candidate_classes_in_evaluable_cases']==[]


def test_no_boundary_is_not_evaluable(tmp_path):
    result=evaluate(tmp_path,book_prefix()[1:])
    assert result['status']=='NOT_FULLY_EVALUABLE'
    assert result['unscoped_record_count']==2


def test_bad_json_is_not_silently_a_negative(tmp_path):
    path=tmp_path/'trace.jsonl';path.write_text('{broken}\n')
    result=m.evaluate_trace(path,'library-v38',True,True)
    assert result['parse_issues'] and result['evaluable_case_count']==0


def test_legacy_marker_format_and_case_isolation(tmp_path):
    rows=[{'method':'POST','path':'/users','status':201,'response':{'id':1}}]
    rows += [{'method':'POST','path':'/books','status':201,'response':{'id':i}} for i in (1,2,3)]
    rows += [{'method':'POST','path':'/loans','status':201,'body':{'userId':1,'bookId':i},'response':{}} for i in (1,2,3)]
    path=tmp_path/'legacy.log';path.write_text(''.join('MODEL_EVENT '+json.dumps(r)+'\n' for r in rows))
    assert m.evaluate_trace(path,'library-v38')['status']=='NOT_FULLY_EVALUABLE'
    report=m.evaluate_trace(path,'library-v38',True,True)
    assert report['external_evaluator']['confirmed_classes_in_evaluable_cases']==['LOAN_LIMIT']
    split=[boundary()]+rows[:-1]+[boundary('2'),rows[-1]]
    report=evaluate(tmp_path,split,'library-v38')
    assert report['external_evaluator']['confirmed_classes_in_evaluable_cases']==[]


@pytest.mark.parametrize('profile',m.PROFILES)
def test_profile_loads_and_evaluates_without_native_or_false_generic_500(tmp_path,profile):
    report=evaluate(tmp_path,[boundary(),event('GET','/missing',{'error':'server error'},status=500)],profile)
    assert report['status']=='EVALUATED_RECORDED_CASES'
    assert report['external_evaluator']['confirmed_classes_in_evaluable_cases']==[]
    assert report['external_evaluator']['candidate_classes_in_evaluable_cases']==[]


def test_netbox_a2a_reuses_historical_uniqueness_witness(tmp_path):
    rows=[boundary(),event('POST','/api/dcim/sites',{'id':1,'slug':'same'}),event('POST','/api/dcim/sites',{'id':2,'slug':'same'})]
    report=evaluate(tmp_path,rows,'netbox-a2a-v38')
    assert report['external_evaluator']['confirmed_classes_in_evaluable_cases']==['C_UNIQUENESS']


def test_garage_reuses_historical_rule(tmp_path):
    rows=[boundary()]+[event('POST','/repair-orders',{'roId':str(i),'carVin':str(i),'customerId':'c','garageId':'g','status':'open'}) for i in (1,2,3)]
    report=evaluate(tmp_path,rows,'garage-v38')
    assert report['external_evaluator']['confirmed_classes_in_evaluable_cases']==['GARAGE_THREE_ACTIVE_ORDERS']


def test_unavailable_readback_is_not_a_negative(tmp_path):
    rows=book_prefix();rows[-1]['status']=500;rows[-1]['response']={'error':'unavailable'}
    report=evaluate(tmp_path,rows)
    assert report['evaluable_case_count']==0 and report['status']=='NOT_FULLY_EVALUABLE'


def test_internal_reset_cannot_stitch_legacy_prefix(tmp_path):
    rows=[boundary(),event('POST','/reset',{},status=200)]
    report=evaluate(tmp_path,rows,'library-v38')
    assert report['evaluable_case_count']==0
