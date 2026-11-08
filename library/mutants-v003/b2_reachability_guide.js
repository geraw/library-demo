// Diagnostic only. This constrains the existing model, never requests events.
// It is not loaded in random campaigns and must not be counted as random discovery.
// Roles bind to whichever logical IDs the original creation stories offer.
// The small plan is embedded to avoid external file IO in the Provengo runtime.
var B2_REACHABILITY_PLAN = [
  {
    "method": "POST",
    "entity": "users",
    "slot": 0
  },
  {
    "method": "POST",
    "entity": "users",
    "slot": 1
  },
  {
    "method": "POST",
    "entity": "users",
    "slot": 2
  },
  {
    "method": "POST",
    "entity": "books",
    "slot": 0
  },
  {
    "method": "POST",
    "entity": "books",
    "slot": 1
  },
  {
    "method": "POST",
    "entity": "books",
    "slot": 2
  },
  {
    "method": "POST",
    "entity": "loans",
    "user": 0,
    "book": 0
  },
  {
    "method": "POST",
    "entity": "holds",
    "user": 1,
    "book": 0,
    "slot": 0
  },
  {
    "method": "DELETE",
    "entity": "loans",
    "user": 0,
    "book": 0
  },
  {
    "method": "POST",
    "entity": "loans",
    "user": 0,
    "book": 1
  },
  {
    "method": "POST",
    "entity": "loans",
    "user": 1,
    "book": 0
  },
  {
    "method": "POST",
    "entity": "holds",
    "user": 2,
    "book": 1,
    "slot": 1
  },
  {
    "method": "DELETE",
    "entity": "loans",
    "user": 0,
    "book": 1
  },
  {
    "method": "POST",
    "entity": "loans",
    "user": 0,
    "book": 2
  },
  {
    "method": "POST",
    "entity": "loans",
    "user": 2,
    "book": 1
  },
  {
    "method": "POST",
    "entity": "holds",
    "user": 1,
    "book": 2,
    "slot": 2
  },
  {
    "method": "DELETE",
    "entity": "loans",
    "user": 0,
    "book": 2
  },
  {
    "method": "DELETE",
    "entity": "loans",
    "user": 2,
    "book": 1
  },
  {
    "method": "POST",
    "entity": "loans",
    "user": 0,
    "book": 1
  },
  {
    "method": "DELETE",
    "entity": "loans",
    "user": 1,
    "book": 0
  },
  {
    "method": "POST",
    "entity": "loans",
    "user": 1,
    "book": 2
  },
  {
    "method": "DELETE",
    "entity": "holds",
    "slot": 0
  },
  {
    "method": "DELETE",
    "entity": "books",
    "slot": 0
  },
  {
    "method": "GET",
    "entity": "loans",
    "user": 0,
    "book": 1
  }
];

bthread("B2 reachability diagnostic guide",function(){
  var users=[],books=[],holds=[];
  function equalRef(value,logical,prefix){
    return String(value)===String(logical) || String(value)==="@{"+prefix+logical+"}";
  }
  var any=bp.EventSet("Any diagnostic event",function(){return true;});
  for(var index=0;index<B2_REACHABILITY_PLAN.length;index++){
    var step=B2_REACHABILITY_PLAN[index];
    function matches(event){
      if(event.name!==step.method)return false;
      var codes=getExpectedResponseCodes(event);
      if(!codes.length || !codes.every(function(c){return c>=200&&c<300;}))return false;
      var entity=getRequestPath(event).split('/')[1];if(entity!==step.entity)return false;
      var d=extractEventData(event);
      if(step.method==='POST'&&(entity==='users'||entity==='books'))return true;
      if(entity==='loans')return equalRef(d.userId,users[step.user],'USER')&&equalRef(d.bookId,books[step.book],'BOOK');
      if(step.method==='POST'&&entity==='holds')return equalRef(d.userId,users[step.user],'USER')&&equalRef(d.bookId,books[step.book],'BOOK');
      if(entity==='holds')return equalRef(d.id,holds[step.slot],'HOLD');
      if(entity==='books')return equalRef(d.id,books[step.slot],'BOOK');
      return false;
    }
    var wrong=bp.EventSet('Not B2 diagnostic step '+(index+1),function(event){return !matches(event);});
    var event=sync({waitFor:any,block:wrong});var data=extractEventData(event);
    if(step.method==='POST'){
      if(step.entity==='users')users[step.slot]=data.id;
      if(step.entity==='books')books[step.slot]=data.id;
      if(step.entity==='holds')holds[step.slot]=data.id;
    }
  }
  bp.log.info('B2_GUIDE_COMPLETED');
  // Finish the diagnostic at the witness; this story offers no request itself.
  sync({waitFor:any,block:any});
});
