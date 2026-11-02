// Standalone verification harness for library/provengo/meta-spec/ensemble-code.js's
// combinedCoverageFunction()/coverageBreakdown()/COVERAGE_WEIGHTS, run via plain Node (not the
// Provengo CLI), so expected scores can be hand-computed and asserted exactly. Mirrors
// ensemble-code.test.js's harness style; kept as a separate file so that file (already
// validated, covering rankingFunction/parameterCoverageFunction) is never touched here.
// Run with: node combined-coverage.test.js
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const SRC = path.join(__dirname, "..", "ensemble-code.js");

// NUMBER_OF_USERS/NUMBER_OF_BOOKS are real globals lib_stories.js declares in the live Provengo
// run - stubbed here since this harness loads ensemble-code.js standalone, without lib_stories.js.
const sandbox = { console, NUMBER_OF_USERS: 4, NUMBER_OF_BOOKS: 4 };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox, { filename: SRC });

let pass = 0, fail = 0;
function assertEqual(actual, expected, label) {
  const ok = Math.abs(actual - expected) < 1e-9;
  console.log((ok ? "PASS" : "FAIL") + " - " + label + " (expected " + expected + ", got " + actual + ")");
  if (ok) pass++; else fail++;
}
function assertTrue(cond, label) {
  console.log((cond ? "PASS" : "FAIL") + " - " + label);
  if (cond) pass++; else fail++;
}
function assertThrows(fn, label) {
  let threw = false;
  try { fn(); } catch (e) { threw = true; }
  console.log((threw ? "PASS" : "FAIL") + " - " + label);
  if (threw) pass++; else fail++;
}

// Same event shapes as ensemble-code.test.js's helpers (not imported from there, to keep this
// file independent of that one; kept byte-for-byte equivalent on purpose).
function stateFeatureEvent(name) {
  return { name: "marker: " + name, data: { lib: "Ctrl", verb: "marker", value: name, eventPriority: 1010 } };
}
function restEvent(verb, url, parameters) {
  return { name: verb, data: { lib: "REST", method: verb, url: "http://localhost:23242" + url, parameters } };
}
function createEvent(type, userId, bookId) {
  const label = type === "loan" ? "Loan" : "Hold";
  const url = type === "loan" ? "/loans" : "/holds";
  return restEvent("POST", url, { description: "Create: " + label + " " + userId + "/" + bookId, userId: userId, bookId: bookId });
}

const ALL_STATE_FEATURES = ["BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE", "HOLD_WITHOUT_LOAN", "MULTI_USER_BOOK_RELATIONS", "USER_WITH_TWO_BOOKS"];

function allPairs(type) {
  const events = [];
  for (let u = 1; u <= 4; u++)
    for (let b = 1; b <= 4; b++)
      events.push(createEvent(type, u, b));
  return events;
}

// --- Test A: empty ensemble --------------------------------------------------------------------
{
  const r = sandbox.coverageBreakdown([]);
  assertEqual(r.state, 0, "A: empty ensemble -> state 0");
  assertEqual(r.loan, 0, "A: empty ensemble -> loan 0");
  assertEqual(r.hold, 0, "A: empty ensemble -> hold 0");
  assertEqual(r.combined, 0, "A: empty ensemble -> combined 0");
  assertEqual(sandbox.combinedCoverageFunction([]), 0, "A: combinedCoverageFunction([]) -> 0");
}

// --- Test B: complete coverage -----------------------------------------------------------------
{
  const trace = ALL_STATE_FEATURES.map(stateFeatureEvent).concat(allPairs("loan")).concat(allPairs("hold"));
  const r = sandbox.coverageBreakdown([trace]);
  assertEqual(r.state, 1, "B: all 6 state features -> state 1");
  assertEqual(r.loan, 1, "B: all 16 loan pairs -> loan 1");
  assertEqual(r.hold, 1, "B: all 16 hold pairs -> hold 1");
  assertEqual(r.combined, 100, "B: full coverage -> combined 100");
}

// --- Test C: partial coverage, exact value from the task spec ---------------------------------
{
  // 3/6 state features, 4/16 loan pairs, 8/16 hold pairs.
  const stateEvents = ["BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE"].map(stateFeatureEvent);
  const loanEvents = [[1, 1], [1, 2], [2, 1], [2, 2]].map(function (p) { return createEvent("loan", p[0], p[1]); });
  const holdEvents = [[1, 1], [1, 2], [1, 3], [1, 4], [2, 1], [2, 2], [2, 3], [2, 4]].map(function (p) { return createEvent("hold", p[0], p[1]); });
  const trace = stateEvents.concat(loanEvents).concat(holdEvents);

  const r = sandbox.coverageBreakdown([trace]);
  assertEqual(r.state, 0.5, "C: 3/6 state features -> state 0.5");
  assertEqual(r.loan, 0.25, "C: 4/16 loan pairs -> loan 0.25");
  assertEqual(r.hold, 0.5, "C: 8/16 hold pairs -> hold 0.5");
  // 0.50*50 + 0.25*25 + 0.25*50 = 43.75, per the task spec.
  assertEqual(r.combined, 43.75, "C: combined == 43.75 exactly");
  assertEqual(sandbox.combinedCoverageFunction([trace]), 43.75, "C: combinedCoverageFunction matches coverageBreakdown.combined");
}

// --- Test D: duplicate events don't inflate either component ----------------------------------
{
  const stateEvents = ["BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE"].map(stateFeatureEvent);
  const loanEvents = [[1, 1], [1, 2], [2, 1], [2, 2]].map(function (p) { return createEvent("loan", p[0], p[1]); });
  const holdEvents = [[1, 1], [1, 2], [1, 3], [1, 4], [2, 1], [2, 2], [2, 3], [2, 4]].map(function (p) { return createEvent("hold", p[0], p[1]); });
  const baseTrace = stateEvents.concat(loanEvents).concat(holdEvents);
  const baseScore = sandbox.combinedCoverageFunction([baseTrace]);

  // Repeat every marker/create event 3x within one trace, and repeat the whole trace 3x in the
  // ensemble - same non-inflation principle already validated for rankingFunction/
  // parameterCoverageFunction in ensemble-code.test.js, now checked through the combined score too.
  const duplicatedTrace = baseTrace.concat(baseTrace).concat(baseTrace);
  const duplicatedEnsemble = [duplicatedTrace, duplicatedTrace, duplicatedTrace];
  const duplicatedScore = sandbox.combinedCoverageFunction(duplicatedEnsemble);

  assertEqual(duplicatedScore, baseScore, "D: duplicating events/traces does not change the combined score");
}

// --- Test E: out-of-range ids are excluded -------------------------------------------------------
{
  const inRangeOnly = [createEvent("loan", 1, 1), createEvent("hold", 1, 1)];
  const withOutOfRange = inRangeOnly.concat([
    createEvent("loan", 6, 1),   // userId=6 is out of range (NUMBER_OF_USERS=4)
    createEvent("hold", 1, 7),   // bookId=7 is out of range (NUMBER_OF_BOOKS=4)
  ]);

  const scoreInRangeOnly = sandbox.combinedCoverageFunction([inRangeOnly]);
  const scoreWithOutOfRange = sandbox.combinedCoverageFunction([withOutOfRange]);
  assertEqual(scoreWithOutOfRange, scoreInRangeOnly, "E: out-of-range loan/hold pairs do not change the combined score");

  const details = sandbox.parameterCoverageDetails([withOutOfRange]);
  assertEqual(details.loanPairs.size, 1, "E: out-of-range loan pair not added to loanPairs");
  assertEqual(details.holdPairs.size, 1, "E: out-of-range hold pair not added to holdPairs");
  assertEqual(details.outOfRangePairs.size, 2, "E: both out-of-range pairs tracked separately instead");
}

// --- Test F: independent rescoring against a real saved ensemble file -------------------------
{
  // Any already-saved sample/ensemble JSON works; this one was produced during the
  // event-priority investigation (gitignored under products/, not committed - regenerate with
  // `provengo sample --overwrite --size=10 --max-length=80 .` from library/provengo if absent).
  const savedFile = path.join(__dirname, "..", "..", "products", "priority-experiment", "baseline_1.json");
  if (!fs.existsSync(savedFile)) {
    console.log("SKIP - F: " + savedFile + " not found (gitignored products/ file, regenerate via `provengo sample`)");
  } else {
    const ensemble = JSON.parse(fs.readFileSync(savedFile, "utf8"));

    // Independently compute the expected combined score using ONLY the already-validated
    // rankingFunction/parameterCoverageDetails - not coverageBreakdown/combinedCoverageFunction
    // themselves - so this checks the new combination arithmetic, not the (already validated
    // elsewhere) extraction logic it reuses.
    const expectedState = sandbox.rankingFunction(ensemble) / 100; // rankingFunction already returns 0-100
    const details = sandbox.parameterCoverageDetails(ensemble);
    const pairUniverse = sandbox.NUMBER_OF_USERS * sandbox.NUMBER_OF_BOOKS;
    const expectedLoan = details.loanPairs.size / pairUniverse;
    const expectedHold = details.holdPairs.size / pairUniverse;
    // COVERAGE_WEIGHTS is declared with `const`, so (unlike the function declarations above) it
    // is not added as an own property of the vm context object - must be read by evaluating the
    // bare identifier back in that same context instead of via sandbox.COVERAGE_WEIGHTS.
    const w = vm.runInContext("COVERAGE_WEIGHTS", sandbox);
    const expectedParameterShare = 1 - w.state;
    const expectedWLoan = expectedParameterShare * w.parameter.loan;
    const expectedWHold = expectedParameterShare * w.parameter.hold;
    const expectedCombined = 100 * (w.state * expectedState + expectedWLoan * expectedLoan + expectedWHold * expectedHold);

    const actual = sandbox.combinedCoverageFunction(ensemble);
    const actualBreakdown = sandbox.coverageBreakdown(ensemble);

    assertEqual(actualBreakdown.state, expectedState, "F: coverageBreakdown.state matches independent rankingFunction-based calculation");
    assertEqual(actualBreakdown.loan, expectedLoan, "F: coverageBreakdown.loan matches independent parameterCoverageDetails-based calculation");
    assertEqual(actualBreakdown.hold, expectedHold, "F: coverageBreakdown.hold matches independent parameterCoverageDetails-based calculation");
    assertEqual(actual, expectedCombined, "F: combinedCoverageFunction matches the independently hand-computed combined score (" + savedFile + ")");
  }
}

// --- Additional required validation: weights (hierarchical: state + parameter.{loan,hold}) ----
{
  assertThrows(function () { sandbox.coverageBreakdown([], { state: 1.5, parameter: { loan: 0.5, hold: 0.5 } }); },
    "V1: a state weight outside [0,1] is rejected, not silently clamped");
  assertThrows(function () { sandbox.coverageBreakdown([], { state: -0.1, parameter: { loan: 0.6, hold: 0.5 } }); },
    "V2: a negative state weight is rejected");
  assertThrows(function () { sandbox.coverageBreakdown([], { state: 0.5, parameter: { hold: 0.5 } }); },
    "V3: a missing parameter sub-weight (loan) is rejected, not treated as 0");
  assertThrows(function () { sandbox.coverageBreakdown([], { state: 0.5, parameter: { loan: 0.3, hold: 0.3 } }); },
    "V5: parameter.loan + parameter.hold not summing to 1 is rejected (they must split 100% of Parameter's own share)");
  assertThrows(function () { sandbox.coverageBreakdown([], { state: 0.5 }); },
    "V6: a missing 'parameter' object entirely is rejected");
  // Sanity: the provisional default weights themselves must be valid.
  assertTrue((function () {
    try { sandbox.coverageBreakdown([]); return true; } catch (e) { return false; }
  })(), "V4: COVERAGE_WEIGHTS defaults pass validation");
  // The hierarchical defaults (state=0.5, parameter={loan:0.5,hold:0.5}) must resolve to the
  // same effective wLoan=wHold=0.25 the flat scheme used before this restructuring.
  {
    const trace = [createEvent("loan", 1, 1), createEvent("hold", 2, 2)];
    const r = sandbox.coverageBreakdown([trace]);
    assertEqual(r.combined, 100 * (0.25 / 16 + 0.25 / 16), "V7: default hierarchical weights resolve to wLoan=wHold=0.25 effectively");
  }
}

// --- Additional required validation: rankingFunction/parameterCoverageFunction are untouched ---
{
  const trace = ALL_STATE_FEATURES.map(stateFeatureEvent).concat([createEvent("loan", 1, 1), createEvent("hold", 2, 2)]);
  const stateOnly = sandbox.rankingFunction([trace]);
  const paramOnly = sandbox.parameterCoverageFunction([trace]);
  assertEqual(stateOnly, 100, "G1: rankingFunction still returns its own independent 0-100 score unaffected by combinedCoverageFunction existing");
  assertEqual(paramOnly, 100 * (2 / 32), "G2: parameterCoverageFunction still returns its own independent 0-100 score (shared 32-pair universe), unaffected");
}

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail === 0 ? 0 : 1);
