// ...is silently replaced by a same-named function in a file loaded later (files load in name
// order). Nothing warns; the first file's callers now run the second file's code.
//
//   expected by the author of a-helpers.js: "a: 1"
//   actual:                                 "b: 1"
//
// Run: provengo run --dry .
function label(x) { return "b: " + x; }

bthread("main", function () {
  request(Event(label(1)));
});
