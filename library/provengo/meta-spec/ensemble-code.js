// ============================================================
// State Coverage
// ============================================================
// Measures how many distinct, hand-picked "suspicious state features" an ensemble reaches. Each
// feature corresponds to an interesting business-rule state in the SUT. Coverage is a Set of
// distinct features hit, so reaching the same state multiple times does not increase the score.
//
// HOLD_CREATABLE is excluded because it has no restricting condition and cannot discriminate
// between scenarios.
const STATE_FEATURES = [
    "LOAN_BLOCKED_VIA_USER_ONLY", "LOAN_BLOCKED_VIA_BOOK_ONLY", "LOAN_BLOCKED_VIA_BOTH",
    "BOOK_LOANED_WITH_ACTIVE_HOLD", "LOAN_AND_HOLD_SAME_PAIR",
    "BOOK_WITH_MULTIPLE_ACTIVE_HOLDS", "USER_LOAN_PLUS_HOLD_DIFFERENT_BOOKS"
];

// Counts how many distinct STATE_FEATURES markers were observed anywhere in the ensemble.
function distinctStateFeaturesHit(ensemble) {
    let hit = new Set();
    for (let test of ensemble)
        for (let event of test)
            if (event.data && event.data.lib === "Ctrl" && event.data.verb === "marker" && STATE_FEATURES.indexOf(event.data.value) !== -1)
                hit.add(event.data.value);
    return hit.size;
}

/**
 * State Coverage ranking function: the fraction of STATE_FEATURES reached by this ensemble. A
 * score below 100 reflects the marker not being observed, not necessarily that the underlying
 * state never occurred.
 *
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns State-feature coverage, 0-100.
 */
function rankingFunction(ensemble) {
    return (distinctStateFeaturesHit(ensemble) / STATE_FEATURES.length) * 100;
}

// ============================================================
// CTD Parameter Coverage (combinatorial, symmetry-reduced)
// ============================================================
// Measures combinations of parameter equivalence classes submitted to create/delete actions,
// rather than raw values, outcomes, or persistent state. Symmetry reduction treats user/book ids
// by class rather than numeric identity, so renaming an id does not create a new combination.
//
// Parameters are classified by type: string parameters (title/name) via classifyCtdStringValue,
// id parameters (userId/bookId/id) via classifyCtdIdValue. Id classification distinguishes VALID
// (a reference to an existing entity) from VALID_NONEXISTENT (a well-formed reference to an
// entity that was never created).
//
// Classification reads the submitted request body/URL directly rather than the SUT's response,
// since a single response code cannot reveal whether multiple fields were simultaneously invalid.
//
// CTD_FEASIBLE_COMBINATIONS_BY_ACTION enumerates, per action, the combinations its test
// generators can actually produce, rather than the full cross-product of classes - not every
// combination is reachable.

// Numbers below this threshold are treated as real ids; at or above it, as ids known not to
// exist (VALID_NONEXISTENT).
var CTD_NONEXISTENT_ID_THRESHOLD = 1000000;
// RTV template referencing a created entity, e.g. "@{USER3}", "@{BOOK12}", "@{HOLD5}".
var CTD_RTV_TEMPLATE_PATTERN = /^@\{[A-Z]+\d+\}$/;

/**
 * Classifies a submitted id-typed value into MISSING/NULL/WRONG_TYPE/OUT_OF_RANGE/VALID/
 * VALID_NONEXISTENT. See the section comment above for VALID vs VALID_NONEXISTENT.
 *
 * @param {*} raw
 * @returns {string}
 */
function classifyCtdIdValue(raw) {
    if (raw === undefined) return "MISSING";
    if (raw === null) return "NULL";
    if (typeof raw === "boolean") return "WRONG_TYPE";
    if (typeof raw === "object") return "WRONG_TYPE"; // plain objects and arrays alike
    if (typeof raw === "string") {
        if (CTD_RTV_TEMPLATE_PATTERN.test(raw)) return "VALID";
        if (/^-?\d+$/.test(raw)) {
            const n = parseInt(raw, 10);
            if (n <= 0) return "OUT_OF_RANGE";
            return n >= CTD_NONEXISTENT_ID_THRESHOLD ? "VALID_NONEXISTENT" : "VALID";
        }
        return "WRONG_TYPE"; // non-numeric, non-template string, e.g. "bad-id"
    }
    if (typeof raw === "number") {
        if (isNaN(raw)) return "WRONG_TYPE";
        if (raw <= 0) return "OUT_OF_RANGE";
        return raw >= CTD_NONEXISTENT_ID_THRESHOLD ? "VALID_NONEXISTENT" : "VALID";
    }
    return "WRONG_TYPE";
}

/**
 * Classifies a submitted string-typed value into MISSING/NULL/WRONG_TYPE/EMPTY/VALID. No
 * existing/nonexistent distinction - title/name aren't entity references.
 *
 * @param {*} raw
 * @returns {string}
 */
function classifyCtdStringValue(raw) {
    if (raw === undefined) return "MISSING";
    if (raw === null) return "NULL";
    if (typeof raw !== "string") return "WRONG_TYPE";
    return raw === "" ? "EMPTY" : "VALID";
}

// Per-action factor spec: where to read submitted value(s) from (JSON body for create actions;
// trailing URL path segments for delete actions), and which classifier applies, in field order.
var CTD_ACTION_SPEC = {
    createBook: { kind: "body", fields: ["title"], classifiers: [classifyCtdStringValue] },
    createUser: { kind: "body", fields: ["name"], classifiers: [classifyCtdStringValue] },
    createLoan: { kind: "body", fields: ["userId", "bookId"], classifiers: [classifyCtdIdValue, classifyCtdIdValue] },
    createHold: { kind: "body", fields: ["userId", "bookId"], classifiers: [classifyCtdIdValue, classifyCtdIdValue] },
    deleteBook: { kind: "pathTail", count: 1, classifiers: [classifyCtdIdValue] },
    deleteUser: { kind: "pathTail", count: 1, classifiers: [classifyCtdIdValue] },
    deleteHold: { kind: "pathTail", count: 1, classifiers: [classifyCtdIdValue] },
    deleteLoan: { kind: "pathTail", count: 2, classifiers: [classifyCtdIdValue, classifyCtdIdValue] }
};

/**
 * Reads the raw submitted value(s) for an action's factors off the event - data.body (parsed) for
 * create actions, or trailing URL path segment(s) for delete actions. Returns null if the event
 * doesn't carry what this spec needs.
 *
 * @param {Event} event
 * @param {{kind:string, fields?:string[], count?:number}} spec
 * @returns {Array<*>|null}
 */
function ctdExtractRawValues(event, spec) {
    const d = event && event.data;
    if (!d) return null;
    if (spec.kind === "body") {
        if (typeof d.body !== "string") return null;
        let parsed;
        try { parsed = JSON.parse(d.body); } catch (e) { return null; }
        if (!parsed || typeof parsed !== "object") return null;
        return spec.fields.map(function (f) { return parsed[f]; });
    }
    // pathTail
    if (typeof d.url !== "string") return null;
    const segments = d.url.split("/").filter(function (s) { return s.length > 0; });
    if (segments.length < spec.count) return null;
    return segments.slice(segments.length - spec.count);
}

/**
 * Classifies an event into an "action:class1[,class2]" CTD combination string, or null if it's
 * not a recognized create/delete action, isn't in CTD_ACTION_SPEC, or its value(s) can't be read.
 *
 * @param {Event} event
 * @returns {string|null}
 */
function classifyCtdCombination(event) {
    const d = event && event.data;
    const name = d && d.model && typeof d.model.name === "string" ? d.model.name : null;
    if (!name) return null;

    const parenIdx = name.indexOf(" (");
    if (parenIdx === -1) return null;
    const action = name.substring(0, parenIdx);
    const spec = CTD_ACTION_SPEC[action];
    if (!spec) return null;

    const raws = ctdExtractRawValues(event, spec);
    if (raws === null) return null;

    const classes = raws.map(function (v, i) { return spec.classifiers[i](v); });
    return action + ":" + classes.join(",");
}

// The feasible-combination universe for each action, enumerated directly rather than computed as
// a cross-product of classes, since not every combination is reachable by the test generators.
var CTD_FEASIBLE_COMBINATIONS_BY_ACTION = {
    createBook: ["VALID", "MISSING", "WRONG_TYPE", "NULL", "EMPTY"],
    createUser: ["VALID", "MISSING", "WRONG_TYPE", "NULL", "EMPTY"],
    // (userId, bookId); includes combinations where one or both ids are VALID_NONEXISTENT.
    createLoan: [
        "VALID,VALID", "VALID,MISSING", "MISSING,VALID", "MISSING,MISSING",
        "WRONG_TYPE,VALID", "VALID,WRONG_TYPE", "WRONG_TYPE,WRONG_TYPE",
        "NULL,VALID", "VALID,NULL", "OUT_OF_RANGE,VALID", "VALID,OUT_OF_RANGE",
        "VALID_NONEXISTENT,VALID", "VALID_NONEXISTENT,MISSING", "VALID_NONEXISTENT,WRONG_TYPE",
        "VALID_NONEXISTENT,NULL", "VALID_NONEXISTENT,OUT_OF_RANGE",
        "VALID,VALID_NONEXISTENT", "MISSING,VALID_NONEXISTENT", "WRONG_TYPE,VALID_NONEXISTENT",
        "NULL,VALID_NONEXISTENT", "OUT_OF_RANGE,VALID_NONEXISTENT",
        "VALID_NONEXISTENT,VALID_NONEXISTENT"
    ],
    // (userId, bookId); structurally identical to createLoan.
    createHold: [
        "VALID,VALID", "VALID,MISSING", "MISSING,VALID", "MISSING,MISSING",
        "WRONG_TYPE,VALID", "VALID,WRONG_TYPE", "WRONG_TYPE,WRONG_TYPE",
        "NULL,VALID", "VALID,NULL", "OUT_OF_RANGE,VALID", "VALID,OUT_OF_RANGE",
        "VALID_NONEXISTENT,VALID", "VALID_NONEXISTENT,MISSING", "VALID_NONEXISTENT,WRONG_TYPE",
        "VALID_NONEXISTENT,NULL", "VALID_NONEXISTENT,OUT_OF_RANGE",
        "VALID,VALID_NONEXISTENT", "MISSING,VALID_NONEXISTENT", "WRONG_TYPE,VALID_NONEXISTENT",
        "NULL,VALID_NONEXISTENT", "OUT_OF_RANGE,VALID_NONEXISTENT",
        "VALID_NONEXISTENT,VALID_NONEXISTENT"
    ],
    // Single path id; MISSING/NULL/EMPTY aren't feasible for a URL path segment.
    deleteBook: ["VALID", "WRONG_TYPE", "OUT_OF_RANGE", "VALID_NONEXISTENT"],
    deleteUser: ["VALID", "WRONG_TYPE", "OUT_OF_RANGE", "VALID_NONEXISTENT"],
    deleteHold: ["VALID", "WRONG_TYPE", "OUT_OF_RANGE", "VALID_NONEXISTENT"],
    // (userId, bookId) as URL path parameters; no single-field-nonexistent combinations here.
    deleteLoan: [
        "VALID,VALID", "WRONG_TYPE,VALID", "VALID,WRONG_TYPE",
        "OUT_OF_RANGE,VALID", "VALID,OUT_OF_RANGE", "VALID_NONEXISTENT,VALID_NONEXISTENT"
    ]
};

var CTD_UNIVERSE = (function () {
    const units = [];
    const actions = Object.keys(CTD_FEASIBLE_COMBINATIONS_BY_ACTION);
    for (let i = 0; i < actions.length; i++) {
        const action = actions[i];
        const combos = CTD_FEASIBLE_COMBINATIONS_BY_ACTION[action];
        for (let j = 0; j < combos.length; j++) units.push(action + ":" + combos[j]);
    }
    return units;
})();
var CTD_UNIVERSE_SET = new Set(CTD_UNIVERSE);
var CTD_UNIVERSE_SIZE = CTD_UNIVERSE.length; // 72

/**
 * Distinct feasible CTD combinations hit (Set - repeats count once), plus any classified
 * combination OUTSIDE the declared universe - diagnostic only, never counted in the score. A
 * non-empty outsideUniverse would mean the enumeration is missing a generator case.
 *
 * @param {Event[][]} ensemble Test suite to be measured.
 * @returns {{hit: Set<string>, outsideUniverse: Set<string>}}
 */
function ctdParameterCoverageDetails(ensemble) {
    const hit = new Set();
    const outsideUniverse = new Set();
    for (let test of ensemble) {
        for (let event of test) {
            const combo = classifyCtdCombination(event);
            if (combo === null) continue;
            if (CTD_UNIVERSE_SET.has(combo)) hit.add(combo);
            else outsideUniverse.add(combo);
        }
    }
    return { hit: hit, outsideUniverse: outsideUniverse };
}

/**
 * CTD Parameter Coverage, 0-100: fraction of the fixed 72-unit feasible-combination universe
 * attempted by this ensemble (accepted or rejected). Deterministic, monotonic, 0 for an empty
 * ensemble.
 *
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns CTD Parameter coverage, 0-100.
 */
function ctdParameterCoverageFunction(ensemble) {
    return (ctdParameterCoverageDetails(ensemble).hit.size / CTD_UNIVERSE_SIZE) * 100;
}

/**
 * Reporting breakdown, NOT the ranking score itself - per-action hit/missing combination lists
 * plus outside-universe classifications. Not used by ctdParameterCoverageFunction; call
 * separately for inspection (same relationship coverageBreakdownV3 has to rankingFunction).
 *
 * @param {Event[][]} ensemble Test suite to be measured.
 * @returns {{unitsHit:number, universeSize:number, perAction:Object<string,{hit:string[],
 *   missing:string[], universeSize:number}>, outsideUniverse:string[]}}
 */
function ctdParameterCoverageBreakdown(ensemble) {
    const details = ctdParameterCoverageDetails(ensemble);
    const actions = Object.keys(CTD_FEASIBLE_COMBINATIONS_BY_ACTION);
    const perAction = {};
    for (let i = 0; i < actions.length; i++) {
        const action = actions[i];
        const combos = CTD_FEASIBLE_COMBINATIONS_BY_ACTION[action];
        const hitCombos = [];
        const missingCombos = [];
        for (let j = 0; j < combos.length; j++) {
            const unit = action + ":" + combos[j];
            (details.hit.has(unit) ? hitCombos : missingCombos).push(combos[j]);
        }
        perAction[action] = { hit: hitCombos, missing: missingCombos, universeSize: combos.length };
    }
    return {
        unitsHit: details.hit.size,
        universeSize: CTD_UNIVERSE_SIZE,
        perAction: perAction,
        outsideUniverse: Array.from(details.outsideUniverse)
    };
}

// ============================================================
// Combined Ranking (active)
// ============================================================
// Combines State Coverage and CTD Parameter Coverage into a single weighted score. This is the
// active ranking function for `provengo ensemble --ranking-function=combinedCoverageFunctionV3`.

var COVERAGE_WEIGHTS_V3 = {
    state: 0.50,
    parameter: 0.50
};

function validateCoverageWeightsV3(weights) {
    if (!weights || typeof weights !== "object") {
        throw new Error("combinedCoverageFunctionV3: weights must be an object");
    }
    const state = weights.state;
    if (typeof state !== "number" || isNaN(state) || state < 0 || state > 1) {
        throw new Error("combinedCoverageFunctionV3: weight 'state' must be a number in [0,1], got " + state);
    }
    const parameter = weights.parameter;
    if (typeof parameter !== "number" || isNaN(parameter) || parameter < 0 || parameter > 1) {
        throw new Error("combinedCoverageFunctionV3: weight 'parameter' must be a number in [0,1], got " + parameter);
    }
    if (Math.abs(state + parameter - 1) > 1e-9) {
        throw new Error("combinedCoverageFunctionV3: weights.state + weights.parameter must sum to 1, got " + (state + parameter));
    }
}

/**
 * @param {Event[][]} ensemble Test suite to be measured.
 * @param {{state:number, parameter:number}} [weights] Defaults to COVERAGE_WEIGHTS_V3.
 * @returns {{state:number, parameter:number, combined:number}} state/parameter in [0,1];
 *   combined in [0,100].
 */
function coverageBreakdownV3(ensemble, weights) {
    weights = weights || COVERAGE_WEIGHTS_V3;
    validateCoverageWeightsV3(weights);

    const state = distinctStateFeaturesHit(ensemble) / STATE_FEATURES.length;
    const parameter = ctdParameterCoverageFunction(ensemble) / 100;

    return {
        state: state,
        parameter: parameter,
        combined: 100 * (weights.state * state + weights.parameter * parameter)
    };
}

/**
 * Ranking-function entry point for
 * `provengo ensemble --ranking-function=combinedCoverageFunctionV3`.
 *
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns {number} Combined coverage (V3), 0-100.
 */
function combinedCoverageFunctionV3(ensemble) {
    return coverageBreakdownV3(ensemble, COVERAGE_WEIGHTS_V3).combined;
}
