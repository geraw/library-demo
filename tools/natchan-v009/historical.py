"""Recompute retained archive observations and classify without importing verdicts."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyzer import classify, ROOT, FAMILIES
spec=importlib.util.spec_from_file_location('retained_family_audit',ROOT.parent/'natchan-v008/family_audit.py')
archive_gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive_gateway)

def analyze(paths):
    raw=archive_gateway.audit(paths);observations=[];coverage=[]
    for journal in raw['journals']:
        for n,item in enumerate(journal['observations']):
            family=item['family'];level=item['evidence_level'];f=item['facts'];facts={}
            metadata=dict(evidence_tier=level,source_lines=item['lines'])
            if level=='recomputed-from-projected-ids':
                facts['reference_projection_differs']=not f['ids_equal']
                # A rejected or missing reference can intentionally be ignored. No policy guessed.
                facts['projection_evidence']='producer_id_projection'
            if level=='same-field-value-status-comparison':facts['status_pair_difference_observed']=f['response_class_differs']
            if level=='same-target-delete-readback':facts['same_target_still_readable_after_delete']=f['still_readable']
            if level in ('identical-write-pair','probe-and-readback','retained-attempt'):
                facts['server_error']=f.get('server_error',False)
            coverage.append(dict(family=family,evidence_level=level,source=item['source'],lines=item['lines'],
                semantic_status='not_evaluable',missing=[f.get('limitation','Required semantic context not established')]))
            if not facts:continue
            source=dict(chain=item['source'],lines=item['lines'])
            observations.append(dict(id=item['source'][0]['sha256']+':'+str(len(observations)),
                product='historical-product-unqualified',product_version=None,run_id=journal['source'][-1]['sha256'],
                tool='historical-producer-unqualified',source=source,facts=facts,fact_basis='recomputed',**metadata))
    report=classify(observations,ROOT/'catalogs');report['historical_coverage']=coverage
    report['family_evidence_counts']={f:dict(Counter(c['evidence_level'] for c in coverage if c['family']==f)) or {'no_measurements':True} for f in FAMILIES}
    report['archive_count']=len(paths);report['distinct_journals']=len(raw['journals']);report['new_sut_requests']=0
    # One finding can generate several catalog assessments. Count unique observation/pattern pairs.
    pairs={(a['observation_id'],p) for a in report['assessments'] for p in a.get('patterns',[])}
    report['pattern_occurrences']=dict(Counter(p for _,p in pairs))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    r=analyze(a.input);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r['pattern_occurrences'],indent=2))
