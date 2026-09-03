import il.ac.bgu.cs.bp.bpjs.execution.BProgramRunner;
import il.ac.bgu.cs.bp.bpjs.execution.listeners.BProgramRunnerListenerAdapter;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import il.ac.bgu.cs.bp.bpjs.model.BProgramSyncSnapshot;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.EventSelectionResult;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.EventSelectionStrategy;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.SimpleEventSelectionStrategy;
import testory.bprogram.TestoryBProgram;
import testory.bprogram.TestoryBProgramBuilder;
import testory.configs.RunOptions;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * Checks whether specific event sequences from bug_mapping_library_system.md chapter 3 are
 * reachable in the real library/provengo model, using a real Provengo EventSelectionStrategy --
 * not a reimplementation of dal.js/lib_stories.js/interfaces.library.js.
 *
 * Strict, single-pass version agreed with the advisor: no PrioritizedEventsESS, no priority
 * scores, no destructive/re-entangling avoidance, no multi-attempt retry. At each step, this
 * asks the real model for exactly the next action in a hand-written scenario. If that action is
 * on offer this synchronization round, it is forced (not merely favored). If it is NOT on offer
 * -- no waiting, no tolerance for anything happening "in between" -- the run stops right there
 * and that step is reported as the failure point.
 *
 * This replaces the earlier greedy-with-retries version (steered with PrioritizedEventsESS,
 * whose "NOT FOUND" was only inconclusive, not a real failure point). The trade-off: this
 * assumes each scenario's next action becomes selectable on the very next round after its
 * precondition is met, with no other necessary event required first -- true now that every
 * create/delete action in interfaces.library.js uses the single-sync requestOneOfDirect pattern
 * (see that file's migration commit). verifyBookDetailExists/verifyLoanExists deliberately still
 * use the older two-phase requestOneOf/getOneOf path (they need a stillRelevant recheck between
 * chooser-win and REST-send), but no scenario here calls either.
 *
 * chooserName(event) reads the descriptive name from data.variant.name when present (every
 * migrated single-sync action), falling back to the raw event name otherwise -- see its own doc
 * comment.
 *
 * Identity tracking: steps require later actions to refer back to the SAME bound user/book/hold,
 * not just any entity of the right type -- otherwise results are unreliable once more than one
 * user/book exists, which is the normal case here.
 *
 * Requires the SUT running (python sut.py, localhost:23242) and Provengo.uber.jar on the
 * classpath.
 *
 * Run:
 *   javac -cp Provengo.uber.jar -d out src/GuidedRun.java
 *   java -cp "Provengo.uber.jar;out" GuidedRun <path-to-provengo-project>
 *
 * Set env var GUIDEDRUN_TRACE=1 to log what was actually on offer whenever a step's target
 * action wasn't among it (diagnostic only -- does not change pass/fail behavior).
 */
public class GuidedRun {

    // =========================================================================================
    // Step / Scenario model
    // =========================================================================================

    /**
     * One step: an action name plus identity constraints on that action's event parameters.
     * - require(var, field): must match a value already bound by an earlier step.
     * - bind(var, field): remember this value under a name for later steps.
     * - bindDistinctFrom(var, field, others...): bind, but must differ from the given earlier vars.
     */
    static class Step {
        final String action;
        final List<String[]> requires = new ArrayList<>();   // {var, field}
        final List<String[]> binds = new ArrayList<>();      // {var, field}
        final Map<String, List<String>> distinctFrom = new HashMap<>(); // field-bound var -> other vars it must differ from

        Step(String action) {
            this.action = action;
        }

        Step require(String var, String field) {
            requires.add(new String[]{var, field});
            return this;
        }

        Step bind(String var, String field) {
            binds.add(new String[]{var, field});
            return this;
        }

        Step bindDistinctFrom(String var, String field, String... others) {
            binds.add(new String[]{var, field});
            distinctFrom.put(var, List.of(others));
            return this;
        }
    }

    static class Scenario {
        final String name;
        final List<Step> steps;

        Scenario(String name, List<Step> steps) {
            this.name = name;
            this.steps = steps;
        }
    }

    // Shorthand so the scenario table below reads close to plain English.
    private static Step step(String action) {
        return new Step(action);
    }

    /**
     * Sequences from bug_mapping_library_system.md chapter 3 that are expected to be reachable.
     * Rows whose correct outcome is a BLOCK (e.g. 3.7) are out of scope for this checker.
     */
    private static final List<Scenario> SCENARIOS = List.of(

            new Scenario("3.1 User->Book->Hold->Loan (hold survives loan)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId")
            )),

            // Hold by user A, then a loan on the SAME book by a DIFFERENT user B -- there is no
            // real logical connection between hold and loan today, so this should succeed.
            new Scenario("3.2 Hold by user A -> Loan on the SAME book by a DIFFERENT user B", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user1", "userId").require("book", "bookId"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createLoan").require("user2", "userId").require("book", "bookId")
            )),

            new Scenario("3.3 Loan->DeleteLoan(return)->DeleteBook", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteBook").require("book", "id")
            )),

            new Scenario("3.4 Loan->DeleteLoan->Loan again (same pair)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteLoan").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId")
            )),

            new Scenario("3.5 Two DIFFERENT users hold the SAME book (waiting queue)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user1", "userId").require("book", "bookId"),
                    step("createHold").require("user2", "userId").require("book", "bookId")
            )),

            // Book already loaned to user A, then a DIFFERENT user B successfully places a hold on
            // the SAME book -- an existing loan must not block a new hold (legitimate queueing).
            new Scenario("3.6 Book already loaned to A -> user B can still hold the SAME book", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user1", "userId").require("book", "bookId"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createHold").require("user2", "userId").require("book", "bookId")
            )),

            // 3.7 (delete a user who only has a hold -- correctly expected to be BLOCKED) is
            // intentionally excluded: this checker only verifies expected-reachable sequences.

            // deleteHold has no CanDelete-style gate in dal.js -- deleting THIS hold should succeed
            // even while the SAME user/book also has an active loan.
            new Scenario("3.10 Hold->Loan->DeleteHold (SAME hold deletable despite coexisting loan)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId").bind("hold", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteHold").require("hold", "id")
            )),

            new Scenario("3.11 Full happy path, one continuous chain, same entities throughout", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId").bind("hold", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteHold").require("hold", "id"),
                    step("deleteBook").require("book", "id"),
                    step("deleteUser").require("user", "id")
            )),

            // Now precise (previously "approximated" by action name only): User1 holds book X,
            // User2 holds the SAME book X, then the loan specifically goes to User2.
            new Scenario("3.16 Two users hold the SAME book, loan goes to the SECOND holder", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user1", "userId").require("book", "bookId"),
                    step("createHold").require("user2", "userId").require("book", "bookId"),
                    step("createLoan").require("user2", "userId").require("book", "bookId")
            )),

            // Two independent chains that must NOT reuse each other's user/book.
            new Scenario("3.18 Two independent User+Book+Hold+Loan chains, no cross-contamination", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createHold").require("user2", "userId").require("book2", "bookId"),
                    step("createLoan").require("user2", "userId").require("book2", "bookId")
            ))
    );

    // =========================================================================================
    // Matching
    // =========================================================================================

    /** Matches a deliberately-nonexistent id (generateMissingId(): existingId + 1_000_000_000). */
    private static final java.util.regex.Pattern NONEXISTENT_ID = java.util.regex.Pattern.compile("\\d{9,}");

    /** True if this is a well-formed, success-intended chooser name for the given action
     *  (e.g. "createLoan (valid-standard): 1/1", not an "(invalid - ...)" or missing-id variant). */
    private static boolean chooserNameMatches(String eventName, String action) {
        if (eventName == null) return false;
        return eventName.startsWith(action)
                && eventName.contains("valid")
                && !eventName.contains("invalid")
                && !NONEXISTENT_ID.matcher(eventName).find();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : null;
    }

    private static Map<String, Object> eventData(BEvent event) {
        return asMap(event == null ? null : event.getData());
    }

    /**
     * The event's chooser-style name. A classic two-phase action (chooser sync, then a separate
     * REST sync) names its chooser event descriptively (e.g. "deleteBook (valid): 1"), so
     * event.getName() is what we want. A single-sync action (every create/delete action after the
     * requestOneOfDirect migration -- see interfaces.library.js) offers the concrete REST event
     * itself, named after the HTTP verb ("DELETE"), with the descriptive name carried instead at
     * data.variant.name -- same place extractParameters() already looks for parameters.
     */
    private static String chooserName(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data != null) {
            Map<String, Object> variant = asMap(data.get("variant"));
            if (variant != null && variant.get("name") != null) {
                return String.valueOf(variant.get("name"));
            }
        }
        return event.getName();
    }

    /**
     * Identity fields (id/userId/bookId/...) of an event -- from event.data.variant.parameters
     * for a chooser event, or event.data.parameters directly for a concrete REST event.
     */
    private static Map<String, Object> extractParameters(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data == null) return null;
        Map<String, Object> direct = asMap(data.get("parameters"));
        if (direct != null) return direct;
        Map<String, Object> variant = asMap(data.get("variant"));
        if (variant == null) return null;
        return asMap(variant.get("parameters"));
    }

    private static Double asDouble(Object o) {
        if (o instanceof Number) return ((Number) o).doubleValue();
        return null;
    }

    /** Shared identity test, usable against both chooser and concrete REST events. */
    private static boolean matchesIdentity(BEvent event, Step step, Map<String, Double> bindings) {
        if (step.requires.isEmpty() && step.distinctFrom.isEmpty()) return true;

        Map<String, Object> parameters = extractParameters(event);
        if (parameters == null) return false;

        for (String[] req : step.requires) {
            String var = req[0], field = req[1];
            Double bound = bindings.get(var);
            Double actual = asDouble(parameters.get(field));
            if (bound == null || actual == null || !bound.equals(actual)) return false;
        }
        for (Map.Entry<String, List<String>> e : step.distinctFrom.entrySet()) {
            String var = e.getKey();
            String field = step.binds.stream().filter(b -> b[0].equals(var)).map(b -> b[1]).findFirst().orElse(null);
            if (field == null) continue;
            Double candidate = asDouble(parameters.get(field));
            if (candidate == null) return false;
            for (String other : e.getValue()) {
                Double otherVal = bindings.get(other);
                if (otherVal != null && otherVal.equals(candidate)) return false;
            }
        }
        return true;
    }

    /** Is this event a well-formed, success-intended offer of the step's action with matching identity? */
    private static boolean matchesChooser(BEvent event, Step step, Map<String, Double> bindings) {
        return chooserNameMatches(chooserName(event), step.action) && matchesIdentity(event, step, bindings);
    }

    /** Commits this step's binds into the bindings map, once the chooser event is confirmed selected. */
    private static void applyBinds(BEvent event, Step step, Map<String, Double> bindings) {
        if (step.binds.isEmpty()) return;
        Map<String, Object> parameters = extractParameters(event);
        if (parameters == null) return;
        for (String[] b : step.binds) {
            Double v = asDouble(parameters.get(b[1]));
            if (v != null) bindings.put(b[0], v);
        }
    }

    // =========================================================================================
    // Harness: strict single-pass run, no retries
    // =========================================================================================

    private static final String SUT_RESET_URL = "http://localhost:23242/reset";

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.err.println("Usage: java GuidedRun <path-to-library/provengo-project>");
            System.exit(1);
        }
        String projectPath = args[0];

        List<String> results = new ArrayList<>();
        for (Scenario scenario : SCENARIOS) {
            resetSut();
            RunResult result = runScenario(projectPath, scenario);
            String verdict = result.reached
                    ? "REACHED"
                    : "FAILED at step " + (result.reachedSteps + 1) + "/" + scenario.steps.size()
                            + " (" + result.failedAction + " was not offered this round)";
            results.add(verdict + "  " + scenario.name);
        }

        System.out.println();
        System.out.println("=========== RESULTS ===========");
        for (String r : results) {
            System.out.println(r);
        }
    }

    private static void resetSut() {
        try {
            URL url = new URL(SUT_RESET_URL);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);
            try (OutputStream os = conn.getOutputStream()) {
                os.write("{}".getBytes(StandardCharsets.UTF_8));
            }
            int code = conn.getResponseCode();
            if (code != 200) {
                System.out.println("  (note: SUT has no /reset endpoint (HTTP " + code + ") -- state accumulates across attempts, harmless here since ids never repeat)");
            }
            conn.disconnect();
        } catch (Exception e) {
            System.out.println("  (warning: could not reach SUT before scenario: " + e.getMessage()
                    + " -- is `python sut.py` running on localhost:23242?)");
        }
    }

    static class RunResult {
        boolean reached;
        int reachedSteps;
        String failedAction;
    }

    private static RunResult runScenario(String projectPath, Scenario scenario) throws Exception {
        System.out.println();
        System.out.println("### Scenario: " + scenario.name);
        System.out.println("    Steps: " + scenario.steps.size());

        RunOptions runOptions = new RunOptions(new String[]{"run", projectPath});
        TestoryBProgramBuilder builder = new TestoryBProgramBuilder(runOptions);
        builder.setProjectDirectory(Paths.get(projectPath));
        TestoryBProgram program = builder.build();

        final int[] step = {0};
        final Map<String, Double> bindings = new HashMap<>();
        final SimpleEventSelectionStrategy base = new SimpleEventSelectionStrategy();

        // The whole point of the simplification: no priority scores, no avoidance heuristics.
        // Each round, offer ONLY the exact next action (if the model happens to offer it too).
        // Nothing else is ever selectable -- not favored over, literally excluded.
        EventSelectionStrategy strict = new EventSelectionStrategy() {
            @Override
            public Set<BEvent> selectableEvents(BProgramSyncSnapshot snapshot) {
                int i = step[0];
                if (i >= scenario.steps.size()) return java.util.Collections.emptySet();
                Step current = scenario.steps.get(i);
                Set<BEvent> offered = base.selectableEvents(snapshot);
                Set<BEvent> matches = new HashSet<>();
                for (BEvent e : offered) {
                    if (matchesChooser(e, current, bindings)) matches.add(e);
                }
                if (matches.isEmpty() && System.getenv("GUIDEDRUN_TRACE") != null) {
                    List<String> names = new ArrayList<>();
                    for (BEvent e : offered) names.add(chooserName(e));
                    java.util.Collections.sort(names);
                    System.out.println("      [trace] wanted " + current.action + ", offered this round ("
                            + offered.size() + "): " + names);
                }
                return matches;
            }

            @Override
            public Optional<EventSelectionResult> select(BProgramSyncSnapshot snapshot, Set<BEvent> selectableEvents) {
                // Empty here means the target action was not on offer this round -- stop, don't
                // wait for a future round and don't let anything else happen in between.
                if (selectableEvents.isEmpty()) return Optional.empty();
                return Optional.of(new EventSelectionResult(selectableEvents.iterator().next()));
            }
        };
        program.setEventSelectionStrategy(strict);

        BProgramRunner runner = new BProgramRunner(program);
        runner.addListener(new BProgramRunnerListenerAdapter() {
            @Override
            public void eventSelected(BProgram bp, BEvent event) {
                int i = step[0];
                if (i >= scenario.steps.size()) return;
                Step current = scenario.steps.get(i);
                if (matchesChooser(event, current, bindings)) {
                    applyBinds(event, current, bindings);
                    int reached = step[0] + 1;
                    step[0] = reached;
                    System.out.println("  >>> step " + reached + "/" + scenario.steps.size()
                            + " reached via: " + chooserName(event) + "   bindings=" + bindings);
                    if (reached >= scenario.steps.size()) {
                        System.out.println("  >>> full sequence reached, halting.");
                        runner.halt();
                    }
                }
            }
        });

        runner.run();

        RunResult result = new RunResult();
        result.reachedSteps = step[0];
        result.reached = result.reachedSteps >= scenario.steps.size();
        if (!result.reached) {
            result.failedAction = scenario.steps.get(result.reachedSteps).action;
        }
        System.out.println("### Result: " + (result.reached
                ? "REACHED"
                : "FAILED at step " + (result.reachedSteps + 1) + "/" + scenario.steps.size()
                        + " (" + result.failedAction + " was not offered this round)"));
        return result;
    }
}
