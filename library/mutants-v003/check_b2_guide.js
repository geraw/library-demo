// Selector harness only: verifies the diagnostic blocks/offers contract, not native reachability.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
const root=__dirname,plan=JSON.parse(fs.readFileSync(path.join(root,'b2-plan.json'),'utf8'));
const events=[];let loanNumber=0;
for(const s of plan){
 const parameters={},u=10+s.user,b=20+s.book,slot=s.entity==='users'?10+s.slot:s.entity==='books'?20+s.slot:30+s.slot;
 let url='/'+s.entity,body;
 if(s.method==='POST'&&(s.entity==='users'||s.entity==='books')){parameters.id=slot;body=s.entity==='users'?{name:'U'}:{title:'B'};}
 else if(s.method==='POST'){
  parameters.userId=u;parameters.bookId=b;body={userId:'@{USER'+u+'}',bookId:'@{BOOK'+b+'}'};
  if(s.entity==='loans')parameters.loanNumber=++loanNumber;else parameters.id=slot;
 }else if(s.method==='DELETE'&&s.entity==='loans'){
  parameters.userId=u;parameters.bookId=b;url+='/@{USER'+u+'}/@{BOOK'+b+'}';
 }else if(s.method==='GET') {parameters.userId='@{USER'+u+'}';parameters.bookId='@{BOOK'+b+'}';}
 else {parameters.id=slot;url+='/@{'+(s.entity==='books'?'BOOK':'HOLD')+slot+'}';}
 const data={url:'http://127.0.0.1:23600'+url,parameters,expectedResponseCodes:[s.method==='POST'?201:200]};
 if(body)data.body=JSON.stringify(body);events.push({name:s.method,data});
}
let guide,step=0,done=false;const stop={};
const context={bp:{EventSet:(name,pred)=>({contains:pred}),log:{info:msg=>{if(msg==='B2_GUIDE_COMPLETED')done=true;}}},
 bthread:(name,body)=>guide=body,
 sync:arg=>{
  if(step===events.length){assert(done);assert(arg.block.contains({name:'GET',data:{}}));throw stop;}
  const e=events[step++];assert(arg.waitFor.contains(e));assert(!arg.block.contains(e),'expected step blocked: '+step);
  assert(arg.block.contains({name:'POST',data:{expectedResponseCodes:[400],url:'/users'}}));return e;
 },getExpectedResponseCodes:e=>e.data.expectedResponseCodes,
 getRequestPath:e=>e.data.url.replace(/^https?:\/\/[^/]+/,''),
 extractEventData:e=>e.data.parameters};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'b2_reachability_guide.js'),'utf8'),context);
try{guide();assert.fail('guide did not stop');}catch(e){if(e!==stop)throw e;}
assert.equal(step,24);assert(done);
if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify([events],null,2));
console.log('B2_GUIDE_SELECTOR_HARNESS_PASSED steps=24 native_scheduler=false');
