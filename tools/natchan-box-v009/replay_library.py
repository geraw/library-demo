"""Reanalyze existing Library traces with fresh knowledge, without SUT requests.
Recorder declarations are reused only from that cell's natchan-request.json.
Original traces, requests, baselines and freezes are never overwritten.
"""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import natchan
from common import VERSION,digest,write
CONFIGURATIONS=('evomaster','restler','provengo-sample10','provengo-java')


def run(runs_root,contract,output):
    runs_root=runs_root.resolve();contract=contract.resolve();output=output.resolve()
    if not runs_root.is_dir() or not contract.is_file():raise ValueError('Runs directory or contract missing')
    if output.exists():raise ValueError('Use a new output directory')
    paths=sorted(runs_root.rglob('http.jsonl'))
    output.mkdir(parents=True)
    knowledge=output/'knowledge.json';freeze=output/'freeze.json'
    write(knowledge,natchan.contract(contract));write(freeze,natchan.make_freeze(contract,knowledge))
    cells=[]
    for i,path in enumerate(paths,1):
        relative=path.relative_to(runs_root)
        configurations=[c for c in CONFIGURATIONS if c in relative.parts]
        if len(configurations)!=1:continue
        cell=output/f'cell-{i:04d}';cell.mkdir()
        capture={};old=path.parent/'natchan-request.json'
        if old.is_file():
            declaration=json.loads(old.read_text(encoding='utf-8-sig')).get('evidence',{}).get('capture',{})
            capture={k:declaration[k] for k in ('complete','exclusive','ordering') if k in declaration}
        request={'schema_version':'natchan-semantic-request/1','run':{'id':'offline-replay','product':'captured-api','tool':'raw-http','start_state':'unknown'},
                 'contract':str(contract),'knowledge':str(knowledge),'freeze':str(freeze),
                 'evidence':{'format':'observer-tool-jsonl','traffic':str(path),'capture':capture}}
        rp=cell/'request.json';write(rp,request)
        record={'source':str(relative),'configuration':configurations[0],'capture_declaration_source':str(old.relative_to(runs_root)) if old.is_file() else None,'output':cell.name}
        try:
            result=natchan.run(rp,cell/'analysis');record['result']=result
        except Exception as exc:record['error']=type(exc).__name__+': '+str(exc)
        cells.append(record)
        print('REANALYZED',relative,record.get('result',{}).get('status','ERROR'),flush=True)
    coverage={c:{'raw_trace_cells':sum(x['configuration']==c for x in cells)} for c in CONFIGURATIONS}
    missing=[c for c,v in coverage.items() if not v['raw_trace_cells']]
    report={'version':VERSION,'status':'PARTIAL' if missing or any('error' in c or c.get('result',{}).get('exit_code',1)!=0 for c in cells) else 'COMPLETE',
            'new_SUT_requests':0,'resampled':False,'missing_raw_configurations':missing,'configuration_coverage':coverage,'cells':cells,
            'scope':'All retained http.jsonl cells; no claim of complete mutation coverage or recovery of discarded traces'}
    write(output/'replay-summary.json',report);return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs-root',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();out=a.output or a.runs_root.parent/('analyzer-replay-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    result=run(a.runs_root,a.contract,out);print('REPLAY_SUMMARY',out/'replay-summary.json')
    raise SystemExit(1 if any('error' in c or c.get('result',{}).get('exit_code',1)!=0 for c in result['cells']) else 0)
