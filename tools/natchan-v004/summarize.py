"""Create a compact shareable report without copying private HTTP payloads."""
import argparse
from collections import Counter
import json
from pathlib import Path


def summarize(report):
    return {'schema_version':'natchan-tse-summary/1','source_repository':'weissye/vikunja_study',
            'source_commit':'a46ae1b4773e59727c37e9cd5f321bb1f1877a83',
            'manifest_sha256':report['manifest_sha256'],
            'runs':report['runs'],'http_records':sum(r['http_records'] or 0 for r in report['runs']),
            'http_5xx':sum(r['http_5xx'] or 0 for r in report['runs']),
            'oracle_only_run_count':sum(r['http_records'] is None for r in report['runs']),
            'known_signature_occurrences':report['known_signature_occurrences'],
            'by_version':{version:dict(Counter(r['catalog_id'] for r in report['assessments'] if
                          r.get('kind')=='known_bug' and r.get('product_version')==version))
                          for version in sorted({r['version'] for r in report['runs']})},
            'original_oracle_summary':report['original_oracle_summary'],
            'catalogs':report['catalogs'],
            'limitations':['Occurrence counts are not unique new bugs.',
                           'Vikunja receipts are direct reproducers, not Provengo detection measurements.',
                           'Gitea C4-C7 cloud evidence lacks complete original HTTP/log witnesses.',
                           'Three Vikunja burst 500s lack per-request timestamps for exact F01 log joins.',
                           'Gitea atomicity field states are producer measurements, not independent full snapshots.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    report=json.loads(a.report.read_text(encoding='utf-8-sig'))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(summarize(report),indent=2)+'\n',encoding='utf-8')
