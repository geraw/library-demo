// Story control-flow harness; this is not a native Provengo/Context lifecycle test.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const root = __dirname;
for (const filename of [
  path.join(root, "../provengo/spec/js/lib_stories.js"),
  path.join(root, "compact-model/spec/js/lib_stories.js")
]) {
  const registered = [], reads = [], removed = [
    {method: "DELETE", entity: "holds"},
    {method: "DELETE", entity: "loans"}
  ];
  const stop = {};
  let waits = 0;
  function Atomic() { this.getAndIncrement = () => 1; }
  const context = {
    COMPACT_SEED: 1,
    java: {util: {Random: function () {}, concurrent: {atomic: {AtomicInteger: Atomic}, ConcurrentHashMap: function () {}}}},
    ctx: {bthread: (name, query, body) => registered.push({name, query, body})},
    bthread() {},
    bp: {EventSet: (name, contains) => ({name, contains})},
    matchAnyHoldDeleted: () => ({contains: e => e.method === "DELETE" && e.entity === "holds"}),
    matchAnyLoanDeleted: () => ({contains: e => e.method === "DELETE" && e.entity === "loans"}),
    waitFor: eventSet => {
      assert.equal(reads.length, waits, "no read before a removal or duplicate read");
      for (const event of [
        {method: "GET", entity: "loans"},
        {method: "POST", entity: "holds"},
        {method: "DELETE", entity: "books"}
      ]) assert.equal(eventSet.contains(event), false);
      if (waits === removed.length) throw stop;
      assert.equal(eventSet.contains(removed[waits++]), true);
    },
    verifyLoanExists: (book, user) => reads.push([book, user])
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(filename, "utf8"), context, {filename});
  const story = registered.filter(s => s.name === "verifyActiveLoanAfterRelationshipRemoval");
  assert.equal(story.length, 1);
  assert.equal(story[0].query, "Loan.All");
  try { story[0].body({bookid: 7, userid: 3}); assert.fail("expected harness stop"); }
  catch (error) { if (error !== stop) throw error; }
  assert.deepEqual(reads, [[7, 3], [7, 3]]);
}
console.log("STORY_RECHECK_HARNESS_PASSED models=2 removals_per_loan=2");
