// State coverage ranking: a Set of distinct STATE_FEATURES markers hit, not raw occurrences -
// reaching the same state many times must not score higher than reaching it once.
// HOLD_CREATABLE deliberately excluded: UserBook.CanCreateHold has no restricting condition
// (true for any user-book pair), so it can't discriminate between scenarios - see lib_stories.js.
const STATE_FEATURES = [
    "BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE",
    "LOAN_CREATABLE",
    "HOLD_WITHOUT_LOAN", "MULTI_USER_BOOK_RELATIONS",
    "USER_WITH_TWO_BOOKS"
];

// Counts how many distinct STATE_FEATURES markers (lib_stories.js's markStateFeature bthreads,
// which call Ctrl.doMark) appeared anywhere in the ensemble - a Set, so reaching the same state
// many times only counts once.
//
// Reads Ctrl.markEvent's own event shape (controlLib.js): name "marker: " + value, data
// {lib:"Ctrl", verb:"marker", value: <feature name>, eventPriority: 1010} - not a custom
// "StateFeature"/data.feature shape, since markStateFeature calls Ctrl.doMark directly.
function distinctStateFeaturesHit(ensemble) {
    let hit = new Set();
    for (let test of ensemble)
        for (let event of test)
            if (event.data && event.data.lib === "Ctrl" && event.data.verb === "marker" && STATE_FEATURES.indexOf(event.data.value) !== -1)
                hit.add(event.data.value);
    return hit.size;
}

/**
 * A score of 0 (or any value below 100) means no StateFeature MARKER for the missing
 * feature(s) was observed in this ensemble - it does NOT mean the underlying state never
 * actually occurred. The marker mechanism's own reliability (whether a state that truly
 * occurred reliably produces its marker) was measured separately against a live SUT - see
 * meta-spec/tests/RESEARCH_SUMMARY.md §8 and the per-run data in state_feature_runs.csv - and
 * is a precondition for trusting this score as a proxy for actual state coverage, not something
 * this function can verify on its own.
 *
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns State-feature coverage, 0-100.
 */
function rankingFunction(ensemble) {
    return (distinctStateFeaturesHit(ensemble) / STATE_FEATURES.length) * 100;
}

//////////////////////////////////////////////////////////////////////////
// Parameter coverage (2026-10-24) - deliberately independent of rankingFunction/STATE_FEATURES
// above: doesn't read StateFeature events or touch lib_stories.js, so the already-validated
// State Coverage measurement can't be affected by this.
//
// Reuses the NUMBER_OF_USERS/NUMBER_OF_BOOKS globals lib_stories.js already declares, rather
// than redeclaring them here - every meta-spec/spec .js file Provengo loads shares one global
// Rhino scope, and a second top-level `const` of the same name is a redeclaration error, not a
// shadowing local (confirmed by hitting exactly that error while developing this).
//////////////////////////////////////////////////////////////////////////

/**
 * Extracts {type, userId, bookId} from an event IF it's a genuinely emitted createLoan or
 * createHold request - i.e. this exact variant was selected and actually sent (requestOneOfDirect
 * is single-sync, so selection is sending), not a rejected/invalid-shape attempt that merely looks
 * similar. Uses the same "Create: " description-prefix convention already established and
 * validated elsewhere in this investigation (dal.js's effects, verify_state_features.py's
 * is_genuine) - interfaces.library.js's createLoan/createHold only set this description, with
 * userId/bookId alongside it, on their valid variants; invalid variants carry no `parameters` at
 * all, so they never match here. Returns null for anything else (including unrelated REST calls).
 *
 * Caveat carried over unchanged from earlier state-feature work (RESEARCH_SUMMARY.md): this only
 * proves the request was genuinely emitted, not that the SUT actually returned 200/201 for it -
 * neither this function nor the rest of the model checks the real response code. Treat the
 * resulting score as coverage of emitted create requests, not confirmed-successful creates.
 */
function extractLoanOrHoldCreateParams(event) {
    const d = event && event.data;
    if (!d || d.lib !== "REST" || d.method !== "POST") return null;
    const params = d.parameters;
    const description = params && params.description;
    if (typeof description !== "string") return null;
    let type;
    if (description.indexOf("Create: Loan") === 0) type = "loan";
    else if (description.indexOf("Create: Hold") === 0) type = "hold";
    else return null;
    // parseInt rather than Number.isInteger: userId/bookId may come back as a Rhino-wrapped
    // java.lang.Integer/Long once deserialized from a persisted samples.json/ensemble.json, and
    // Number.isInteger() requires typeof === "number", which such a wrapped value may not
    // satisfy. parseInt coerces via String() first, so it's safe across that boundary regardless;
    // isNaN after parseInt is the correct "was this actually present and numeric" check.
    const userId = Number.parseInt(params.userId, 10);
    const bookId = Number.parseInt(params.bookId, 10);
    if (isNaN(userId) || isNaN(bookId)) return null;
    return { type: type, userId: userId, bookId: bookId };
}

/**
 * Parameter coverage, split per action type (loan/hold) since they're different endpoints/slots,
 * not one shared value space. Each is a Set of distinct (userId, bookId) pairs, counted once no
 * matter how many times the same pair recurs - same non-double-counting principle as
 * distinctStateFeaturesHit.
 *
 * Only pairs within the basic NUMBER_OF_USERS x NUMBER_OF_BOOKS space count towards coverage - a
 * pair with an id outside that range is a known artifact of lib_stories.js's
 * tryToDeleteNonexisting{User,Book,Loan} bthreads burning real id-generator counters (see
 * RESEARCH_SUMMARY.md / project memory), not a legitimate part of the parameter space, and is
 * NOT normalized into the denominator to compensate - it's tracked separately in
 * outOfRangePairs instead, so the base 4x4=16-pair universe stays a fixed, bug-independent
 * definition that's fair to compare across candidates/runs.
 *
 * @param {Event[][]} ensemble Test suite to be measured.
 * @returns {{loanPairs: Set<string>, holdPairs: Set<string>, outOfRangePairs: Set<string>}}
 */
function parameterCoverageDetails(ensemble) {
    const loanPairs = new Set();
    const holdPairs = new Set();
    const outOfRangePairs = new Set();
    for (let test of ensemble) {
        for (let event of test) {
            const extracted = extractLoanOrHoldCreateParams(event);
            if (!extracted) continue;
            const inRange = extracted.userId >= 1 && extracted.userId <= NUMBER_OF_USERS &&
                extracted.bookId >= 1 && extracted.bookId <= NUMBER_OF_BOOKS;
            const key = extracted.type + ":" + extracted.userId + "," + extracted.bookId;
            if (inRange) {
                (extracted.type === "loan" ? loanPairs : holdPairs).add(key);
            } else {
                outOfRangePairs.add(key);
            }
        }
    }
    return { loanPairs: loanPairs, holdPairs: holdPairs, outOfRangePairs: outOfRangePairs };
}

/**
 * Parameter coverage of emitted create requests (see extractLoanOrHoldCreateParams's caveat - not
 * "confirmed successful creates"), 0-100: the fraction of the fixed 2*NUMBER_OF_USERS*NUMBER_OF_BOOKS
 * (loan pairs + hold pairs, each out of 16) universe actually exercised by this ensemble.
 * Deliberately NOT combined with rankingFunction above - a separate, independent score so
 * `provengo ensemble --ranking-function=parameterCoverageFunction` can be compared against
 * `--ranking-function=rankingFunction` without either affecting the other's measurement.
 *
 * KNOWN CLI QUIRK (found 2026-10-24, not fixed here - it's in Provengo's own closed-source
 * GeneticOptimizer, not this file): `provengo ensemble --ranking-function=parameterCoverageFunction`
 * printed "rank 0.000" against a real live-SUT pool that genuinely had non-zero coverage (9/10
 * traces independently confirmed to contain genuine loan/hold creates, via both Python and a
 * direct Node `vm` call to this exact function on the raw samples.json - both agreed exactly,
 * e.g. 28.125 on the full 10-trace pool). Re-scoring the CLI's OWN written output file
 * (`ensemble_param2.json`) directly through this same function gave 18.75, not 0 - the function
 * is correct; the CLI's live progress-log "rank" number during/after a custom-named
 * `--ranking-function` search is not trustworthy and must not be read as the real score. Always
 * re-score the written ensemble file independently (as done here) rather than trusting the CLI's
 * printed rank for any ranking function other than the one it shipped with by default.
 *
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns Parameter coverage, 0-100.
 */
function parameterCoverageFunction(ensemble) {
    const details = parameterCoverageDetails(ensemble);
    const universe = 2 * NUMBER_OF_USERS * NUMBER_OF_BOOKS;
    return ((details.loanPairs.size + details.holdPairs.size) / universe) * 100;
}

//////////////////////////////////////////////////////////////////////////
// Combined coverage (2026-11-02) - a weighted combination of the already-independently-
// validated State Coverage (distinctStateFeaturesHit/STATE_FEATURES above) and Parameter
// Coverage (parameterCoverageDetails above), as three separately-normalized components
// (state/loan/hold, each 0-1). Reuses those functions as-is; does not duplicate marker
// detection or parameter extraction/validation, and does not alter rankingFunction or
// parameterCoverageFunction above - both remain independently runnable
// (--ranking-function=rankingFunction / =parameterCoverageFunction), unaffected by this.
//
// Loan and Hold are each normalized over their OWN NUMBER_OF_USERS*NUMBER_OF_BOOKS=16-pair
// space (not parameterCoverageFunction's shared 32-pair universe) specifically so a weight can
// be assigned to each independently.
//
// Weights are hierarchical, not three flat independent numbers: `state` is State's share of the
// total, and `parameter.loan`/`parameter.hold` split the REMAINING share (1 - state) between
// Loan and Hold - parameter.loan + parameter.hold must sum to 1 on their own (a complete split
// of "the rest"), not to (1 - state) directly. This mirrors how the question actually gets
// discussed with the advisor as two separate decisions ("how much does Parameter matter
// relative to State", then separately "how should Parameter's budget split between Loan and
// Hold") rather than one three-way number pick. It's equivalent in expressiveness to a flat
// wState+wLoan+wHold=1 scheme (wLoan = (1-wState)*parameter.loan, same for hold) - this is a
// parameterization choice, not a different scoring capability.
//////////////////////////////////////////////////////////////////////////

// Provisional defaults only (2026-11-02) - NOT a research finding and not yet reviewed with
// the advisor. The investigation that led here found Loan pairs structurally harder to cover
// than Hold pairs (business-rule-serialized vs. unrestricted - see dal.js's
// UserBook.CanCreateLoan/CanCreateHold), but per explicit instruction this is deliberately NOT
// used to justify a larger Loan weight here - that is exactly the kind of decision reserved for
// the advisor discussion + controlled weighting experiments this function is meant to enable,
// not something to bake in now. 50/50 within `parameter` here resolves to the same wLoan=0.25/
// wHold=0.25 as the flat scheme this replaced. Change these numbers for a future experiment;
// nothing else in this section needs to change to support that.
const COVERAGE_WEIGHTS = {
    state: 0.50,
    parameter: {
        loan: 0.50,
        hold: 0.50
    }
};

// Hard failure, not a clamp: silently normalizing or clamping an invalid weights object would
// hide a misconfiguration (e.g. a typo'd component name, or shares that don't sum to 1) behind
// a plausible-looking score instead of surfacing it.
function validateCoverageWeights(weights) {
    if (!weights || typeof weights !== "object") {
        throw new Error("combinedCoverageFunction: weights must be an object");
    }
    const state = weights.state;
    if (typeof state !== "number" || isNaN(state) || state < 0 || state > 1) {
        throw new Error("combinedCoverageFunction: weight 'state' must be a number in [0,1], got " + state);
    }
    const parameter = weights.parameter;
    if (!parameter || typeof parameter !== "object") {
        throw new Error("combinedCoverageFunction: weights.parameter must be an object with 'loan' and 'hold'");
    }
    const loanShare = parameter.loan;
    const holdShare = parameter.hold;
    if (typeof loanShare !== "number" || isNaN(loanShare) || loanShare < 0) {
        throw new Error("combinedCoverageFunction: weights.parameter.loan must be a nonnegative number, got " + loanShare);
    }
    if (typeof holdShare !== "number" || isNaN(holdShare) || holdShare < 0) {
        throw new Error("combinedCoverageFunction: weights.parameter.hold must be a nonnegative number, got " + holdShare);
    }
    if (Math.abs(loanShare + holdShare - 1) > 1e-9) {
        throw new Error("combinedCoverageFunction: weights.parameter.loan + weights.parameter.hold must sum to 1 (a complete split of Parameter's own share), got " + (loanShare + holdShare));
    }
}

/**
 * The three coverage components (each 0-1) plus the combined score (0-100), computed purely by
 * calling the existing, already-validated distinctStateFeaturesHit()/parameterCoverageDetails()
 * - so a high combined score can be checked against its parts instead of hiding poor coverage
 * in one component. This is the function to call for inspection/reporting;
 * combinedCoverageFunction() below is the thin ranking-function-shaped wrapper around it.
 *
 * @param {Event[][]} ensemble Test suite to be measured.
 * @param {{state:number, parameter:{loan:number, hold:number}}} [weights] Defaults to
 *   COVERAGE_WEIGHTS. Validated the same way regardless of caller - see validateCoverageWeights.
 * @returns {{state:number, loan:number, hold:number, combined:number}} state/loan/hold in
 *   [0,1]; combined in [0,100].
 */
function coverageBreakdown(ensemble, weights) {
    weights = weights || COVERAGE_WEIGHTS;
    validateCoverageWeights(weights);

    const state = distinctStateFeaturesHit(ensemble) / STATE_FEATURES.length;
    const details = parameterCoverageDetails(ensemble);
    const pairUniverse = NUMBER_OF_USERS * NUMBER_OF_BOOKS;
    const loan = details.loanPairs.size / pairUniverse;
    const hold = details.holdPairs.size / pairUniverse;

    const parameterShare = 1 - weights.state;
    const wLoan = parameterShare * weights.parameter.loan;
    const wHold = parameterShare * weights.parameter.hold;

    return {
        state: state,
        loan: loan,
        hold: hold,
        combined: 100 * (weights.state * state + wLoan * loan + wHold * hold)
    };
}

/**
 * Ranking-function-shaped entry point for `provengo ensemble --ranking-function=combinedCoverageFunction`.
 * Always uses COVERAGE_WEIGHTS - call coverageBreakdown(ensemble, weights) directly (e.g. from a
 * verification script) to inspect the three components or try different weights without editing
 * this function.
 *
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns Combined coverage, 0-100.
 */
function combinedCoverageFunction(ensemble) {
    return coverageBreakdown(ensemble, COVERAGE_WEIGHTS).combined;
}
