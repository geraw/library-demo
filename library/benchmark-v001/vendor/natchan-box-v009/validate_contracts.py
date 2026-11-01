"""Derive and freeze contract-only acceptance inputs; never opens run evidence."""
import argparse
from pathlib import Path

import natchan
from common import InputError, VERSION, keys, loads, read, write


def validate(manifest, output):
    if output.exists():
        raise InputError('OUTPUT_MUST_BE_NEW_DIRECTORY')
    doc = loads(read(manifest))
    keys(doc, {'schema_version', 'contracts'}, {'schema_version', 'contracts'})
    if doc['schema_version'] != 'natchan-contract-check/1' or not isinstance(doc['contracts'], list):
        raise InputError('CONTRACT_CHECK_MANIFEST_INVALID')
    output.mkdir(parents=True)
    rows, ids = [], set()
    for item in doc['contracts']:
        keys(item, {'id', 'path', 'sha256'}, {'id', 'path', 'sha256'})
        name = item['id']
        if not isinstance(name, str) or not name.isascii() or not name.replace('-', '').isalnum() or name in ids:
            raise InputError('CONTRACT_CHECK_ID_INVALID')
        ids.add(name)
        source = natchan.local_path(manifest.resolve().parent, item['path'])
        if natchan.hash_file(source) != item['sha256']:
            raise InputError('CONTRACT_CHECK_INPUT_HASH_MISMATCH')
        try:
            context = natchan.contract(source)
            folder = output / name
            folder.mkdir()
            knowledge = folder / 'knowledge.json'
            write(knowledge, context)
            write(folder / 'freeze.json', natchan.make_freeze(source, knowledge))
            bindings = context['write_read_bindings']
            path_bindings = context.get('create_update_bindings', {})
            row = {'id': name, 'exit_code': 0, 'contract_sha256': item['sha256'],
                   'knowledge_bytes': knowledge.stat().st_size, 'operations': len(context['operations']),
                   'structural_candidates': sum(v['status'] == 'structural_candidate' for v in bindings.values()),
                   'usable_scalar_bindings': sum(v.get('usable_scalar_fields', 0) > 0 for v in bindings.values()),
                   'unknown_bindings': sum(v['status'] == 'unknown' for v in bindings.values()),
                   's2_update_families': sum(v['status'] == 'structural_candidate' for v in path_bindings.values()),
                   's2_contract_pairs': sum(bool(p['fields']) for v in path_bindings.values() for p in v['pairs']),
                   'gaps': len(context['gaps'])}
        except InputError as e:
            row = {'id': name, 'exit_code': e.code, 'reason': str(e), 'contract_sha256': item['sha256']}
        rows.append(row)
    report = {'schema_version': 'natchan-contract-check-result/1', 'analyzer_version': VERSION,
              'scope': 'contract_derivation_and_freeze_only_not_run_analysis', 'contracts': rows,
              'run_evidence_read': False, 'new_sut_requests': 0}
    write(output / 'summary.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    try:
        result = validate(args.manifest, args.output)
        return 0 if all(r['exit_code'] == 0 for r in result['contracts']) else 2
    except (InputError, OSError):
        print('CONTRACT_CHECK_FAILED_SEE_SUMMARY_OR_MANIFEST')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
