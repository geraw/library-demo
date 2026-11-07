"""Check actual handoff files, catalogs, tests and public CLI; never execute a SUT."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from classifier import load_catalogs

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


def verify():
    required=['classifier.py','normalize.py','review_mealie.py','catalog.schema.json','observations.schema.json',
              'BUG_FORMAT.md','TAXONOMY.json','HANDOFF_PROMPT_HE.md','Invoke-Natchan-Classify-v003.ps1',
              'examples/bug-template.json','examples/jsonl-gateway-mapping.json','examples/synthetic-vikunja-pair.json']
    missing=[name for name in required if not (ROOT/name).is_file()]
    if missing:raise ValueError('Missing handoff files: '+str(missing))
    entries,_=load_catalogs(ROOT/'catalogs');by_id={e['id']:e for e in entries}
    taxonomy=json.loads((ROOT/'TAXONOMY.json').read_text())
    for family in taxonomy['families']:
        for id in family['catalog_ids']:
            if id not in by_id:raise ValueError('Taxonomy references missing rule '+id)
    commands=[]
    def run(argv):
        p=subprocess.run(argv,cwd=REPO,capture_output=True,text=True)
        commands.append(dict(command=argv,exit_code=p.returncode,output=p.stdout+p.stderr))
        if p.returncode:raise ValueError('Command failed: '+str(argv)+'\n'+p.stdout+p.stderr)
    for tests in ['tools/natchan-v002/tests','tools/natchan-v003/tests']:
        run([sys.executable,'-m','unittest','discover','-s',tests,'-q'])
    for script in ['classifier.py','normalize.py','review_mealie.py']:
        run([sys.executable,str(ROOT/script),'--help'])
    with tempfile.TemporaryDirectory() as directory:
        output=Path(directory)/'classification.json'
        run([sys.executable,str(ROOT/'classifier.py'),'--input',str(ROOT/'examples/synthetic-vikunja-pair.json'),'--output',str(output)])
        report=json.loads(output.read_text())
        if not any(a.get('catalog_id')=='GEN-CREATE-UPDATE-PARTIAL-COMPOUND' for a in report['assessments']):
            raise ValueError('Compound CLI smoke failed')
        if not output.with_suffix('.md').is_file():raise ValueError('Missing Markdown companion')
        raw=Path(directory)/'raw.jsonl';raw.write_text('{"status":500,"operation":"update","entity":"tasks"}\n')
        normalized=Path(directory)/'normalized.json'
        run([sys.executable,str(ROOT/'normalize.py'),'--input',str(raw),'--mapping',str(ROOT/'examples/jsonl-gateway-mapping.json'),'--output',str(normalized)])
        result=Path(directory)/'normalized-classification.json'
        run([sys.executable,str(ROOT/'classifier.py'),'--input',str(normalized),'--output',str(result)])
        if not any(a.get('catalog_id')=='GEN-SERVER_ERROR' for a in json.loads(result.read_text())['assessments']):
            raise ValueError('Normalized JSONL CLI smoke failed')
        powershell='not_executed: pwsh unavailable; run wrapper on target Windows machine'
        if shutil.which('pwsh'):
            run(['pwsh','-NoProfile','-File',str(ROOT/'Invoke-Natchan-Classify-v003.ps1'),'-InputPath',str(ROOT/'examples/synthetic-vikunja-pair.json'),'-OutputPath',str(Path(directory)/'ps.json'),'-Python',sys.executable])
            powershell='executed_successfully'
    return dict(schema_version=1,status='PASS',required_files_checked=required,
                taxonomy_family_count=len(taxonomy['families']),catalog_entry_count=len(entries),
                draft_ids=[e['id'] for e in entries if e['status']=='draft'],powershell=powershell,
                commands=commands,note='Synthetic CLI verification and unit tests; no real Vikunja/Gitea execution')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    if args.output.exists():parser.error('Output exists')
    report=verify();args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:json.dump(report,target,indent=2);target.write('\n')
    print('NATCHAN_HANDOFF_VERIFIED '+str(args.output.resolve()))
