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

// Counts how many distinct STATE_FEATURES markers (lib_stories.js's markStateFeature bthreads)
// appeared anywhere in the ensemble - a Set, so reaching the same state many times only counts
// once.
function distinctStateFeaturesHit(ensemble) {
    let hit = new Set();
    for (let test of ensemble)
        for (let event of test)
            if (event.name === "StateFeature" && event.data && STATE_FEATURES.indexOf(event.data.feature) !== -1)
                hit.add(event.data.feature);
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
