// Transport/offer harness only: does not emulate the native scheduler.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=path.join(__dirname,'full-model'), selected=[];let pickNegative=false;
function Atomic(){this.n=1;this.getAndIncrement=()=>this.n++;}
const context={COMPACT_SEED:1,java:{util:{Random:function(){this.nextInt=()=>123;},concurrent:{atomic:{AtomicInteger:Atomic}}}},
 bp:{Event:(name,data)=>({name,data}),EventSet:function(name,pred){this.contains=pred;},log:{error:m=>{throw Error(m);}}},
 ctx:{registerEffect(){},registerQuery(){},bthread(){}},bthread(){},
 sync:arg=>{const offered=Array.isArray(arg.request)?arg.request:[arg.request];assert(offered.length);let e;
  if(pickNegative){e=offered.find(e=>e.data.expectedResponseCodes.includes(400));assert(e,'negative alternatives were removed');pickNegative=false;}
  else e=offered.find(e=>e.data.model?.valid)||offered[0];selected.push(e);return e;}};
vm.createContext(context);
for(const f of ['lib/utils.js','spec/js/dal.js','spec/js/interfaces.library.js','spec/js/lib_stories.js'])vm.runInContext(fs.readFileSync(path.join(root,f),'utf8'),context,{filename:f});
pickNegative=true;vm.runInContext("createUser(1,'A');",context);
pickNegative=true;vm.runInContext("createBook(1,'X');",context);
vm.runInContext("tryToUpdateUserAndExpectError(1,{name:'B'},405);verifyMissingEntityReadIsRejected('Book',999,'/books/999');",context);
assert.deepEqual(selected.map(e=>e.data.expectedResponseCodes[0]),[400,201,400,201,405,404]);
for(const e of selected){assert(!('callback'in e.data));assert(!('lib'in e.data));}
if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify([selected],null,2));
console.log('FULL_ADAPTER_HARNESS_PASSED negative_alternatives=true events='+selected.length);
