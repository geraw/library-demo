// Lightweight DSL adapter checks. These are not native Provengo runtime tests.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
let requests = [];
let threads = [];
const context = {
  RESTSession: function(url) { this.baseURL=url; this.defaultHeaders={}; this.defaultCallback={}; },
  bthread: (name, body) => threads.push({name, body}),
  sync: request => requests.push(request),
  bp: {Event: (name,data) => ({name,data})}
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'investigator_stories_v004.js'),'utf8'),context);
assert.strictEqual(threads.length,14);
for (const thread of threads) {
  const before = requests.length;
  thread.body();
  assert.strictEqual(requests.length,before+1); // One selection, no retry loop.
  for (const event of requests.at(-1).request) {
    assert(event.data.expectedResponseCodes.every(c=>c>=400 && c<500));
  }
}
if (process.argv[2]) {
  const actual = fs.readFileSync(process.argv[2],'utf8');
  const start = actual.indexOf('function requestOneOfDirect(');
  const end = actual.indexOf('// Claude: this shadows',start);
  assert(start>=0 && end>start);
  const adapter = {
    svc: {}, pvg:{fail:message=>{throw Error(message);}}, sync:x=>x,
    buildRestEvent:(session,method,url,v)=>({name:method,data:{expectedResponseCodes:v.expectedResponseCodes}})
  };
  vm.runInNewContext(actual.slice(start,end),adapter);
  const offered = adapter.requestOneOfDirect('post','/books',[
    {valid:true,expectedResponseCodes:[201]},
    {valid:false,expectedResponseCodes:[400]},
    {valid:true,expectedResponseCodes:[400]}
  ]).request;
  assert.strictEqual(offered.length,1);
  assert.strictEqual(offered[0].data.expectedResponseCodes[0],201);
}
console.log('PROFILE_ADAPTER_CHECKS_PASS');
