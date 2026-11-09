// Standalone edge-case test harness for library/provengo/meta-spec/ensemble-code.js's CTD
// Parameter Coverage design (classifyCtdIdValue / classifyCtdStringValue / classifyCtdCombination /
// ctdParameterCoverageDetails / ctdParameterCoverageFunction / ctdParameterCoverageBreakdown, and
// coverageBreakdownV3/combinedCoverageFunctionV3's repointed parameter term) - run via plain Node
// (not the Provengo CLI), mirrors the other *.test.js harnesses in this directory.
// Run with: node ctd-parameter-coverage.test.js
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const SRC = path.join(__dirname, "..", "ensemble-code.js");
const sandbox = { console, NUMBER_OF_USERS: 4, NUMBER_OF_BOOKS: 4 };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox, { filename: SRC });

let pass = 0, fail = 0;
function assertEqual(actual, expected, label) {
  const ok = actual === expected || (typeof actual === "number" && typeof expected === "number" && Math.abs(actual - expected) < 1e-9);
  console.log((ok ? "PASS" : "FAIL") + " - " + label + " (expected " + JSON.stringify(expected) + ", got " + JSON.stringify(actual) + ")");
  if (ok) pass++; else fail++;
}
function assertTrue(cond, label) {
  console.log((cond ? "PASS" : "FAIL") + " - " + label);
  if (cond) pass++; else fail++;
}
function assertNull(actual, label) {
  assertTrue(actual === null, label + " (got " + JSON.stringify(actual) + ")");
}

// Builds a create-action event exactly as buildRestEvent/requestOneOfDirect really produce it:
// data.model.name carries "<action> (<label>): <id>", data.body carries the submitted JSON body
// as a STRING (interfaces.library.js:62 - data.body = JSON.stringify(options.body)).
function bodyEvent(action, label, bodyObj, expectedResponseCodes) {
  return {
    name: "POST",
    data: {
      lib: "REST",
      model: { name: action + " (" + label + "): 1", valid: label.indexOf("valid") === 0 && label.indexOf("invalid") !== 0 },
      body: JSON.stringify(bodyObj),
      expectedResponseCodes: expectedResponseCodes
    }
  };
}

// Builds a delete-action event exactly as deleteBook/deleteUser/deleteHold/deleteLoan really
// produce it: data.url carries the full path (base URL + resource path), the id(s) as trailing
// path segments - either an RTV template ("@{BOOK3}") or a literal invalid/nonexistent token.
function pathEvent(action, label, url, expectedResponseCodes) {
  return {
    name: "DELETE",
    data: {
      lib: "REST",
      model: { name: action + " (" + label + "): 1", valid: label === "valid" },
      url: "http://localhost:23242" + url,
      expectedResponseCodes: expectedResponseCodes
    }
  };
}

// ---------------------------------------------------------------------------------------------
// 1. Equivalent requests with different concrete IDs produce the same coverage item (symmetry).
// ---------------------------------------------------------------------------------------------
{
  const e1 = bodyEvent("createLoan", "valid-standard", { userId: "@{USER1}", bookId: "@{BOOK1}" }, [201]);
  const e2 = bodyEvent("createLoan", "valid-standard", { userId: "@{USER3}", bookId: "@{BOOK4}" }, [201]);
  assertEqual(sandbox.classifyCtdCombination(e1), "createLoan:VALID,VALID", "T1a: createLoan with USER1/BOOK1 classifies to createLoan:VALID,VALID");
  assertEqual(sandbox.classifyCtdCombination(e1), sandbox.classifyCtdCombination(e2), "T1b: USER1/BOOK1 and USER3/BOOK4 (different concrete ids, same symmetry class) classify identically");

  const h1 = pathEvent("deleteBook", "valid", "/books/@{BOOK1}", [200]);
  const h2 = pathEvent("deleteBook", "valid", "/books/@{BOOK4}", [200]);
  assertEqual(sandbox.classifyCtdCombination(h1), sandbox.classifyCtdCombination(h2), "T1c: deleteBook with BOOK1 vs BOOK4 (different concrete ids) classify identically");
}

// ---------------------------------------------------------------------------------------------
// 2. Meaningfully different parameter combinations produce different items.
// ---------------------------------------------------------------------------------------------
{
  const valid = bodyEvent("createLoan", "valid-standard", { userId: "@{USER1}", bookId: "@{BOOK1}" }, [201]);
  const missingBook = bodyEvent("createLoan", "invalid - missing bookId", { userId: "@{USER1}" }, [400]);
  const zeroUser = bodyEvent("createLoan", "invalid - userId is zero", { userId: 0, bookId: "@{BOOK1}" }, [400]);
  assertEqual(sandbox.classifyCtdCombination(valid), "createLoan:VALID,VALID", "T2a: a fully valid createLoan classifies to VALID,VALID");
  assertEqual(sandbox.classifyCtdCombination(missingBook), "createLoan:VALID,MISSING", "T2b: missing bookId classifies to VALID,MISSING");
  assertEqual(sandbox.classifyCtdCombination(zeroUser), "createLoan:OUT_OF_RANGE,VALID", "T2c: userId=0 classifies to OUT_OF_RANGE,VALID");
  assertTrue(sandbox.classifyCtdCombination(valid) !== sandbox.classifyCtdCombination(missingBook) &&
    sandbox.classifyCtdCombination(missingBook) !== sandbox.classifyCtdCombination(zeroUser),
    "T2d: three behaviorally different combinations all classify to three different units");
}

// ---------------------------------------------------------------------------------------------
// 3. Valid and invalid parameter classes are distinguished.
// ---------------------------------------------------------------------------------------------
{
  assertEqual(sandbox.classifyCtdIdValue("@{USER1}"), "VALID", "T3a: an RTV template is VALID");
  assertEqual(sandbox.classifyCtdIdValue(0), "OUT_OF_RANGE", "T3b: 0 is OUT_OF_RANGE");
  assertEqual(sandbox.classifyCtdIdValue(-5), "OUT_OF_RANGE", "T3c: a negative number is OUT_OF_RANGE");
  assertEqual(sandbox.classifyCtdIdValue(undefined), "MISSING", "T3d: an absent field is MISSING");
  assertEqual(sandbox.classifyCtdIdValue(null), "NULL", "T3e: an explicit null is NULL");
  assertEqual(sandbox.classifyCtdIdValue(true), "WRONG_TYPE", "T3f: a boolean is WRONG_TYPE");
  assertEqual(sandbox.classifyCtdIdValue({ val: 1 }), "WRONG_TYPE", "T3g: a plain object is WRONG_TYPE");
  assertEqual(sandbox.classifyCtdIdValue("bad-user-id"), "WRONG_TYPE", "T3h: a non-numeric, non-template string is WRONG_TYPE");
  assertEqual(sandbox.classifyCtdIdValue(1000000000), "VALID_NONEXISTENT", "T3i: a generateMissingId-scale number (>= 1e6) is VALID_NONEXISTENT");
  assertEqual(sandbox.classifyCtdIdValue(999999), "VALID", "T3j: the SUT's own real id ceiling (999999, sut.py's _ID_MAX) is still VALID, not VALID_NONEXISTENT");
  assertEqual(sandbox.classifyCtdStringValue(""), "EMPTY", "T3k: an empty string is EMPTY (string classifier)");
  assertEqual(sandbox.classifyCtdStringValue("My Book"), "VALID", "T3l: a non-empty string is VALID");
  assertEqual(sandbox.classifyCtdStringValue(12345), "WRONG_TYPE", "T3m: a number where a string is expected is WRONG_TYPE");
}

// ---------------------------------------------------------------------------------------------
// 4. A request with two invalid fields is classified using BOTH submitted fields, regardless of
//    the SUT's short-circuit validation (sut.py validates userId then bookId, returning on the
//    first failure - the response alone could never prove bookId was also invalid).
// ---------------------------------------------------------------------------------------------
{
  // Mirrors interfaces.library.js:529's real "multiple wrong types" variant exactly: both fields
  // wrong type, but expectedResponseCodes is just [400] - a single generic rejection code, the
  // same code a SINGLE-field failure would also carry. The classifier must not need more than this.
  const dualInvalid = bodyEvent("createLoan", "invalid - multiple wrong types", { userId: true, bookId: false }, [400]);
  assertEqual(sandbox.classifyCtdCombination(dualInvalid), "createLoan:WRONG_TYPE,WRONG_TYPE",
    "T4: a request with BOTH userId and bookId wrong-typed classifies as WRONG_TYPE,WRONG_TYPE from the submitted body alone - not inferred from (and not contradicted by) the SUT's single-field-only rejection response");
}

// ---------------------------------------------------------------------------------------------
// 5. Duplicate occurrences do not increase distinct-combination coverage (no repetition bonus).
// ---------------------------------------------------------------------------------------------
{
  const e = bodyEvent("createLoan", "valid-standard", { userId: "@{USER1}", bookId: "@{BOOK1}" }, [201]);
  const once = sandbox.ctdParameterCoverageFunction([[e]]);
  const fiveTimes = sandbox.ctdParameterCoverageFunction([[e, e, e, e, e]]);
  const acrossTraces = sandbox.ctdParameterCoverageFunction([[e], [e], [e]]);
  assertEqual(once, fiveTimes, "T5a: repeating the identical event 5x in one trace does not change the score");
  assertEqual(once, acrossTraces, "T5b: repeating the identical event across 3 traces does not change the score either");
  assertEqual(once, 100 / sandbox.CTD_UNIVERSE_SIZE, "T5c: one distinct unit hit scores exactly 100/universeSize");
}

// ---------------------------------------------------------------------------------------------
// 6. Impossible combinations are excluded from the universe (not counted, not in the denominator).
// ---------------------------------------------------------------------------------------------
{
  // No real generator ever makes BOTH userId and bookId OUT_OF_RANGE simultaneously (verified
  // against interfaces.library.js's own invalid-case lists) - construct it directly to confirm the
  // classifier still reports it (it IS a real, well-defined combination), but that it is tracked
  // as "outside the declared universe" and never counted towards the score.
  const impossible = bodyEvent("createLoan", "invalid - synthetic-both-out-of-range", { userId: 0, bookId: -1 }, [400]);
  const details = sandbox.ctdParameterCoverageDetails([[impossible]]);
  assertTrue(details.outsideUniverse.has("createLoan:OUT_OF_RANGE,OUT_OF_RANGE"), "T6a: a combination no real variant generator constructs is recorded as outsideUniverse");
  assertTrue(!details.hit.has("createLoan:OUT_OF_RANGE,OUT_OF_RANGE"), "T6b: that same combination is NOT counted as a hit");
  assertEqual(sandbox.ctdParameterCoverageFunction([[impossible]]), 0, "T6c: an ensemble containing only an outside-universe combination scores 0, not a phantom positive score");
  assertTrue(sandbox.CTD_UNIVERSE.indexOf("createLoan:OUT_OF_RANGE,OUT_OF_RANGE") === -1, "T6d: the declared universe itself does not list this combination");
  assertEqual(sandbox.CTD_UNIVERSE_SIZE, 72, "T6e: the total declared universe size is exactly 72 (5+5+22+22+4+4+4+6), matching the documented enumeration");
}

// ---------------------------------------------------------------------------------------------
// 7. The score stays within 0-100, including for an empty ensemble.
// ---------------------------------------------------------------------------------------------
{
  assertEqual(sandbox.ctdParameterCoverageFunction([[]]), 0, "T7a: an empty ensemble (no events) scores 0");
  assertEqual(sandbox.ctdParameterCoverageFunction([]), 0, "T7b: an ensemble with zero traces scores 0");

  // Build one event per declared universe unit (every action/combination at least once) -> 100.
  const allUnitEvents = [];
  const actions = Object.keys(sandbox.CTD_FEASIBLE_COMBINATIONS_BY_ACTION);
  const isPathAction = { deleteBook: true, deleteUser: true, deleteHold: true, deleteLoan: true };
  function rawForClass(cls) {
    if (cls === "MISSING") return undefined;
    if (cls === "NULL") return null;
    if (cls === "WRONG_TYPE") return true;
    if (cls === "OUT_OF_RANGE") return 0;
    if (cls === "VALID_NONEXISTENT") return 1000000005;
    if (cls === "VALID") return "@{USER1}";
    if (cls === "EMPTY") return "";
    return "unexpected-class:" + cls;
  }
  for (const action of actions) {
    for (const combo of sandbox.CTD_FEASIBLE_COMBINATIONS_BY_ACTION[action]) {
      const classes = combo.split(",");
      if (isPathAction[action]) {
        const segs = classes.map(function (c) {
          const v = rawForClass(c);
          return v === undefined ? "MISSING_PLACEHOLDER" : String(v);
        });
        allUnitEvents.push(pathEvent(action, "universe-fill", "/x/" + segs.join("/"), [200]));
      } else {
        const fieldNames = action === "createBook" ? ["title"] : action === "createUser" ? ["name"] : ["userId", "bookId"];
        const body = {};
        classes.forEach(function (c, i) {
          const v = rawForClass(c);
          if (v !== undefined) body[fieldNames[i]] = v;
        });
        allUnitEvents.push(bodyEvent(action, "universe-fill", body, [201]));
      }
    }
  }
  const fullEnsemble = [allUnitEvents];
  const breakdown = sandbox.ctdParameterCoverageBreakdown(fullEnsemble);
  assertEqual(breakdown.unitsHit, 72, "T7c: a synthetic ensemble built from one event per declared universe unit hits all 72 units");
  assertEqual(sandbox.ctdParameterCoverageFunction(fullEnsemble), 100, "T7d: that same ensemble scores exactly 100");
  assertTrue(sandbox.ctdParameterCoverageFunction(fullEnsemble) <= 100, "T7e: score never exceeds 100 even on a maximal ensemble");
}

// ---------------------------------------------------------------------------------------------
// 8. The combined ranking actually uses the new CTD Parameter Coverage implementation.
// ---------------------------------------------------------------------------------------------
{
  const oneUnit = [[bodyEvent("createLoan", "valid-standard", { userId: "@{USER1}", bookId: "@{BOOK1}" }, [201])]];
  const twoUnits = [[
    bodyEvent("createLoan", "valid-standard", { userId: "@{USER1}", bookId: "@{BOOK1}" }, [201]),
    bodyEvent("createLoan", "invalid - missing bookId", { userId: "@{USER1}" }, [400])
  ]];
  const b1 = sandbox.coverageBreakdownV3(oneUnit);
  const b2 = sandbox.coverageBreakdownV3(twoUnits);
  assertEqual(b1.parameter, sandbox.ctdParameterCoverageFunction(oneUnit) / 100, "T8a: coverageBreakdownV3.parameter matches ctdParameterCoverageFunction/100 exactly");
  assertEqual(sandbox.combinedCoverageFunctionV3(oneUnit), b1.combined, "T8b: combinedCoverageFunctionV3 matches coverageBreakdownV3(...).combined exactly");
  assertTrue(b2.parameter > b1.parameter, "T8c: hitting one more CTD unit strictly increases the parameter sub-score");
  assertTrue(sandbox.combinedCoverageFunctionV3(twoUnits) > sandbox.combinedCoverageFunctionV3(oneUnit),
    "T8d: the ACTIVE combined ranking function (combinedCoverageFunctionV3) is strictly higher when more CTD combinations are hit, with identical State Coverage (0 markers in both) - proving the combined output is actually driven by the new design, not left unchanged");

  // Sanity: every earlier Parameter Coverage design was removed - CTD is the only one left.
  assertEqual(typeof sandbox.rawParameterScoreNormalized, "undefined", "T8e: the old raw-variant active design (rawParameterScoreNormalized) no longer exists");
  assertEqual(typeof sandbox.parameterVariantCoverageFunction, "undefined", "T8f: the equivalence-class design (parameterVariantCoverageFunction) no longer exists");
  assertEqual(typeof sandbox.parameterCoverageFunction, "undefined", "T8g: the original ID-pair design (parameterCoverageFunction) no longer exists");
  assertEqual(typeof sandbox.requestOutcomeCoverageFunction, "undefined", "T8h: the V2 outcome-class design (requestOutcomeCoverageFunction) no longer exists");
}

// ---------------------------------------------------------------------------------------------
// Path-based (delete) actions: extraction from URL path segments, including the 2-segment case.
// ---------------------------------------------------------------------------------------------
{
  const validDelete = pathEvent("deleteBook", "valid", "/books/@{BOOK1}", [200]);
  const badId = pathEvent("deleteBook", "invalid - bad-id", "/books/bad-id", [400]);
  const zeroId = pathEvent("deleteBook", "invalid - zero", "/books/0", [400]);
  const nonexistent = pathEvent("deleteBook", "valid-business-reject", "/books/1000000007", [404]);
  assertEqual(sandbox.classifyCtdCombination(validDelete), "deleteBook:VALID", "T9a: deleteBook with an RTV-templated existing id classifies to deleteBook:VALID");
  assertEqual(sandbox.classifyCtdCombination(badId), "deleteBook:WRONG_TYPE", "T9b: deleteBook /books/bad-id classifies to deleteBook:WRONG_TYPE");
  assertEqual(sandbox.classifyCtdCombination(zeroId), "deleteBook:OUT_OF_RANGE", "T9c: deleteBook /books/0 classifies to deleteBook:OUT_OF_RANGE");
  assertEqual(sandbox.classifyCtdCombination(nonexistent), "deleteBook:VALID_NONEXISTENT", "T9d: deleteBook with a generateMissingId-scale literal path id classifies to deleteBook:VALID_NONEXISTENT");

  const deleteLoanValid = pathEvent("deleteLoan", "valid", "/loans/@{USER1}/@{BOOK1}", [200]);
  const deleteLoanBadBook = pathEvent("deleteLoan", "invalid - bad-book-id", "/loans/1/bad-book-id", [400]);
  assertEqual(sandbox.classifyCtdCombination(deleteLoanValid), "deleteLoan:VALID,VALID", "T9e: deleteLoan with two existing path ids classifies to deleteLoan:VALID,VALID");
  assertEqual(sandbox.classifyCtdCombination(deleteLoanBadBook), "deleteLoan:VALID,WRONG_TYPE", "T9f: deleteLoan with a bad bookId path segment classifies to deleteLoan:VALID,WRONG_TYPE (userId segment unaffected)");
}

// ---------------------------------------------------------------------------------------------
// Unrecognized / malformed events are ignored (return null), not thrown or miscounted.
// ---------------------------------------------------------------------------------------------
{
  assertNull(sandbox.classifyCtdCombination({ data: { lib: "REST" } }), "T10a: an event with no model.name classifies to null");
  assertNull(sandbox.classifyCtdCombination(bodyEvent("readBookDetail", "valid-standard", { id: 1 }, [200])), "T10b: a read action (not in CTD_ACTION_SPEC) classifies to null");
  assertNull(sandbox.classifyCtdCombination({ data: { lib: "Ctrl", verb: "marker", value: "LOAN_BLOCKED_VIA_USER_ONLY" } }), "T10c: a State Coverage marker event classifies to null - CTD Parameter Coverage never reads marker events");
}

console.log("\n" + pass + " passed, " + fail + " failed");
