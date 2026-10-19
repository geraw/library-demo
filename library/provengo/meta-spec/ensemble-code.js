// State coverage ranking: a Set of distinct STATE_FEATURES markers hit, not raw occurrences -
// reaching the same state many times must not score higher than reaching it once.
const STATE_FEATURES = [
    "BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE",
    "LOAN_CREATABLE", "HOLD_CREATABLE",
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
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns State-feature coverage, 0-100.
 */
function rankingFunction(ensemble) {
    return (distinctStateFeaturesHit(ensemble) / STATE_FEATURES.length) * 100;
}
