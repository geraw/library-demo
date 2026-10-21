#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results-root', required=True)
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    root = Path(a.results_root)
    rows = []
    for p in sorted(root.glob('*/run_metadata.json')):
        try:
            rows.append(json.loads(p.read_text(encoding='utf-8-sig')))
        except Exception:
            pass
    latest = {}
    for r in rows:
        latest[(r.get('tool'), r.get('input_mode'))] = r

    latest_rows = list(latest.values())
    out = {
        'schema_version': 2,
        'artifact_version': 'v36',
        'experiment': 'netbox_a2a',
        'measurement_parity': {
            'same_sut': True,
            'same_openapi_projection_12_operations': True,
            'same_external_http_proxy': True,
            'same_sequence_local_semantic_evaluator': True,
            'campaign_global_score_used_officially': False,
            'native_tool_faults_kept_separate': True,
            'hidden_ground_truth_never_used_for_official_score': True,
            'hidden_ground_truth_not_exposed_to_tools': True,
        },
        'information_parity_note': (
            'ProvengoBasic, ProvengoComplex, RESTler and EvoMaster receive the same '
            'metadata-stripped OpenAPI boundary. ProvengoComplex derives deep structural '
            'families automatically from that OpenAPI and receives no analyst-authored '
            'fault trigger or seeded-fault selector.'
        ),
        'native_tool_faults': [
            {'tool': r.get('tool'), 'input_mode': r.get('input_mode'), 'value': r.get('native_tool_faults')}
            for r in latest_rows
        ],
        'sequence_confirmed_semantic_classes': [
            {'tool': r.get('tool'), 'input_mode': r.get('input_mode'), 'classes': r.get('sequence_confirmed_semantic_classes', []), 'score': r.get('sequence_confirmed_score', '0/5')}
            for r in latest_rows
        ],
        'campaign_reachability_classes': [
            {'tool': r.get('tool'), 'input_mode': r.get('input_mode'), 'classes': r.get('campaign_reachability_classes', []), 'diagnostic_only': True}
            for r in latest_rows
        ],
        'hidden_triggered_classes': [
            {'tool': r.get('tool'), 'input_mode': r.get('input_mode'), 'classes': r.get('hidden_triggered_classes', []), 'score': r.get('hidden_triggered_score', '0/5'), 'diagnostic_only': True}
            for r in latest_rows
        ],
        'ground_truth_consistency': [
            {'tool': r.get('tool'), 'input_mode': r.get('input_mode'), 'consistency': r.get('ground_truth_consistency', {})}
            for r in latest_rows
        ],
        'latest_runs': latest_rows,
        'run_count': len(rows),
    }
    Path(a.output).write_text(json.dumps(out, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
