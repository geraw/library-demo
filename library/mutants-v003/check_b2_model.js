// Evaluate the real DAL queries along the witness. Not a Context scheduler emulator.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=__dirname, entities=new Map(), queries=new Map();
const context={ctx:{
  Entity:(id,type,data)=>Object.assign({id,type},data),
  insertEntity:e=>entities.set(e.id,e),removeEntity:id=>entities.delete(id),
  registerQuery:(name,pred)=>queries.set(name,pred),registerEffect(){},
  runQuery:name=>[...entities.values()].filter(queries.get(name))
}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'full-model/spec/js/dal.js'),'utf8'),context);
const plan=JSON.parse(fs.readFileSync(path.join(root,'b2-plan.json'),'utf8'));
const query=(name,data)=>queries.get(name)(data);
const holdsMade=new Set();let loanNumber=0;let pendingRead=new Set();
for(const [i,s] of plan.entries()){
 const u=s.user+1,b=s.book+1;
 if(s.method==='POST'&&s.entity==='users')context.createUserEntity({id:s.slot+1,name:'U'});
 else if(s.method==='POST'&&s.entity==='books')context.createBookEntity({id:s.slot+1,title:'B'});
 else if(s.method==='POST'&&s.entity==='loans'){
  const pair=context.ctx.runQuery('UserBook.All').find(e=>e.userid===u&&e.bookid===b);
  assert(pair&&query('UserBook.CanCreateLoan',pair),'loan unavailable at '+(i+1));
  context.createLoanEntity({userId:u,bookId:b,loanNumber:++loanNumber});pendingRead.add(u+':'+b);
 }else if(s.method==='POST'&&s.entity==='holds'){
  const pair=context.ctx.runQuery('UserBook.All').find(e=>e.userid===u&&e.bookid===b);
  assert(pair&&query('UserBook.CanCreateHold',pair)&&!holdsMade.has(u+':'+b),'hold story unavailable');
  holdsMade.add(u+':'+b);context.createHoldEntity({id:s.slot+1,userId:u,bookId:b});
 }else if(s.method==='DELETE'&&s.entity==='loans'){
  assert(context.ctx.runQuery('Loan.All').some(e=>e.userid===u&&e.bookid===b));
  context.deleteLoanEntity({userId:u,bookId:b});pendingRead.delete(u+':'+b);
  for(const l of context.ctx.runQuery('Loan.All'))pendingRead.add(l.userid+':'+l.bookid);
 }else if(s.method==='DELETE'&&s.entity==='holds'){
  assert(context.ctx.runQuery('Hold.All').some(e=>e.holdid===s.slot+1));context.deleteHoldEntity({id:s.slot+1});
  for(const l of context.ctx.runQuery('Loan.All'))pendingRead.add(l.userid+':'+l.bookid);
 }else if(s.method==='DELETE'&&s.entity==='books'){
  const book=context.ctx.runQuery('Book.All').find(e=>e.bookid===s.slot+1);
  assert(book&&query('Book.CanDelete',book));context.deleteBookEntity({id:s.slot+1});
 }else if(s.method==='GET'&&s.entity==='loans'){
  assert(context.ctx.runQuery('Loan.All').some(e=>e.userid===u&&e.bookid===b));
  assert(pendingRead.has(u+':'+b),'no verification story available');
 }else assert.fail('unhandled step');
}
console.log('B2_DAL_PREREQUISITES_PASSED steps='+plan.length+' users=3 books=3 native_scheduler=false');
