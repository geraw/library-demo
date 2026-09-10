import il.ac.bgu.cs.bp.bpjs.execution.BProgramRunner;
import il.ac.bgu.cs.bp.bpjs.execution.listeners.BProgramRunnerListenerAdapter;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import il.ac.bgu.cs.bp.bpjs.model.BProgramSyncSnapshot;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.AbstractEventSelectionStrategy;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.EventSelectionResult;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.SimpleEventSelectionStrategy;
import testory.bprogram.Actuator;
import testory.bprogram.TestoryBProgram;
import testory.bprogram.TestoryBProgramBuilder;
import testory.configs.RunOptions;
import testory.libraries.TestoryLibrary;

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
 * Single-pass version agreed with the advisor: no PrioritizedEventsESS, no priority scores, no
 * multi-attempt retry. At each step, this asks the real model for exactly the next action in a
 * hand-written scenario, and selects it directly (not merely favored) whenever it's on offer.
 *
 * At each step, only the exact target action is selectable -- no fallback to other events, no
 * guards, no retries. An earlier version of this checker needed both (selecting some other safe
 * event when the target wasn't on offer yet, to give the model's own Context-update machinery a
 * chance to run), because a real bug in the model at the time -- a mutual block() deadlock between
 * createLoan/createHold and deleteUser/deleteBook -- made the target action never become
 * selectable on its own. That bug has since been fixed upstream, so the strict, fallback-free
 * approach below now works directly.
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
 *   javac -cp Provengo.uber.jar -d out src/StrictGuidedRun.java
 *   java -cp "Provengo.uber.jar;out" StrictGuidedRun <path-to-provengo-project>
 *
 * Set env var GUIDEDRUN_TRACE=1 to log what was actually on offer whenever a step's target
 * action wasn't among it (diagnostic only -- does not change pass/fail behavior).
 */
public class StrictGuidedRun {

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
        /** True (the default): this sequence is expected to be REACHABLE. False: it's expected
         *  to be BLOCKED -- reaching it anyway is the bug. */
        final boolean expectReached;

        Scenario(String name, List<Step> steps) {
            this(name, steps, true);
        }

        Scenario(String name, List<Step> steps, boolean expectReached) {
            this.name = name;
            this.steps = steps;
            this.expectReached = expectReached;
        }
    }

    /** Marks a scenario as expected to be BLOCKED, not reachable -- REACHED is the bug here. */
    private static Scenario expectBlocked(String name, List<Step> steps) {
        return new Scenario(name, steps, false);
    }

    // Shorthand so the scenario table below reads close to plain English.
    private static Step step(String action) {
        return new Step(action);
    }

    /**
     * Sequences from bug_mapping_library_system.md chapter 3/4, plus additional edge cases. Most
     * are expected to be REACHABLE; a few (built with expectBlocked) are expected to be BLOCKED,
     * so REACHED is the bug for those instead.
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
            )),

            // Inspired by 3.9: delete user1 after they return their own loan, while a completely
            // separate user2/book2 loan stays active throughout -- the delete-eligibility check
            // must key off user1's own loan status, not get confused by user2's still-active one.
            new Scenario("3.9-variant Delete user after return, unrelated second loan stays active", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createLoan").require("user2", "userId").require("book2", "bookId"),
                    step("deleteLoan").require("user1", "userId").require("book1", "bookId"),
                    step("deleteUser").require("user1", "id")
            )),

            // Inspired by 3.12: a book changes hands after being returned -- user1 borrows and
            // returns it, then a DIFFERENT user2 successfully borrows the SAME book.
            new Scenario("3.12-variant Book changes hands after return (different borrower)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user1", "userId").require("book", "bookId"),
                    step("deleteLoan").require("user1", "userId").require("book", "bookId"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createLoan").require("user2", "userId").require("book", "bookId")
            )),

            // Inspired by 4.9: delete a hold, then create a completely fresh hold for a DIFFERENT
            // user/book pair -- the new hold must reflect the new pair, not leftover data from the
            // deleted one.
            new Scenario("4.9-variant New hold for a different pair after deleting an old one", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold", "id"),
                    step("deleteHold").require("hold", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createHold").require("user2", "userId").require("book2", "bookId")
            )),

            // Inspired by 4.11: create and delete a user, then create and delete a completely
            // separate second user -- no contamination between the two cycles.
            new Scenario("4.11-variant Create/delete a user, then create/delete a different user", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("deleteUser").require("user2", "id")
            )),

            // Extreme/edge cases below, added to stress the model beyond the original chapter-3
            // rows: deeper queues, repeated cycles, and every CanDelete gate combo dal.js actually
            // enforces (or deliberately does NOT enforce, per hold/loan being logically
            // unconnected today).

            // 3.1-extreme: hold and loan are logically unconnected in dal.js today (Hold has no
            // CanDelete-style gate at all), so a user must be able to place a hold on a book they
            // ALREADY have on loan.
            new Scenario("3.1-extreme User places a Hold on a book they already have on Loan", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("createHold").require("user", "userId").require("book", "bookId")
            )),

            // 3.16-extreme: extend the two-deep queue to three holders, then the loan still goes
            // to whichever holder is requested -- no FIFO enforcement anywhere in dal.js.
            new Scenario("3.16-extreme Three-deep hold queue on the same book, loan goes to the THIRD holder", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createUser").bindDistinctFrom("user3", "id", "user1", "user2"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user1", "userId").require("book", "bookId"),
                    step("createHold").require("user2", "userId").require("book", "bookId"),
                    step("createHold").require("user3", "userId").require("book", "bookId"),
                    step("createLoan").require("user3", "userId").require("book", "bookId")
            )),

            // 4.5-variant: three holds on the same book by different users, deleted in REVERSE
            // (LIFO) order -- deleteHold has no ordering assumption in dal.js, so every order works.
            new Scenario("4.5-variant Three holds on the same book, deleted in LIFO order", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createUser").bindDistinctFrom("user3", "id", "user1", "user2"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user1", "userId").require("book", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book", "bookId").bind("hold2", "id"),
                    step("createHold").require("user3", "userId").require("book", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold3", "id"),
                    step("deleteHold").require("hold2", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            // 4.11-extreme: three sequential create/delete cycles, each on a distinct user, no
            // cross-contamination across any pair of them.
            new Scenario("4.11-extreme Three sequential create/delete user cycles, no cross-contamination", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bindDistinctFrom("user3", "id", "user1", "user2"),
                    step("deleteUser").require("user3", "id")
            )),

            // 3.7: a user who only has a hold (no loan) must still be blocked from deletion --
            // User.CanDelete in dal.js requires no active loan AND no active hold.
            expectBlocked("3.7 Delete a user who only has a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("deleteUser").require("user", "id")
            )),

            // 2.4.3-extreme: a user with an active LOAN (no hold) must also be blocked from
            // deletion -- User.CanDelete requires no loan too, not just no hold.
            expectBlocked("2.4.3-extreme Delete a user who has an active Loan (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteUser").require("user", "id")
            )),

            // 2.7.3-extreme: the book-side mirror of 3.7 -- a book that only has a Hold (no loan)
            // must still be blocked from deletion, since Book.CanDelete also checks !hasHoldForBook.
            expectBlocked("2.7.3-extreme Delete a book that only has a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("deleteBook").require("book", "id")
            )),

            // 2.7.4-extreme: the book-side mirror of 2.4.3-extreme -- a book with an active Loan
            // must be blocked from deletion.
            expectBlocked("2.7.4-extreme Delete a book that has an active Loan (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteBook").require("book", "id")
            )),

            // Combined-gate extreme: a user with BOTH an active loan AND an active hold must still
            // be blocked from deletion (either condition alone is already enough).
            expectBlocked("Combined-gate Delete a user who has BOTH an active Loan and a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteUser").require("user", "id")
            )),

            // Combined-gate extreme: the book-side mirror -- a book with BOTH an active loan AND
            // an active hold must still be blocked from deletion.
            expectBlocked("Combined-gate Delete a book that has BOTH an active Loan and a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteBook").require("book", "id")
            )),

            // 3.17: once a book is fully deleted, no loan should ever be creatable for that bookId
            // again -- dal.js removes the UserBook pair on deleteBookEntity, so no "ghost" loan for
            // a deleted book should ever become reachable.
            expectBlocked("3.17 Loan attempt for a bookId that was already deleted (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("deleteBook").require("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId")
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
            Map<String, Object> variant = asMap(data.get("model"));
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
        Map<String, Object> variant = asMap(data.get("model"));
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
            if (v != null) {
                bindings.put(b[0], v);
            }
        }
    }

    // =========================================================================================
    // Harness: strict single-pass run, no retries
    // =========================================================================================

    private static final String SUT_RESET_URL = "http://localhost:23242/reset";

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.err.println("Usage: java StrictGuidedRun <path-to-library/provengo-project>");
            System.exit(1);
        }
        String projectPath = args[0];

        List<String> results = new ArrayList<>();
        for (Scenario scenario : SCENARIOS) {
            resetSut();
            RunResult result = runScenario(projectPath, scenario);
            String verdict;
            if (scenario.expectReached) {
                verdict = result.reached
                        ? "REACHED"
                        : "STUCK at step " + (result.reachedSteps + 1) + "/" + scenario.steps.size()
                                + " (" + result.failedAction + " never became reachable)";
            } else {
                verdict = result.reached
                        ? "BUG: REACHED (should have been blocked!)"
                        : "OK: correctly blocked at step " + (result.reachedSteps + 1) + "/" + scenario.steps.size()
                                + " (" + result.failedAction + " never became reachable)";
            }
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

    /** How many selections may pass with no step progress before a scenario is given up on. */
    private static final int MAX_EVENTS_WITHOUT_PROGRESS = 3000;

    /** Diagnostic: set env var GUIDEDRUN_DIAG=1 to log each round's selected event. */
    private static final boolean DIAG = System.getenv("GUIDEDRUN_DIAG") != null;

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
        final List<Actuator> actuators = new ArrayList<>();
        for (TestoryLibrary lib : builder.getLibrariesInUse()) {
            lib.getActuator(runOptions).ifPresent(a -> {
                a.setup(runOptions);
                actuators.add(a);
            });
        }

        final int[] step = {0};
        final int[] eventsSinceProgress = {0};
        final Map<String, Double> bindings = new HashMap<>();
        final SimpleEventSelectionStrategy base = new SimpleEventSelectionStrategy();
        final java.util.Random rng = new java.util.Random();

        AbstractEventSelectionStrategy strict = new AbstractEventSelectionStrategy() {
            @Override
            public Set<BEvent> selectableEvents(BProgramSyncSnapshot snapshot) {
                int i = step[0];
                if (i >= scenario.steps.size()) return java.util.Collections.emptySet();
                Step current = scenario.steps.get(i);
                Set<BEvent> offered = base.selectableEvents(snapshot);

                // Strict: literally nothing except the exact target is ever selectable. No safe
                // fallback, no destructive/re-entangling guards -- there is nothing else to avoid,
                // because there is nothing else on offer at all. Now that the mutual block()
                // deadlock between createLoan/createHold and deleteUser/deleteBook is fixed
                // upstream, the target is expected to become selectable on its own, without
                // needing any other event to happen first.
                Set<BEvent> matches = new HashSet<>();
                for (BEvent e : offered) {
                    if (matchesChooser(e, current, bindings)) matches.add(e);
                }
                if (matches.isEmpty() && System.getenv("GUIDEDRUN_TRACE") != null) {
                    List<String> names = new ArrayList<>();
                    for (BEvent e : offered) names.add(chooserName(e));
                    java.util.Collections.sort(names);
                    System.out.println("      [trace] wanted " + current.action + ", offered this round ("
                            + offered.size() + " total): " + names);
                }
                return matches;
            }

            @Override
            public Optional<EventSelectionResult> select(BProgramSyncSnapshot snapshot, Set<BEvent> selectableEvents) {
                // Empty here means the target action was not on offer this round -- stop, don't
                // wait for a future round and don't let anything else happen in between.
                if (selectableEvents.isEmpty()) return Optional.empty();
                List<BEvent> list = new ArrayList<>(selectableEvents);
                BEvent chosen = list.get(rng.nextInt(list.size()));
                if (DIAG) {
                    System.out.println("      [DIAG] select() got " + list.size() + " options, chose: " + chooserName(chosen));
                }
                return Optional.of(new EventSelectionResult(chosen));
            }
        };
        program.setEventSelectionStrategy(strict);

        BProgramRunner runner = new BProgramRunner(program);
        runner.addListener(new BProgramRunnerListenerAdapter() {
            @Override
            public void error(BProgram bp, Exception ex) {
                System.out.println("      [ERROR] " + ex);
                ex.printStackTrace();
            }

            @Override
            public void eventSelected(BProgram bp, BEvent event) {
                for (Actuator a : actuators) {
                    try {
                        a.actuate(bp, event);
                    } catch (Exception ex) {
                        System.out.println("      [actuate exception] " + ex);
                    }
                }
                int i = step[0];
                if (i >= scenario.steps.size()) return;
                Step current = scenario.steps.get(i);
                if (matchesChooser(event, current, bindings)) {
                    applyBinds(event, current, bindings);
                    int reached = step[0] + 1;
                    step[0] = reached;
                    eventsSinceProgress[0] = 0;
                    System.out.println("  >>> step " + reached + "/" + scenario.steps.size()
                            + " reached via: " + chooserName(event) + "   bindings=" + bindings);
                    if (reached >= scenario.steps.size()) {
                        System.out.println("  >>> full sequence reached, halting.");
                        runner.halt();
                    }
                    return;
                }
                int c = ++eventsSinceProgress[0];
                if (c >= MAX_EVENTS_WITHOUT_PROGRESS) {
                    System.out.println("  >>> giving up: " + c + " events with no progress past step " + i);
                    runner.halt();
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
        String outcome;
        if (scenario.expectReached) {
            outcome = result.reached
                    ? "REACHED"
                    : "STUCK at step " + (result.reachedSteps + 1) + "/" + scenario.steps.size()
                            + " (" + result.failedAction + " never became reachable)";
        } else {
            outcome = result.reached
                    ? "BUG: REACHED (should have been blocked!)"
                    : "OK: correctly blocked at step " + (result.reachedSteps + 1) + "/" + scenario.steps.size()
                            + " (" + result.failedAction + " never became reachable)";
        }
        System.out.println("### Result: " + outcome);
        return result;
    }
}
