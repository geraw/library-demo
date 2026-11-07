"""Declarative offline gateway for previously unseen JSON/JSONL layouts."""
import argparse
import hashlib
import json
from pathlib import Path
from classifier import get, MISSING


def convert(path,mapping):
    source_path=Path(path)
    raw=Path(path).read_bytes();text=raw.decode('utf-8-sig')
    if mapping['format']=='jsonl':
        records=[]
        for line_no,line in enumerate(text.splitlines(),1):
            if line.strip():records.append((line_no,json.loads(line)))
    elif mapping['format']=='json':
        document=json.loads(text);values=get(document,mapping['records_path']) if mapping.get('records_path') else document
        if not isinstance(values,list):raise ValueError('Mapped JSON records must be an array')
        records=list(enumerate(values,1))
    else:raise ValueError('format must be json or jsonl')
    digest=hashlib.sha256(raw).hexdigest();observations=[]
    for position,record in records:
        if not isinstance(record,dict):raise ValueError('Record is not an object')
        obs=dict(mapping.get('defaults',{}))
        for target,path in mapping['fields'].items():
            value=get(record,path)
            if value is not MISSING:obs[target]=value
        obs['id']=mapping.get('id_prefix','record')+'-'+str(position)
        obs['source']=dict(filename=source_path.name,sha256=digest,record=position)
        obs['fact_basis']='imported_oracle'
        observations.append(obs)
    return dict(schema_version='natchan-observations/1',source=dict(filename=source_path.name,sha256=digest),observations=observations)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--mapping',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    mapping=json.loads(args.mapping.read_text(encoding='utf-8-sig'))
    result=convert(args.input,mapping)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2);target.write('\n')
    print('NATCHAN_OBSERVATIONS '+str(args.output.resolve()))
