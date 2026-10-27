"""Derive bounded analyzer metadata from OpenAPI plus a producer story IR; no SUT access."""
import argparse
import hashlib
import json
from pathlib import Path
import re


class Contract:
    def __init__(self, raw): self.raw=raw;self.paths=raw.get('paths',{})
    def resolve(self, value, depth=0):
        if not isinstance(value,dict) or depth>25:return {}
        if '$ref' in value:
            node=self.raw
            for k in value['$ref'].removeprefix('#/').split('/'):
                node=node.get(k.replace('~1','/').replace('~0','~'),{})
            return self.resolve(node,depth+1)
        if 'allOf' in value:
            out={k:v for k,v in value.items() if k!='allOf'};props={};required=[]
            for p in value['allOf']:
                x=self.resolve(p,depth+1);props.update(x.get('properties',{}));required+=x.get('required',[])
            out['properties']={**props,**out.get('properties',{})};out['required']=required+out.get('required',[]);return out
        for alt in ('oneOf','anyOf'):
            if alt in value:
                choices=[self.resolve(x,depth+1) for x in value[alt]]
                choices=[x for x in choices if x.get('type')!='null']
                if len(choices)==1:return choices[0]
        return value
    def props(self,s):return {k:self.resolve(v) for k,v in self.resolve(s).get('properties',{}).items()}
    def body(self,route,method):
        op=self.paths.get(route,{}).get(method,{})
        for ct,x in self.resolve(op.get('requestBody',{})).get('content',{}).items():
            if 'json' in ct:return self.resolve(x.get('schema',{}))
        for p in op.get('parameters',[]):
            p=self.resolve(p)
            if p.get('in')=='body':return self.resolve(p.get('schema',{}))
        return {}
    def response(self,route):
        for code,r in self.paths.get(route,{}).get('get',{}).get('responses',{}).items():
            if not str(code).startswith('2'):continue
            r=self.resolve(r)
            for ct,x in r.get('content',{}).items():
                if 'json' in ct:return self.resolve(x.get('schema',{}))
            if 'schema' in r:return self.resolve(r['schema'])
        return {}


def norm(s):return re.sub('[^a-z]','',s.lower())


def derive(raw,ir,product,contract_sha):
    C=Contract(raw);entities=ir['entities'];out_entities={}
    for name,e in entities.items():
        out_entities[name]={k:e.get(k) for k in ('path','detail','id_field','create_method','update','refs')}
    projections=[]
    for s in ir['stories']:
        if s.get('family')!='PROJ-NEST':continue
        route=s['key'].split(' ',1)[1]
        if route not in C.paths:continue
        response=C.response(route);array=response.get('type')=='array';places=[]
        used={s['owner']}
        for pl in s['places']:
            child=pl['child'];e=entities.get(child,{})
            if child in used or not e.get('create_method'):continue
            possible=[p for p in places if pl['at'].startswith(p['original_at']+'.') and any(r['target']==p['child'] and r['shape']=='scalar' for r in e.get('refs',[]))]
            parent=possible[-1] if possible else None;target=parent['child'] if parent else s['owner']
            refs=[r['field'] for r in e.get('refs',[]) if r['target']==target and r['shape']=='scalar']
            if len(refs)!=1:continue
            at=pl['at']
            if array and not at.startswith('$[]'):at='$[]'+at[1:]
            pat=parent['at'] if parent else '$'
            places.append(dict(at=at,original_at=pl['at'],child=child,parent_entity=target,parent_at=pat,reference_field=refs[0]))
            used.add(child)
        if places:projections.append(dict(view_template=route,owner=s['owner'],response_array=array,places=places))
    arithmetic=[]
    for name,e in entities.items():
        if not e.get('create_method'):continue
        props=C.props(C.body(e['path'],e['create_method']))
        opfield=None;operators={}
        for f,sch in props.items():
            if not sch.get('enum'):continue
            ops={}
            for symbol in sch['enum']:
                m=re.search(r'`'+re.escape(str(symbol))+r'`\s*-\s*([A-Za-z]+)',sch.get('description',''))
                if m:
                    op={'plus':'+','add':'+','increment':'+','minus':'-','subtract':'-','decrement':'-','replace':'=','set':'='}.get(m[1].lower())
                    if op:ops[str(symbol)]=op
            if set(ops.values())=={'+','-','='}:opfield=f;operators=ops;break
        iteration=next((f for f in props if 'iteration' in f.lower()),None)
        value=next((f for f in props if f.lower()=='value'),None)
        parents=[r for r in e.get('refs',[]) if r.get('required') and r['shape']=='scalar']
        if not opfield or not iteration or not value or len(parents)!=1:continue
        parent=parents[0]['target'];stem=re.sub('config$','',name)
        step=next((f for f in props if f.lower()=='step'),None)
        modes={}
        if step:
            for v in props[step].get('enum',[]):
                if str(v).lower().startswith('perc'):modes[str(v)]='percent'
                elif str(v).lower().startswith('abs') or str(v).lower()=='na':modes[str(v)]='absolute'
        for route in C.paths:
            response=C.response(route);top=C.resolve(response.get('items',{})) if response.get('type')=='array' else response
            if iteration not in C.props(top):continue
            def find(schema,path,depth=0):
                if depth>8:return None
                for f,sch in C.props(schema).items():
                    if sch.get('type')!='array':continue
                    item=C.resolve(sch.get('items',{}));p=C.props(item);key=next((k for k in p if norm(k)==norm(parent)+'id'),None);val=next((k for k in p if norm(k)==stem),None)
                    if key and val:return path+'.'+f+'[]',key,val
                    found=find(item,path+'.'+f+'[]',depth+1)
                    if found:return found
                return None
            hit=find(top,'$')
            if hit:
                arithmetic.append(dict(entity=name,parent_entity=parent,parent_field=parents[0]['field'],operator_field=opfield,operators=operators,iteration_field=iteration,value_field=value,step_field=step,modes=modes,view_template=route,items_at=hit[0],item_parent_field=hit[1],output_field=hit[2],value_type=props[value].get('type'),rounding={'mode':'unspecified'}))
    return dict(schema_version='natchan-story-semantics/1',product=product,contract_sha256=contract_sha,
        semantics_status='contract-derived relations and explicitly configured metamorphic hypotheses; not a product specification',entities=out_entities,projections=projections,arithmetic=arithmetic)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--contract',type=Path,required=True);p.add_argument('--derived-stories',type=Path,required=True);p.add_argument('--product',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--display-rounding-steps',default='',help='Explicit tolerated display quantization steps; never inferred as a contract guarantee');a=p.parse_args()
    raw=a.contract.read_bytes();result=derive(json.loads(raw),json.loads(a.derived_stories.read_bytes()),a.product,hashlib.sha256(raw).hexdigest())
    result['derivation_sources']={'contract_sha256':result['contract_sha256'],'derived_stories_sha256':hashlib.sha256(a.derived_stories.read_bytes()).hexdigest()}
    if a.display_rounding_steps:
        steps=[float(x) for x in a.display_rounding_steps.split(',')]
        if any(x<=0 for x in steps):raise SystemExit('Display rounding steps must be positive')
        for rule in result['arithmetic']:rule['rounding']['display_steps']=steps
        result['rounding_policy_source']='Explicit tolerated producer display-rounding policy, not a contract guarantee; compatible discrepancies stay observations.'
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
