// @provengo summon ctrl

/**
 * createLoan goes through interfaces.library.js's two-phase requestOneOf, which puts the
 * descriptive variant name (e.g. "createLoan (valid-standard): 3/7") directly on event.name, so
 * any(regex) matches it. createHold/deleteUser/deleteBook go through the single-sync
 * requestOneOfDirect instead, which names the raw BEvent after the bare HTTP verb ("POST"/
 * "DELETE") and buries the descriptive name in event.data.model.name -- any(regex) alone can
 * never match those. nameMatches checks both places so one goal definition works for either path.
 */
function nameMatches(regex) {
    return { contains: function (event) {
        if (regex.test(event.name)) return true;
        var model = event.data && event.data.model;
        return !!(model && model.name && regex.test(model.name));
    }};
}

/**
 * createLoan's chooser winning is NOT the same as the loan actually being created: stillRelevant
 * is rechecked right before the real REST call fires, and a stale attempt (the user/book got
 * reassigned elsewhere while this chooser was pending) is silently aborted with no further event at
 * all -- see StrictGuidedRun.java's isTwoPhaseChooser/isRawRestSend comments, and
 * scenarios_from_ensemble.py's loan_actually_completed, which hit this exact gap empirically (0/7
 * "valid" chooser wins in one ensemble run actually completed). So instead of matching the chooser's
 * descriptive name (which fires regardless of whether the request is later aborted), this matches
 * the actual fired REST call to /loans directly -- the one event that only exists if the request
 * genuinely went out -- keyed off its parameters.description (a plain string -- see below for why
 * expectedResponseCodes itself isn't used) since every other action here is single-sync, so
 * winning the chooser IS completing; only createLoan needs this.
 *
 * Not keyed off expectedResponseCodes: that field deserializes as a Java List once read back from
 * samples.json/ensemble.json, and Rhino's Array.prototype.some/indexOf over it throws "Cannot find
 * default value for object" -- description is a plain string (like model.name above), so regex
 * matching it is safe. interfaces.library.js's requestOneOf falls back to
 * `chosen.description || selectedEvent.name` for a completed REST event's own description when the
 * variant set neither: a genuine valid completion's variant sets `description: "Create: Loan ..."`
 * (see lib_stories.js/dal.js's createDescription), while createLoan's invalid-shape variants set no
 * parameters at all, so their completions fall through to the chooser's own name, still prefixed
 * "createLoan (invalid ...)" -- distinguishable without ever touching expectedResponseCodes.
 */
function loanCompletion(descriptionPattern) {
    return { contains: function (event) {
        var d = event.data;
        if (!d || d.lib !== "REST" || d.model || d.method !== "POST") return false;
        if (!d.url || d.url.indexOf("/loans") === -1) return false;
        var params = d.parameters;
        var description = params && params.description;
        return !!(description && descriptionPattern.test(description));
    }};
}

/**
 * List of events "of interest" that we want test suites to cover.
 * A goal is met once any sampled scenario actually exercises that gate's accept or reject path.
 */
const GOALS = [
    loanCompletion(/^Create: Loan/),
    loanCompletion(/^createLoan \(invalid/),
    nameMatches(/createHold \(valid/),
    nameMatches(/createHold \(invalid/),
    nameMatches(/deleteUser \(valid/),
    nameMatches(/deleteUser \(invalid/),
    nameMatches(/deleteBook \(valid/),
    nameMatches(/deleteBook \(invalid/)
];

const makeGoals = function(){
    return [ [ any(/Howdy/), any(/Venus/) ],
             [ any(/Mars/) ],
             [ Ctrl.markEvent("Classic!") ] ];
}


/**
 * Counts how many goals are met by the passed test suite.
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @param {EventSet[]} goals Goals to be covered by the test suite.
 * @returns How many goals were met by the test suite.
 */
function countMetGoals(ensemble, goals) {
    let metGoals = 0;
    goalLoop: for (let goal of goals) {
        for ( let test of ensemble ) {
            for (let event of test) {
                if ( goal.contains(event) ) {
                    metGoals++;
                    continue goalLoop;
                }
            }
        }
    }
    return metGoals;
}

/**
 * Counts how many test scenarios in the passed ensemble cover at least one goal.
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @param {EventSet[]} goals Set of goals to be covered by the test suite.
 * @returns How many test scenarios cover at least one goal.
 */
function countGoalMeeters(ensemble, goals) {
    let meeters = 0;
    scenarioLoop: for ( let scenario of ensemble ) {
        for (let event of scenario) {
            for (let goal of goals) {
                if ( goal.contains(event) ) {
                    meeters++;
                    continue scenarioLoop;
                }
            }
        }
    }
    return meeters;
}

/**
 * Rank test suites based on how many goals the hit, and how many 
 * scenarios hit goals.
 * 
 *  Examples:
 *   - Suite covering all goals, each scenario covers at least one goal: 100
 *   - Suite covering all goals, 30% scenarios don't cover any goal: 70
 *   - Suite covering 8 out of 10 goals, each scenario cover at least one goal: 80
 *   - Suite covering 7 out of 10 goals, 5 out of 100 scenarios don't cover any goal: 66.5
 * 
 *  rank = (% covered goals) * (% goal covering scenarios) * 100
 * 
 * @param {Event[][]} ensemble Test suite to be ranked.
 * @returns Score of the test suite.
 */
function rankingFunction(ensemble) {
    
    // How many goals did `ensemble` hit?
    const metGoalsCount = countMetGoals(ensemble, GOALS);
    const metGoalsPercent = metGoalsCount/GOALS.length;

    const goalMeeters = countGoalMeeters(ensemble, GOALS);
    const goalMeetersPercent = goalMeeters/ensemble.length;

    return metGoalsPercent*goalMeetersPercent*100; // convert to human-readable percentage

}