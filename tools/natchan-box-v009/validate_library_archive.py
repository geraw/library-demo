"""Retrospective transport acceptance utility; no seeded-bug answers enter the judge."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

import natchan
from common import InputError, digest, write, loads, read


def validate(archive, output):
    if output.exists():
        raise InputError('OUTPUT_MUST_BE_NEW_DIRECTORY')
    output.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        contract_info = z.getinfo('openapi.json')
        if contract_info.file_size > 32 * 1024 * 1024:
            raise InputError('CONTRACT_TOO_LARGE')
        (output / 'contract.json').write_bytes(z.read(contract_info))
        write(output / 'knowledge.json', natchan.contract(output / 'contract.json'))
        write(output / 'freeze.json', natchan.make_freeze(output / 'contract.json', output / 'knowledge.json'))
        summaries = []
        for tool in ('restler', 'evomaster'):
            members = [i for i in z.infolist() if i.filename.endswith('/' + tool + '/http.jsonl')]
            if len(members) != 1 or members[0].file_size > 512 * 1024 * 1024:
                raise InputError('UNIQUE_BOUNDED_OBSERVER_MEMBER_REQUIRED')
            target = output / (tool + '.jsonl')
            with z.open(members[0]) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            req = {'schema_version': 'natchan-semantic-request/1',
                   'run': {'id': 'library-retrospective-' + tool, 'product': 'library', 'tool': tool,
                           'start_state': 'unknown'},
                   'contract': 'contract.json', 'knowledge': 'knowledge.json', 'freeze': 'freeze.json',
                   'evidence': {'format': 'observer-tool-jsonl', 'traffic': target.name}}
            request = output / (tool + '.request.json')
            write(request, req)
            result = natchan.run(request, output / (tool + '-analysis'))
            if result['exit_code']:
                raise InputError('LIBRARY_ANALYSIS_FAILED_SEE_RESULT')
            coverage = loads(read(output / (tool + '-analysis') / 'coverage.json'))
            findings = loads(read(output / (tool + '-analysis') / 'findings.json'))
            summaries.append({'tool': tool, 'member': members[0].filename,
                              'member_sha256': natchan.hash_file(target), 'member_bytes': target.stat().st_size,
                              'result': {k: result[k] for k in ('status', 'exit_code', 'exchanges')},
                              'classes': coverage['classes'], 'server_5xx': coverage['server_5xx'],
                              'ingestion': coverage['ingestion'], 'symptom_groups': findings['groups']})
    report = {'schema_version': 'natchan-library-retrospective/1', 'analyzer_version': natchan.VERSION,
              'archive_sha256': natchan.hash_file(archive), 'contract_sha256': natchan.hash_file(output / 'contract.json'),
              'evaluation': 'development_post_hoc_not_held_out',
              'oracle_and_producer_verdict_rows_used': False, 'new_sut_requests': 0,
              'seeded_bug_detection_or_native_tool_bug_credit_claimed': False, 'runs': summaries}
    write(output / 'retrospective-summary.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    try:
        validate(args.archive, args.output)
    except (InputError, OSError, zipfile.BadZipFile, KeyError) as e:
        print('LIBRARY_ACCEPTANCE_INPUT_OR_ANALYSIS_ERROR')
        return 2
    print('LIBRARY_RETROSPECTIVE_COMPLETE')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
