import il.ac.bgu.cs.bp.bpjs.execution.BProgramRunner;
import il.ac.bgu.cs.bp.bpjs.execution.listeners.BProgramRunnerListenerAdapter;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import testory.bprogram.PrioritizedEventsESS;
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
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Checks whether specific event sequences from bug_mapping_library_system.md chapter 3 are
 * reachable in the real library/provengo model, using a real Provengo EventSelectionStrategy
 * (PrioritizedEventsESS) to steer -- not force -- the model toward each target sequence. No
 * reimplementation of dal.js/lib_stories.js/interfaces.library.js.
 *
 * Positive reachability only. REACHED is a certain witness (the model itself offered every step).
 * NOT FOUND after all attempts is inconclusive, not proof of unreachability -- the strategy is
 * greedy and doesn't backtrack, so several attempts are tried per scenario.
 *
 * Identity tracking: steps require later actions to refer back to the SAME bound user/book/hold,
 * not just any entity of the right type -- otherwise results are unreliable once more than one
 * user/book exists, which is the normal case here.
 *
 * Progress is counted on the "chooser" event Provengo selects for each step (e.g.
 * "createLoan (valid-standard): 1/1"), not the later raw REST completion event. Completion-based
 * counting was tried and dropped: for some deletes it never showed up as observable even though
 * the operation genuinely succeeded (verified with curl). Chooser events checked out reliably
 * across every scenario here, so they're the progress signal.
 *
 * Requires the SUT running (python sut.py, localhost:23242) and Provengo.uber.jar on the
 * classpath.
 *
 * Note: the local sut.py has a one-line /reset route fix, uncommitted, pending review -- without
 * it this still works, just needs more retries per scenario.
 *
 * Run:
 *   javac -cp Provengo.uber.jar -d out src/GuidedRun.java
 *   java -cp "Provengo.uber.jar;out" GuidedRun <path-to-provengo-project>
 */
public class GuidedRun {

    /** How many selected events a scenario may go through with no step progress before this
     *  attempt is abandoned as inconclusive (see ATTEMPTS_PER_SCENARIO below). */
    private static final int MAX_EVENTS_WITHOUT_PROGRESS = 3000;
    /** Set env var GUIDEDRUN_TRACE=1 to log every selected event, chooser and concrete alike. */
    private static final boolean DEBUG_TRACE = System.getenv("GUIDEDRUN_TRACE") != null;

    private static final String SUT_RESET_URL = "http://localhost:23242/reset";

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

    /** True if this is a well-formed, success-intended chooser event for the given action
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
     * event.getName() is what we want. A single-sync action (e.g. deleteBook after the
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

    /** Chooser match: used only to steer PrioritizedEventsESS toward the desired action/identity. */
    private static boolean matchesChooser(BEvent event, Step step, Map<String, Double> bindings) {
        return chooserNameMatches(chooserName(event), step.action) && matchesIdentity(event, step, bindings);
    }

    /** Normalized request path from a concrete REST event, for trace logging. */
    private static String requestPath(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data == null) return "";
        Object raw = data.get("path");
        if (raw == null) raw = data.get("url");
        if (raw == null) return "";
        String path = String.valueOf(raw).replaceFirst("^https?://[^/]+", "");
        int q = path.indexOf('?');
        return q >= 0 ? path.substring(0, q) : path;
    }

    /** Commits this step's binds into the bindings map, once the chooser event is confirmed selected. */
    private static void applyBinds(BEvent event, Step step, Map<String, Double> bindings, Map<String, String> varType) {
        if (step.binds.isEmpty()) return;
        Map<String, Object> parameters = extractParameters(event);
        if (parameters == null) return;
        String type = entityTypeOf(step.action);
        for (String[] b : step.binds) {
            Double v = asDouble(parameters.get(b[1]));
            if (v != null) {
                bindings.put(b[0], v);
                if (type != null) varType.put(b[0], type);
            }
        }
    }

    /** Which entity type a create/delete action's own "id" identifies: user, book, or hold  */
    private static String entityTypeOf(String action) {
        if (action.equals("createUser") || action.equals("deleteUser")) return "user";
        if (action.equals("createBook") || action.equals("deleteBook")) return "book";
        if (action.equals("createHold") || action.equals("deleteHold")) return "hold";
        return null;
    }

    /**
     * True if this chooser event would delete a bound entity we still need later, and isn't the
     * deletion we actually want right now. Skips deleteLoan -- it never removes a user/book.
     */
    private static boolean isDestructiveToBindings(BEvent event, Step currentStep,
                                                     Map<String, Double> bindings, Map<String, String> varType) {
        String name = chooserName(event);
        if (name == null) return false;
        String deletedType;
        if (name.startsWith("deleteUser")) deletedType = "user";
        else if (name.startsWith("deleteBook")) deletedType = "book";
        else if (name.startsWith("deleteHold")) deletedType = "hold";
        else return false;
        if (!chooserNameMatches(name, deletedType.equals("user") ? "deleteUser" : deletedType.equals("book") ? "deleteBook" : "deleteHold")) return false;
        if (matchesChooser(event, currentStep, bindings)) return false; // this IS the deletion we intend right now

        Map<String, Object> parameters = extractParameters(event);
        if (parameters == null) return false;
        Double targetId = asDouble(parameters.get("id"));
        if (targetId == null) return false;

        for (Map.Entry<String, Double> b : bindings.entrySet()) {
            if (deletedType.equals(varType.get(b.getKey())) && targetId.equals(b.getValue())) {
                return true;
            }
        }
        return false;
    }

    /**
     * Bound vars that a later deleteUser/deleteBook step needs loan/hold-free (dal.js requires
     * both for CanDelete). deleteHold/deleteLoan aren't at risk here and are skipped.
     */
    private static java.util.Set<String> varsNeededFreeForFutureDelete(Scenario scenario, int fromStepIndex) {
        java.util.Set<String> result = new java.util.HashSet<>();
        for (int i = fromStepIndex; i < scenario.steps.size(); i++) {
            Step s = scenario.steps.get(i);
            if (s.action.equals("deleteUser") || s.action.equals("deleteBook")) {
                for (String[] req : s.requires) {
                    if (req[1].equals("id")) result.add(req[0]);
                }
            }
        }
        return result;
    }

    /**
     * True if this chooser event would create a new loan/hold that re-entangles a bound entity a
     * later step needs to delete -- e.g. re-loaning a book right after its loan was deleted, before
     * we get to delete the book. Create-side counterpart to isDestructiveToBindings().
     */
    private static boolean isReEntanglingBindings(BEvent event, Step currentStep, int currentStepIndex,
                                                    Scenario scenario, Map<String, Double> bindings) {
        String name = chooserName(event);
        if (name == null) return false;
        String action;
        if (name.startsWith("createLoan")) action = "createLoan";
        else if (name.startsWith("createHold")) action = "createHold";
        else return false;
        if (!chooserNameMatches(name, action)) return false;
        if (matchesChooser(event, currentStep, bindings)) return false; // this IS what we want right now

        java.util.Set<String> needFree = varsNeededFreeForFutureDelete(scenario, currentStepIndex);
        if (needFree.isEmpty()) return false;

        Map<String, Object> parameters = extractParameters(event);
        if (parameters == null) return false;
        Double u = asDouble(parameters.get("userId"));
        Double b = asDouble(parameters.get("bookId"));
        for (String var : needFree) {
            Double bound = bindings.get(var);
            if (bound != null && (bound.equals(u) || bound.equals(b))) return true;
        }
        return false;
    }

    // =========================================================================================
    // Harness: retries, SUT reset, run loop
    // =========================================================================================

    private static final int ATTEMPTS_PER_SCENARIO = 10;

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.err.println("Usage: java GuidedRun <path-to-library/provengo-project>");
            System.exit(1);
        }
        String projectPath = args[0];

        List<String> results = new ArrayList<>();
        for (Scenario scenario : SCENARIOS) {
            boolean reached = false;
            int attemptsUsed = 0;
            for (int attempt = 1; attempt <= ATTEMPTS_PER_SCENARIO; attempt++) {
                attemptsUsed = attempt;
                System.out.println();
                System.out.println("--- attempt " + attempt + "/" + ATTEMPTS_PER_SCENARIO + " ---");
                resetSut();
                reached = runScenario(projectPath, scenario);
                if (reached) break; // one witness is enough
            }
            String verdict = reached
                    ? "REACHED (witness found on attempt " + attemptsUsed + "/" + ATTEMPTS_PER_SCENARIO + ")"
                    : "NOT FOUND after " + ATTEMPTS_PER_SCENARIO + " attempts (inconclusive)";
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

    private static boolean runScenario(String projectPath, Scenario scenario) throws Exception {
        System.out.println();
        System.out.println("### Scenario: " + scenario.name);
        System.out.println("    Steps: " + scenario.steps.size());

        RunOptions runOptions = new RunOptions(new String[]{"run", projectPath});
        TestoryBProgramBuilder builder = new TestoryBProgramBuilder(runOptions);
        builder.setProjectDirectory(Paths.get(projectPath));
        TestoryBProgram program = builder.build();

        final AtomicInteger step = new AtomicInteger(0);
        final AtomicInteger eventsSinceProgress = new AtomicInteger(0);
        final Map<String, Double> bindings = new HashMap<>();
        final Map<String, String> varType = new HashMap<>();

        PrioritizedEventsESS ess = new PrioritizedEventsESS();
        ess.setPrioritizer(event -> {
            int i = step.get();
            if (i >= scenario.steps.size()) return 0;
            Step current = scenario.steps.get(i);

            // Steer requestOneOf toward a valid variant for the desired action/identity.
            if (matchesChooser(event, current, bindings)) return 1000;
            // Avoid volunteering to delete an already-bound entity the scenario still needs.
            if (isDestructiveToBindings(event, current, bindings, varType)) return -1000;
            // Avoid volunteering to create a new loan/hold that re-entangles a bound entity a
            // later step still needs to delete (e.g. re-loaning a book right after its loan was
            // deleted, which would re-block Book.CanDelete before we get to delete the book).
            if (isReEntanglingBindings(event, current, i, scenario, bindings)) return -1000;
            return 0;
        });
        program.setEventSelectionStrategy(ess);

        BProgramRunner runner = new BProgramRunner(program);
        runner.addListener(new BProgramRunnerListenerAdapter() {
            @Override
            public void eventSelected(BProgram bp, BEvent event) {
                if (DEBUG_TRACE) {
                    System.out.println("      [trace] " + event.getName() + " path=" + requestPath(event));
                }
                int i = step.get();
                if (i >= scenario.steps.size()) return;
                Step current = scenario.steps.get(i);

                if (matchesChooser(event, current, bindings)) {
                    applyBinds(event, current, bindings, varType);
                    int reached = step.incrementAndGet();
                    eventsSinceProgress.set(0);
                    System.out.println("  >>> step " + reached + "/" + scenario.steps.size()
                            + " reached via: " + event.getName() + "   bindings=" + bindings);
                    if (reached >= scenario.steps.size()) {
                        System.out.println("  >>> full sequence reached, halting.");
                        runner.halt();
                    }
                    return;
                }

                int c = eventsSinceProgress.incrementAndGet();
                if (c >= MAX_EVENTS_WITHOUT_PROGRESS) {
                    System.out.println("  >>> giving up: " + c + " events with no progress past step " + i);
                    runner.halt();
                }
            }
        });

        runner.run();

        int reachedSteps = step.get();
        boolean reached = reachedSteps >= scenario.steps.size();
        System.out.println("### Result: " + (reached ? "REACHED" : "NOT FOUND")
                + " (completed REST steps " + reachedSteps + "/" + scenario.steps.size() + ")");
        return reached;
    }
}
