"""Reanalyze versioned Library archives through preserved gateways and common rules.

Offline only. Each dataset declares archive layout and tool/product gateways.
Legacy compact summaries without oracle reads must not be scored with this CLI.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'natchan-v002'))
from evidence import ingest, Limits, library_manifest
from analyze import analyze_envelope
sys.path.insert(0,str(ROOT.parent/'natchan-v003'))
from library_adapter import observations_from_analysis
sys.path.insert(0,str(ROOT))
from engine import analyze as common_analyze


def run(manifest,output):
    if output.exists():raise ValueError('Use a fresh output directory')
    parts=[];datasets=[]
    for spec in manifest['datasets']:
        path=Path(spec['archive'])
        mapping=library_manifest() if spec.get('layout')=='library-v011' else spec['manifest']
        limits=Limits(max_member_bytes=512*1024*1024,max_total_bytes=2*1024*1024*1024,max_events=300000)
        env=ingest(path,mapping,limits=limits)
        result=analyze_envelope(env,'control' if spec.get('layout')=='library-v011' else None)
        row=dict(id=spec['id'],archive=str(path),archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 status=result['status'],issues=env['issues'],summary=result['summary'],runs=[],
                 control_comparison=result['control_comparison'])
        for r in result['runs']:
            semantic=r['semantic']
            row['runs'].append(dict(id=r['id'],tool=r['tool'],semantic_status=semantic['status'],
                external_evaluator=semantic.get('external_evaluator'),native=r['native'],
                candidate_class_cases=dict(Counter(k for c in semantic.get('cases',[]) if c.get('evaluable') for k in c.get('result',{}).get('candidate_classes',[])))))
        datasets.append(row)
        if result['status']!='complete':continue
        values=observations_from_analysis(result)
        artifacts={a['id']:a for a in env['artifacts']}
        for o in values:
            original=o['source'];artifact=artifacts[original['artifact_id']]
            o['source']=dict(original,sha256=artifact['sha256'],record=original['line'],file=str(path),member=artifact['locator'])
            o['run_id']=spec['id']+':'+o['run_id']
        run_rows=[dict(id=spec['id']+':'+r['id'],product='library',version='issta-v006',tool=r['tool'],http_records=None) for r in result['runs']]
        parts.append((spec['id'],dict(observations=values,runs=run_rows,
            read_inputs=[dict(path=str(path),sha256=row['archive_sha256'])])))
    classified=common_analyze(parts)
    classified['library_datasets']=datasets
    classified['archive_limits']=dict(max_member_bytes=limits.max_member_bytes,max_total_bytes=limits.max_total_bytes,max_events=limits.max_events)
    classified['gateway_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.mkdir(parents=True)
    (output/'analysis.json').write_text(json.dumps(classified,ensure_ascii=False,indent=2))
    (output/'summary.json').write_text(json.dumps(dict(datasets=datasets,rule_occurrences=classified['rule_occurrences'],
        new_sut_requests=0,analyst_narrative_used=False),ensure_ascii=False,indent=2))
    print(json.dumps(dict(status='complete' if all(x['status']=='complete' for x in datasets) else 'incomplete',
        datasets=len(datasets),rules=classified['rule_occurrences'])))
    return classified


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(json.loads(a.manifest.read_text()),a.output)
