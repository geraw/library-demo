"""Offline analysis into a NEW directory; never rewrite original run evidence.
Capture declarations must come from the recorder, not from a desired outcome.
"""
import argparse,json
from pathlib import Path
import natchan
from common import write


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--contract',type=Path,required=True)
    p.add_argument('--traffic',type=Path,required=True)
    p.add_argument('--format',choices=['http-jsonl','journal-jsonl','observer-tool-jsonl','har'],required=True)
    p.add_argument('--capture',type=Path,help='Existing recorder declaration JSON: complete, exclusive, ordering')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise SystemExit('Output must be a new directory')
    if not a.contract.is_file() or not a.traffic.is_file():raise SystemExit('Input file missing')
    capture=json.loads(a.capture.read_text(encoding='utf-8-sig')) if a.capture else {}
    a.output.mkdir(parents=True)
    contract=a.contract.resolve();knowledge=(a.output/'knowledge.json').resolve();freeze=(a.output/'freeze.json').resolve()
    write(knowledge,natchan.contract(contract));write(freeze,natchan.make_freeze(contract,knowledge))
    request={'schema_version':'natchan-semantic-request/1','run':{'id':'offline-replay','product':'captured-api','tool':'raw-http','start_state':'unknown'},
             'contract':str(contract),'knowledge':str(knowledge),'freeze':str(freeze),
             'evidence':{'format':a.format,'traffic':str(a.traffic.resolve()),'capture':capture}}
    rp=a.output/'request.json';write(rp,request)
    result=natchan.run(rp,a.output/'analysis')
    print(json.dumps(result))
    raise SystemExit(result['exit_code'])

if __name__=='__main__':main()
