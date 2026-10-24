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
