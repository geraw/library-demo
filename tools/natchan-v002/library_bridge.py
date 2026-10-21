"""Adapt retained events to the preserved Library checker, without changing its rules."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

CHECKER_PATH = Path(__file__).resolve().parents[1] / 'semantic-checker-v001' / 'checker.py'


def checker():
    spec=importlib.util.spec_from_file_location('natchan_preserved_checker',CHECKER_PATH)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(events, artifact):
    """Retain source line numbers; imported verdict payloads are ignored by the checker."""
    records=sorted(events,key=lambda e:e['source']['line'])
    lines=[]
    for event in records:
        number=event['source']['line']
        if type(number) is not int or number <= len(lines):
            raise ValueError('Trace record source lines must be positive and unique')
        lines.extend(['']*(number-len(lines)-1))
        lines.append(json.dumps(event['payload'],ensure_ascii=False))
    # This is a representation adapter, not a replay: no API calls or SUT import.
    data=('\n'.join(lines)+'\n').encode('utf-8')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'retained-trace.jsonl'
        path.write_bytes(data)
        report=checker().evaluate_trace(path,'library-issta-v006')
    report['adapter_trace_sha256']=report.pop('trace_sha256')
    report['trace_sha256']=artifact['sha256']
    report['adapter_note']='Re-serialized retained records; source line numbers preserved. Original and adapter hashes are separate.'
    report['evaluator_source']=dict(path='tools/semantic-checker-v001/checker.py',
        sha256=hashlib.sha256(CHECKER_PATH.read_bytes()).hexdigest(),
        rules_manifest_sha256=hashlib.sha256((CHECKER_PATH.parent/'provenance.json').read_bytes()).hexdigest())
    return report
