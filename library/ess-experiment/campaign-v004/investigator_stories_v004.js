//@provengo summon rest
// Investigator profile: finite negative-operation families. One choice per family.
const investigatorService = new RESTSession("http://127.0.0.1:23243", "investigator-v004", {
  headers: {"Content-Type": "application/json"}
});
function investigate(name, method, variants, expected) {
  bthread("investigator." + name, function () {
    var events = variants.map(function (variant) {
      var data = {
        lib: "REST", method: method, url: investigatorService.baseURL + variant.path,
        headers: investigatorService.defaultHeaders, parameters: {},
        expectedResponseCodes: [expected], callback: investigatorService.defaultCallback,
        model: {name: name + ": " + variant.label, valid: false}
      };
      if (variant.body !== undefined) data.body = JSON.stringify(variant.body);
      return bp.Event(method, data);
    });
    sync({request: events}); // Exactly one operation, no retry-until-valid loop.
  });
}
function bodies(path, cases) {
  return cases.map(function (body) {return {path: path, body: body, label: JSON.stringify(body)};});
}
investigate("invalidReader", "POST", bodies("/users", [{}, {name:null}, {name:123}, {name:""}]), 400);
investigate("invalidBook", "POST", bodies("/books", [{}, {title:null}, {title:123}, {title:""}]), 400);
var invalidRelations = [{}, {userId:0,bookId:1}, {userId:1,bookId:0},
  {userId:null,bookId:1}, {userId:1,bookId:"bad-id"}, {userId:true,bookId:false}];
investigate("invalidLoan", "POST", bodies("/loans", invalidRelations), 400);
investigate("invalidReservation", "POST", bodies("/holds", invalidRelations), 400);
// Fixed out-of-range IDs: these tests start empty and never create resources.
["users", "books", "holds"].forEach(function (resource) {
  investigate("missingDelete." + resource, "DELETE", [
    {path:"/" + resource + "/1000000001", label:"unknown ID"}], 404);
  investigate("invalidDelete." + resource, "DELETE", ["0", "-1", "bad-id"].map(function (id) {
    return {path:"/" + resource + "/" + id, label:id};
  }), 400);
});
investigate("missingLoanDelete", "DELETE", [
  {path:"/loans/1000000001/1000000001", label:"unknown pair"}], 404);
investigate("invalidLoanDelete", "DELETE", [
  {path:"/loans/0/1", label:"zero reader"},
  {path:"/loans/1/bad-id", label:"invalid book"}], 400);
investigate("invalidBookRead", "GET", [
  {path:"/books/0", label:"zero ID"}, {path:"/books/bad-id", label:"invalid ID"}], 400);
investigate("missingBookRead", "GET", [
  {path:"/books/1000000001", label:"unknown book"}], 404);
