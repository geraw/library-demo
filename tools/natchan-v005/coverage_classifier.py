"""Reuse the classifier; reserve 'insufficient evidence' for genuinely missing facts."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'natchan-v003'))
from classifier import classify as base_classify, get, MISSING


def classify(observations,catalogs):
    report=base_classify(observations,catalogs)
    for row in report['assessments']:
        row['possible_known_bugs']=[p for p in row.get('possible_known_bugs',[]) if
                                    all(c['satisfied'] or get(row['facts'],c['condition']['fact']) is MISSING for c in p['checks'])]
    return report
