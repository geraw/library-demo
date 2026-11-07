import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT))
import analyze_runs as analyzer
from native_adapters import analyze


def test_three_tool_metrics_are_separate(tmp_path):
    native=tmp_path/'native.jsonl';native.write_text(json.dumps({'case':1,'native_pass':False})+'\n')
    evo=tmp_path/'evo.log';evo.write_text('Potential faults: 3\n')
    buckets=tmp_path/'bug_buckets';buckets.mkdir();(buckets/'one.txt').write_text('native evidence')
    manifest={'schema_version':1,'runs':[
        {'id':'p','tool':'provengo','system':'library','artifacts':{'native_jsonl':'native.jsonl'}},
        {'id':'r','tool':'restler','system':'garage','artifacts':{'bug_buckets':'bug_buckets'}},
        {'id':'e','tool':'evomaster','system':'netbox','artifacts':{'log':'evo.log'}}]}
    result=analyzer.analyze_manifest(manifest,tmp_path)
    assert result['run_count']==3
    assert [r['native']['count'] for r in result['runs']]==[1,1,3]
    assert len({r['native']['metric'] for r in result['runs']})==3
    assert all(r['semantic']['status']=='not_evaluated' for r in result['runs'])


def test_missing_evidence_not_zero_and_other_tool_can_be_registered(tmp_path):
    assert analyze('evomaster',{})['count'] is None
    assert analyze('newtool',{})['status']=='unknown'
    path=tmp_path/'evo.log';path.write_text('Finished without a recognized summary')
    assert analyze('evomaster',{'log':path})['count'] is None
    path.write_text('Potential faults: 0')
    assert analyze('evomaster',{'log':path})['count']==0


def test_latest_run_does_not_hide_previous_run(tmp_path):
    result=analyzer.analyze_manifest({'schema_version':1,'runs':[
        {'id':'seed1','tool':'evomaster','system':'library'},
        {'id':'seed2','tool':'evomaster','system':'library'}]},tmp_path)
    assert result['run_count']==2
    with pytest.raises(ValueError):analyzer.analyze_manifest({'schema_version':1,'runs':[
        {'id':'same','tool':'evomaster','system':'library'},
        {'id':'same','tool':'evomaster','system':'library'}]},tmp_path)


def test_truncated_native_report_is_not_zero(tmp_path):
    path=tmp_path/'native.jsonl';path.write_text('{broken}\n'+json.dumps({'case':1,'native_pass':True})+'\n')
    result=analyze('provengo',{'native_jsonl':path})
    assert result['status']=='incomplete' and result['count'] is None


def test_http_anomalies_are_not_semantic_bugs(tmp_path):
    trace=tmp_path/'http.jsonl';trace.write_text(json.dumps({'role':'tool','case':1,'method':'GET','path':'/missing','status':500,'response':{}})+'\n')
    result=analyzer.analyze_manifest({'schema_version':1,'runs':[{'id':'e','tool':'evomaster','system':'any',
        'profile':'library-issta-v006','artifacts':{'trace':'http.jsonl'}}]},tmp_path)['runs'][0]
    assert result['http_anomalies']['http_5xx']==1
    assert result['native']['count'] is None
    assert result['semantic']['status']=='NOT_FULLY_EVALUABLE'
    assert result['semantic']['external_evaluator']['confirmed_classes_in_evaluable_cases']==[]


def test_inputs_are_measured_not_assumed_equal(tmp_path):
    (tmp_path/'a').write_text('A');(tmp_path/'b').write_text('B')
    runs=[{'id':n,'tool':'provengo','system':'library','inputs':{'sut':n}} for n in ['a','b']]
    report=analyzer.analyze_manifest({'schema_version':1,'runs':runs},tmp_path)
    assert report['runs'][0]['input_sha256']['sut']!=report['runs'][1]['input_sha256']['sut']


def test_csv_preserves_unknown_count(tmp_path):
    report=analyzer.analyze_manifest({'schema_version':1,'runs':[{'id':'p','tool':'provengo','system':'library'}]},tmp_path)
    output=tmp_path/'report.json';table=analyzer.write_report(report,output)
    import csv
    row=next(csv.DictReader(table.open(encoding='utf-8-sig')))
    assert row['native_count']=='' and row['native_status']=='unknown'
    with pytest.raises(ValueError):analyzer.write_report(report,output)
