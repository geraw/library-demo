"""Neutral contract and unguided control-coverage pilot; no supplied sequences or bindings."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'campaign-v006'))
import pilot_v006 as baseline


def main(args):
    source=args.campaign.resolve()
    for name in ('openapi.json','sut_buggy_issta.py'):
        if not (source/name).is_file():raise RuntimeError('Missing source campaign input: '+name)
    root=source/('neutral-contract-v007-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
    root.mkdir()
    shutil.copy2(source/'sut_buggy_issta.py',root/'sut_buggy_issta.py')
    contract=json.loads((Path(__file__).parent/'library_openapi_v007.json').read_text())
    contract['servers']=[{'url':'http://127.0.0.1:23243'}]
    baseline.core.write(root/'openapi.json',contract)
    baseline.core.write(root/'contract-change.json',{
        'source_campaign':str(source),'source_contract_sha256':baseline.core.sha(source/'openapi.json'),
        'new_contract_sha256':baseline.core.sha(root/'openapi.json'),
        'sut_sha256':baseline.core.sha(root/'sut_buggy_issta.py'),
        'changes':['Neutral operation descriptions; no mutation thresholds',
                   'Flattened User, Book and Hold response schemas',
                   'Positive integer constraints','Explicit JSON error and deletion response schemas',
                   'Documented existing 400 responses for book detail and loan filters'],
        'guidance':'No links, annotations, shared identifier types, seeded resources or supplied test sequences',
        'phase':'Unguided control coverage; mutations disabled','seconds_per_tool':args.seconds})
    evo,restler=args.evomaster_jar,args.restler
    if args.previous_pilot:
        previous=json.loads((args.previous_pilot/'provenance.json').read_text())
        if baseline.core.sha(source/'sut_buggy_issta.py')!=previous['sut_sha256']:
            raise RuntimeError('Source SUT differs from previous pilot')
        evo=evo or Path(previous['evomaster_jar']);restler=restler or Path(previous['restler'])
    baseline.BUGS='none'
    baseline.SECONDS=args.seconds
    print('NEUTRAL_CAMPAIGN '+str(root),flush=True)
    try:
        baseline.main(argparse.Namespace(campaign=root,evomaster_jar=evo,restler=restler,
            tools=args.tools,previous_pilot=None,install_local_tools=args.install_local_tools))
    finally:
        # Report coverage only. This does not manufacture a sequence for either tool.
        reports={}
        for folder in root.glob('baselines-all-v006-*'):
            if not folder.is_dir():continue
            for tool in ('restler','evomaster'):
                log=folder/tool/'http.jsonl'
                if not log.is_file():continue
                counts={key:0 for key in ('loan_creations','hold_creations','loan_returns','hold_cancellations','observer_errors','verdicts')}
                with log.open(encoding='utf-8') as stream:
                    for line in stream:
                        row=json.loads(line)
                        if row['role']=='observer_error':counts['observer_errors']+=1
                        if row['role']=='verdict':counts['verdicts']+=1
                        if row['role']!='tool':continue
                        path=row['path'].split('?')[0]
                        if row['method']=='POST' and row['status']==201:
                            if path=='/loans':counts['loan_creations']+=1
                            if path=='/holds':counts['hold_creations']+=1
                        if row['method']=='DELETE' and row['status']==200:
                            if path.startswith('/loans/'):counts['loan_returns']+=1
                            if path.startswith('/holds/'):counts['hold_cancellations']+=1
                execution=folder/tool/'search-execution.json'
                outcome=json.loads(execution.read_text()) if execution.exists() else {}
                counts['coverage_ready']=all(counts[k]>0 for k in ('loan_creations','hold_creations','loan_returns','hold_cancellations')) and not counts['observer_errors'] and not counts['verdicts'] and outcome.get('exit_code')==0 and not outcome.get('watchdog_timeout',True)
                reports[tool]=counts
                print('CONTROL_COVERAGE '+tool+' '+json.dumps(counts),flush=True)
        baseline.core.write(root/'coverage-summary.json',reports)
        ready=bool(reports) and all(row['coverage_ready'] for row in reports.values())
        print('V007_CONTROL_COVERAGE_READY' if ready else 'V007_CONTROL_COVERAGE_INCOMPLETE',flush=True)
        archive=shutil.make_archive(str(root)+'-review','zip',root)
        print('V007_REVIEW_ZIP '+archive,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--previous-pilot',type=Path)
    parser.add_argument('--evomaster-jar',type=Path)
    parser.add_argument('--restler',type=Path)
    parser.add_argument('--tools',choices=['both','restler','evomaster'],default='both')
    parser.add_argument('--seconds',type=int,choices=range(30,301),default=60)
    parser.add_argument('--install-local-tools',action='store_true')
    main(parser.parse_args())
