// Interface-adapter smoke only. This does not emulate Provengo scheduling/Context.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=path.join(__dirname,'compact-model');
const selected=[];
function Atomic(){this.n=1;this.getAndIncrement=()=>this.n++;}
const context={COMPACT_SEED:1,java:{util:{Random:function(){this.nextInt=()=>123;},concurrent:{atomic:{AtomicInteger:Atomic}}}},
  bp:{Event:(name,data)=>({name,data}),EventSet:function(name,predicate){this.name=name;this.contains=predicate;},log:{error:m=>{throw Error(m);}}},
  ctx:{registerEffect(){},registerQuery(){},bthread(){}},bthread(){},
  sync:arg=>{const e=Array.isArray(arg.request)?arg.request[0]:arg.request;assert(e);selected.push(e);return e;}};
vm.createContext(context);
for(const f of ['lib/utils.js','spec/js/dal.js','spec/js/interfaces.library.js','spec/js/lib_stories.js'])vm.runInContext(fs.readFileSync(path.join(root,f),'utf8'),context,{filename:f});
vm.runInContext(`createUser(1,'A');createBook(1,'X');createLoan(1,1,1);createHold(1,1,1);
verifyBookExists(1);verifyBookDetailExists(1);verifyLoanExists(1,1);verifyHoldExists(1);
deleteLoan(1,1,1);deleteHold(1,1,1);deleteBook(1);deleteUser(1);
verifyMissingEntityReadIsRejected('Book',1,'/books/@{BOOK1}');
tryToCreateBookWithBadParametersAndExpectError(1);tryToCreateLoanAndExpectError(1,1,1);`,context);
assert.equal(selected.length,13);
function plain(v){assert.notEqual(typeof v,'function');if(v && typeof v==='object')for(const x of Object.values(v))plain(x);}
for(const e of selected){plain(e.data);assert(!('callback' in e.data));assert(e.data.expectedResponseCodes.every(c=>[200,201,204,404].includes(c)));assert(!JSON.stringify(e).includes('invalid -'));}
console.log('COMPACT_ADAPTER_SMOKE_PASSED events='+selected.length);

if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify([selected],null,2));
