"""Bundle latest retained traces for independent replay; no SUT or oracle execution."""
import argparse,hashlib,json,zipfile
from pathlib import Path,PureWindowsPath


def collect(root,summary,contract,output,configuration):
    root=root.resolve();data=json.loads(summary.read_text(encoding='utf-8-sig'));selected={}
    for cell in data['cells']:
        if cell['configuration']!=configuration:continue
        parts=PureWindowsPath(cell['source']).parts
        if len(parts)<3 or '..' in parts or PureWindowsPath(cell['source']).is_absolute():raise ValueError('Unsafe source path')
        mutation=parts[-2]
        if mutation not in ('B1','B2','B4','none'):continue
        if mutation not in selected or cell['source']>selected[mutation]['source']:selected[mutation]=cell
    if not selected:raise ValueError('No matching retained traces')
    files=[]
    for cell in selected.values():
        rel=Path(*PureWindowsPath(cell['source']).parts);path=(root/rel).resolve()
        if not path.is_relative_to(root):raise ValueError('Source outside runs directory')
        if not path.is_file():raise ValueError('Raw trace missing: '+str(rel))
        files.append((path,str(rel).replace('\\','/')))
        request=path.parent/'natchan-request.json'
        if request.is_file():files.append((request,str(rel.parent/'natchan-request.json').replace('\\','/')))
    files.append((contract,'openapi.json'))
    if sum(p.stat().st_size for p,n in files)>384*1024*1024:raise ValueError('Selected evidence exceeds 384 MiB; split the source selection')
    manifest={'configuration':configuration,'selected_cells':list(selected.values()),'files':{},'new_SUT_requests':0}
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,name in files:
            raw=path.read_bytes();z.writestr(name,raw);manifest['files'][name]=hashlib.sha256(raw).hexdigest()
        z.writestr('evidence-manifest.json',json.dumps(manifest,indent=2))
    return {'output':str(output.resolve()),'size_bytes':output.stat().st_size,'mutations':sorted(selected)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs-root',type=Path,required=True);p.add_argument('--replay-summary',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--configuration',default='provengo-sample10')
    a=p.parse_args();print(json.dumps(collect(a.runs_root,a.replay_summary,a.contract,a.output,a.configuration)))
