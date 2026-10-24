// Standalone edge-case test harness for library/provengo/meta-spec/ensemble-code.js's
// rankingFunction, run via plain Node (not the Provengo CLI), so expected
// scores can be hand-computed and asserted exactly. See conversation for context.
// Run with: node ensemble-code.test.js
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const SRC = path.join(__dirname, "..", "ensemble-code.js");

const sandbox = { console };
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

// Matches lib_stories.js's markStateFeature(): bp.sync({request: bp.Event("StateFeature", {feature: name})}).
function stateFeatureEvent(name) {
  return { name: "StateFeature", data: { feature: name } };
}
function restEvent(verb, url, parameters) {
  return { name: verb, data: { lib: "REST", method: verb, url: "http://localhost:23242" + url, parameters } };
}

const ALL_STATE_FEATURES = ["BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE", "HOLD_WITHOUT_LOAN", "MULTI_USER_BOOK_RELATIONS", "USER_WITH_TWO_BOOKS"];
const NUM_STATE_FEATURES = ALL_STATE_FEATURES.length;

// --- Test 1: state-feature coverage counted from StateFeature marker events ------------------
{
  const partialTrace = ["BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE", "HOLD_WITHOUT_LOAN"].map(stateFeatureEvent);
  const fullTrace = ALL_STATE_FEATURES.map(stateFeatureEvent);

  const scorePartial = sandbox.rankingFunction([partialTrace]);
  const scoreFull = sandbox.rankingFunction([fullTrace]);
  assertEqual(scorePartial, 100 * (4 / NUM_STATE_FEATURES), "T1a: 4/" + NUM_STATE_FEATURES + " state feature markers");
  assertEqual(scoreFull, 100, "T1b: all state feature markers -> 100");
  assertTrue(scoreFull > scorePartial, "T1c: the richer trace scores strictly higher");
}

// --- Test 2: unrelated (non-StateFeature) events don't affect the score ----------------------
{
  const trace = [stateFeatureEvent("HOLD_WITHOUT_LOAN"), restEvent("POST", "/loans", { userId: 1, bookId: 1 })];
  const score = sandbox.rankingFunction([trace]);
  assertEqual(score, 100 * (1 / NUM_STATE_FEATURES), "T2: a REST event alongside one marker doesn't add or remove coverage");
}

// --- Test 3: duplicate markers/traces don't inflate the score --------------------------------
{
  const trace = [stateFeatureEvent("HOLD_WITHOUT_LOAN"), stateFeatureEvent("HOLD_WITHOUT_LOAN")];
  const s1 = sandbox.rankingFunction([trace]);
  const s2 = sandbox.rankingFunction([trace, trace, trace]);
  assertEqual(s1, 100 * (1 / NUM_STATE_FEATURES), "T3a: repeating the same marker in one trace counts once");
  assertEqual(s1, s2, "T3b: repeating the identical trace 3x does not change the score");
}

// --- Test 4: coverage accumulates across different tests in the ensemble ---------------------
{
  const t1 = [stateFeatureEvent("BOOK_DELETE_ELIGIBLE")];
  const t2 = [stateFeatureEvent("USER_DELETE_ELIGIBLE")];
  const score = sandbox.rankingFunction([t1, t2]);
  assertEqual(score, 100 * (2 / NUM_STATE_FEATURES), "T4: markers from different tests in the ensemble both count");
}

// --- Test 5: specific edge cases requested during RankingFunction review (2026-10-24) --------
{
  // T5a: exactly half of the 6 features marked -> score is exactly 50, not just "some partial
  // value" (T1a already covers 4/6; this is the round-number case asked for explicitly).
  const halfTrace = ["BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE"].map(stateFeatureEvent);
  assertEqual(sandbox.rankingFunction([halfTrace]), 50, "T5a: exactly 3/6 features marked -> score 50");
}
{
  // T5b: a StateFeature-named event whose feature value is NOT in STATE_FEATURES (e.g. a stray
  // HOLD_CREATABLE marker left over from before it was dropped, or any unrecognized name) must
  // not count towards the score - only recognized feature names should move the needle.
  const trace = [stateFeatureEvent("HOLD_CREATABLE"), stateFeatureEvent("SOME_UNKNOWN_FEATURE")];
  assertEqual(sandbox.rankingFunction([trace]), 0, "T5b: StateFeature events with a name outside STATE_FEATURES don't count");
}
{
  // T5c: an ensemble with REST traffic but zero StateFeature markers scores 0, regardless of how
  // much unrelated activity happened - the function only ever counts markers it actually saw,
  // never a ground truth it has no way to see (this is the empirically-validated-elsewhere
  // "unmarked features aren't counted" behavior, captured here as a standing unit test).
  const trace = [
    restEvent("POST", "/users", { id: 1 }),
    restEvent("POST", "/books", { id: 1 }),
    restEvent("POST", "/loans", { userId: 1, bookId: 1 }),
  ];
  assertEqual(sandbox.rankingFunction([trace]), 0, "T5c: no StateFeature markers at all -> score 0, even with real REST activity");
}

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail === 0 ? 0 : 1);
