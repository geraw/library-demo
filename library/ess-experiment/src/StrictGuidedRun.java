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
 *
 * 2.9.3-extreme / 2.9.4-extreme background: these used to report REACHED for a second createLoan
 * on an already-busy user/book, even though the real SUT correctly rejects it with 400. Root
 * cause: UserBook.CanCreateLoan (dal.js) is only consulted once, when the ctx.bthread controller
 * first spawns the createLoan live copy for a given user-book pair (see ctx.bthread in Provengo's
 * bundled libs/context.js -- it only reacts to a query match becoming "new", never to one becoming
 * false again), so a pair eligible when its book/user were created could stay "offered" long after
 * the user picked up a loan elsewhere. Fixed upstream: lib_stories.js's createLoan ctx.bthread now
 * passes a stillRelevant recheck into createLoan() (interfaces.library.js), which stays on the
 * two-phase requestOneOf path (chooser sync, then a separate REST-send sync) specifically so that
 * recheck has a checkpoint to run at, right before the REST call actually fires.
 *
 * That two-phase shape is also why this checker needs isTwoPhaseChooser/isRawRestSend/
 * awaitingConfirmation below: winning a two-phase action's chooser only means the action was
 * CHOSEN, not yet sent, so this checker does NOT advance to the next scenario step at that point --
 * it waits for the action's own separate REST-send event to confirm it first (or, if stillRelevant
 * aborts the request before that send ever happens, the step correctly never gets reached). Every
 * other action here stays single-sync (requestOneOfDirect) and is unaffected by this distinction.
 *
 * One more wrinkle surfaced once the above was in place: verifyCannotCreateLoanForBusyUserOrBook
 * (lib_stories.js) spawns its own live copy the moment a pair becomes ineligible, calling createLoan
 * with expectedCode 400 -- an intentional-rejection request that gets the EXACT SAME descriptive
 * chooser name as a real attempt ("valid" only describes the request's shape, not its expected
 * outcome), for the SAME userId/bookId this checker is targeting. Without expectsRejection() below
 * to check the event's own expectedResponseCodes, this checker could pick up that correctly-rejected
 * request and mistake it for the target action succeeding.
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
        private static List<Scenario> scenarios1() {
        return List.of(
            new Scenario("3.1 User->Book->Hold->Loan (hold survives loan)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId")
            )),

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

            new Scenario("3.6 Book already loaned to A -> user B can still hold the SAME book", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user1", "userId").require("book", "bookId"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createHold").require("user2", "userId").require("book", "bookId")
            )),

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

            new Scenario("3.16 Two users hold the SAME book, loan goes to the SECOND holder", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user1", "userId").require("book", "bookId"),
                    step("createHold").require("user2", "userId").require("book", "bookId"),
                    step("createLoan").require("user2", "userId").require("book", "bookId")
            )),

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

            new Scenario("3.12-variant Book changes hands after return (different borrower)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user1", "userId").require("book", "bookId"),
                    step("deleteLoan").require("user1", "userId").require("book", "bookId"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createLoan").require("user2", "userId").require("book", "bookId")
            )),

            new Scenario("4.9-variant New hold for a different pair after deleting an old one", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold", "id"),
                    step("deleteHold").require("hold", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createHold").require("user2", "userId").require("book2", "bookId")
            )),

            new Scenario("4.11-variant Create/delete a user, then create/delete a different user", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("3.1-extreme User places a Hold on a book they already have on Loan", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("createHold").require("user", "userId").require("book", "bookId")
            )),

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

            new Scenario("4.11-extreme Three sequential create/delete user cycles, no cross-contamination", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bindDistinctFrom("user3", "id", "user1", "user2"),
                    step("deleteUser").require("user3", "id")
            )),

            expectBlocked("3.7 Delete a user who only has a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("deleteUser").require("user", "id")
            )),

            expectBlocked("2.4.3-extreme Delete a user who has an active Loan (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteUser").require("user", "id")
            )),

            expectBlocked("2.7.3-extreme Delete a book that only has a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("deleteBook").require("book", "id")
            )),

            expectBlocked("2.7.4-extreme Delete a book that has an active Loan (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteBook").require("book", "id")
            )),

            expectBlocked("Combined-gate Delete a user who has BOTH an active Loan and a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteUser").require("user", "id")
            )),

            expectBlocked("Combined-gate Delete a book that has BOTH an active Loan and a Hold (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("deleteBook").require("book", "id")
            )),

            expectBlocked("3.17 Loan attempt for a bookId that was already deleted (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("deleteBook").require("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId")
            )),

            expectBlocked("2.9.3-extreme Second active Loan for the SAME user on a DIFFERENT book (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createLoan").require("user", "userId").require("book1", "bookId"),
                    step("createLoan").require("user", "userId").require("book2", "bookId")
            )),

            expectBlocked("2.9.4-extreme Second active Loan for the SAME book by a DIFFERENT user (should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user1", "userId").require("book", "bookId"),
                    step("createLoan").require("user2", "userId").require("book", "bookId")
            )),

            expectBlocked("3.17-hold Hold attempt for a bookId that was already deleted (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("deleteBook").require("book", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId")
            )),

            expectBlocked("Hold attempt for a userId that was already deleted (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("deleteUser").require("user", "id"),
                    step("createHold").require("user", "userId").require("book", "bookId")
            )),

            expectBlocked("2.9.3-extreme-triple A third book's stale Loan offer is also correctly BLOCKED", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createBook").bindDistinctFrom("book3", "id", "book1", "book2"),
                    step("createLoan").require("user", "userId").require("book1", "bookId"),
                    step("createLoan").require("user", "userId").require("book3", "bookId")
            ))
        );
    }

    private static List<Scenario> scenarios2() {
        return List.of(
            expectBlocked("Combined-gate-cross-book Delete a user with a Hold on one book and a Loan on another (should be BLOCKED)", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createHold").require("user", "userId").require("book1", "bookId"),
                    step("createLoan").require("user", "userId").require("book2", "bookId"),
                    step("deleteUser").require("user", "id")
            )),

            new Scenario("One user holds TWO different books simultaneously", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createHold").require("user", "userId").require("book1", "bookId"),
                    step("createHold").require("user", "userId").require("book2", "bookId")
            )),

            new Scenario("User with two Holds deletes both, then is deletable", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createHold").require("user", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteHold").require("hold2", "id"),
                    step("deleteUser").require("user", "id")
            )),

            expectBlocked("User with two Holds is still blocked after deleting only ONE of them", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createHold").require("user", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user", "userId").require("book2", "bookId"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteUser").require("user", "id")
            )),

            expectBlocked("Book held by two users is still blocked after deleting only ONE of their Holds", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bind("book", "id"),
                    step("createHold").require("user1", "userId").require("book", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book", "bookId"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book", "id")
            )),

            expectBlocked("A second Loan for the EXACT SAME pair is blocked while the first is still active", List.of(
                    step("createUser").bind("user", "id"),
                    step("createBook").bind("book", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId"),
                    step("createLoan").require("user", "userId").require("book", "bookId")
            )),

            new Scenario("Two independent busy Loan pairs don't interfere with each other", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createLoan").require("user2", "userId").require("book2", "bookId")
            )),

            expectBlocked("Loan blocked when BOTH user and book are busy via DIFFERENT independent loans", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createLoan").require("user2", "userId").require("book2", "bookId"),
                    step("createLoan").require("user1", "userId").require("book2", "bookId")
            )),

            expectBlocked("3.9 Delete user with an active Loan is blocked by their OWN loan, not an unrelated user's", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createLoan").require("user2", "userId").require("book2", "bookId"),
                    step("deleteUser").require("user1", "id")
            )),

            new Scenario("3.12 Book changes hands after return, with a third unrelated active loan throughout", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bindDistinctFrom("user2", "id", "user1"),
                    step("createBook").bindDistinctFrom("book2", "id", "book1"),
                    step("createUser").bindDistinctFrom("user3", "id", "user1", "user2"),
                    step("createBook").bindDistinctFrom("book3", "id", "book1", "book2"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createLoan").require("user2", "userId").require("book2", "bookId"),
                    step("createLoan").require("user3", "userId").require("book3", "bookId"),
                    step("deleteLoan").require("user1", "userId").require("book1", "bookId"),
                    step("deleteLoan").require("user2", "userId").require("book2", "bookId"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId")
            )),

            new Scenario("Book created before any user exists -- the pair still works", List.of(
                    step("createBook").bind("book", "id"),
                    step("createUser").bind("user", "id"),
                    step("createLoan").require("user", "userId").require("book", "bookId")
            )),

            new Scenario("sample-derived-1 (3 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-2 (4 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-3 (4 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-4 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-5 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-6 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-7 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            new Scenario("sample-derived-8 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-9 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-10 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-11 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            new Scenario("sample-derived-12 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            new Scenario("sample-derived-13 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-14 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-15 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-16 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id")
            )),

            new Scenario("sample-derived-17 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-18 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-19 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id")
            ))
        );
    }

    private static List<Scenario> scenarios3() {
        return List.of(
            new Scenario("sample-derived-20 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            new Scenario("sample-derived-21 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-22 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-23 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-24 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-25 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-26 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-27 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id")
            )),

            new Scenario("sample-derived-28 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-29 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-30 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteHold").require("hold2", "id")
            )),

            new Scenario("sample-derived-31 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user2", "userId").require("book2", "bookId"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-32 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-33 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-34 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-35 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-36 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-37 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold3", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-38 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-39 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-40 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-41 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-42 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book2", "bookId"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-43 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-44 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-45 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user4", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-46 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-47 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-48 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-49 (11 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createBook").bind("book2", "id")
            ))
        );
    }

    private static List<Scenario> scenarios4() {
        return List.of(
            new Scenario("sample-derived-50 (12 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-51 (3 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id")
            )),

            new Scenario("sample-derived-52 (4 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-53 (4 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-54 (4 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-55 (4 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-56 (4 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-57 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-58 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user1", "id")
            )),

            new Scenario("sample-derived-59 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-60 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-61 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-62 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-63 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id")
            )),

            new Scenario("sample-derived-64 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-65 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-66 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-67 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-68 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-69 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-70 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-71 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-72 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-73 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-74 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-75 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id")
            )),

            new Scenario("sample-derived-76 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-77 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-78 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-79 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id")
            ))
        );
    }

    private static List<Scenario> scenarios5() {
        return List.of(
            new Scenario("sample-derived-80 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-81 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-82 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-83 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-84 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user1", "id")
            )),

            new Scenario("sample-derived-85 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-86 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-87 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold2", "id")
            )),

            new Scenario("sample-derived-88 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-89 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-90 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-91 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            new Scenario("sample-derived-92 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-93 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-94 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-95 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-96 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id")
            )),

            new Scenario("sample-derived-97 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-98 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-99 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-100 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-101 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-102 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-103 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-104 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-105 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-106 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-107 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-108 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-109 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book2", "id")
            ))
        );
    }

    private static List<Scenario> scenarios6() {
        return List.of(
            new Scenario("sample-derived-110 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-111 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-112 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-113 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-114 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-115 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-116 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-117 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-118 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-119 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-120 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-121 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-122 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-123 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-124 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-125 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-126 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book2", "bookId"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-127 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-128 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book4", "id")
            )),

            new Scenario("sample-derived-129 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-130 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-131 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-132 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-133 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-134 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-135 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-136 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createLoan").require("user1", "userId").require("book3", "bookId"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-137 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-138 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-139 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user2", "id")
            ))
        );
    }

    private static List<Scenario> scenarios7() {
        return List.of(
            new Scenario("sample-derived-140 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteBook").require("book3", "id")
            )),

            new Scenario("sample-derived-141 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-142 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-143 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-144 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-145 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-146 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteHold").require("hold2", "id")
            )),

            new Scenario("sample-derived-147 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-148 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-149 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-150 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-151 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            new Scenario("sample-derived-152 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-153 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            new Scenario("sample-derived-154 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-155 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-156 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-157 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-158 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            new Scenario("sample-derived-159 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-160 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("deleteLoan").require("user2", "userId").require("book1", "bookId")
            )),

            new Scenario("sample-derived-161 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-162 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            new Scenario("sample-derived-163 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-164 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id")
            )),

            new Scenario("sample-derived-165 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-166 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-167 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-168 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-169 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold2", "id")
            ))
        );
    }

    private static List<Scenario> scenarios8() {
        return List.of(
            new Scenario("sample-derived-170 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book3", "bookId"),
                    step("deleteBook").require("book4", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-171 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-172 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteHold").require("hold2", "id")
            )),

            new Scenario("sample-derived-173 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-174 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-175 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold3", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-176 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-177 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-178 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-179 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-180 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteUser").require("user4", "id")
            )),

            new Scenario("sample-derived-181 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-182 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-183 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-184 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-185 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-186 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-187 (11 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-188 (11 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createHold").require("user4", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-189 (11 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("deleteLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-190 (12 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user4", "id")
            )),

            new Scenario("sample-derived-191 (12 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold3", "id"),
                    step("createHold").require("user3", "userId").require("book3", "bookId").bind("hold4", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold5", "id")
            )),

            new Scenario("sample-derived-192 (12 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book4", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-193 (13 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-194 (14 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            new Scenario("sample-derived-195 (14 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-1 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-2 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-3 (3 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-4 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book1", "id")
            ))
        );
    }

    private static List<Scenario> scenarios9() {
        return List.of(
            expectBlocked("sample-derived-blocked-5 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-6 (4 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-7 (3 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-8 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-9 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-10 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            expectBlocked("sample-derived-blocked-11 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-12 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-13 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            expectBlocked("sample-derived-blocked-14 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-15 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-16 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-17 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-18 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-19 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            expectBlocked("sample-derived-blocked-20 (10 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-21 (9 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-22 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-23 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-24 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            expectBlocked("sample-derived-blocked-25 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book2", "bookId"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-26 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            expectBlocked("sample-derived-blocked-27 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-28 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-29 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-30 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-31 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-32 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-33 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-34 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user3", "id")
            ))
        );
    }

    private static List<Scenario> scenarios10() {
        return List.of(
            expectBlocked("sample-derived-blocked-35 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-36 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-37 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-38 (10 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-39 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            expectBlocked("sample-derived-blocked-40 (9 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold4", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-41 (9 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold4", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            expectBlocked("sample-derived-blocked-42 (3 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-43 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-44 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-45 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-46 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-47 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            new Scenario("sample-derived-196 (4 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id")
            )),

            new Scenario("sample-derived-197 (4 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-198 (4 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-199 (4 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-200 (4 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-201 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            new Scenario("sample-derived-202 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-203 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-204 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-205 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-206 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-207 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book2", "bookId"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-208 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-209 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-210 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-211 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-212 (5 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            ))
        );
    }

    private static List<Scenario> scenarios11() {
        return List.of(
            new Scenario("sample-derived-213 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            new Scenario("sample-derived-214 (5 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-215 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-216 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-217 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id")
            )),

            new Scenario("sample-derived-218 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-219 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-220 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-221 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-222 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-223 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-224 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-225 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-226 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-227 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-228 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-229 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-230 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-231 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            new Scenario("sample-derived-232 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-233 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-234 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-235 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-236 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-237 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold2", "id")
            )),

            new Scenario("sample-derived-238 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-239 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-240 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-241 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-242 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id")
            ))
        );
    }

    private static List<Scenario> scenarios12() {
        return List.of(
            new Scenario("sample-derived-243 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            new Scenario("sample-derived-244 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-245 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-246 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-247 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-248 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-249 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-250 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-251 (6 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-252 (6 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-253 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-254 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-255 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book3", "id")
            )),

            new Scenario("sample-derived-256 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-257 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-258 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-259 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-260 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            new Scenario("sample-derived-261 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-262 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book4", "id")
            )),

            new Scenario("sample-derived-263 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id")
            )),

            new Scenario("sample-derived-264 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            new Scenario("sample-derived-265 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            new Scenario("sample-derived-266 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id")
            )),

            new Scenario("sample-derived-267 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-268 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-269 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-270 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            new Scenario("sample-derived-271 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-272 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user3", "id")
            ))
        );
    }

    private static List<Scenario> scenarios13() {
        return List.of(
            new Scenario("sample-derived-273 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-274 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id")
            )),

            new Scenario("sample-derived-275 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book4", "id")
            )),

            new Scenario("sample-derived-276 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-277 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-278 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-279 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-280 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book4", "id")
            )),

            new Scenario("sample-derived-281 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-282 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-283 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-284 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-285 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-286 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-287 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-288 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-289 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-290 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-291 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-292 (7 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-293 (7 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            new Scenario("sample-derived-294 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-295 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-296 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-297 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-298 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-299 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-300 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-301 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-302 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id")
            ))
        );
    }

    private static List<Scenario> scenarios14() {
        return List.of(
            new Scenario("sample-derived-303 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-304 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createLoan").require("user1", "userId").require("book3", "bookId"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-305 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-306 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-307 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-308 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-309 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-310 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-311 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-312 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-313 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user1", "id")
            )),

            new Scenario("sample-derived-314 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-315 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-316 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-317 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold2", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-318 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-319 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-320 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-321 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-322 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-323 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold3", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-324 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-325 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-326 (8 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-327 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-328 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-329 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-330 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold3", "id")
            )),

            new Scenario("sample-derived-331 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-332 (8 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book4", "id")
            ))
        );
    }

    private static List<Scenario> scenarios15() {
        return List.of(
            new Scenario("sample-derived-333 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-334 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold3", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold4", "id")
            )),

            new Scenario("sample-derived-335 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            new Scenario("sample-derived-336 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-337 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book2", "bookId")
            )),

            new Scenario("sample-derived-338 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-339 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book4", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-340 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-341 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-342 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user4", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-343 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-344 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            new Scenario("sample-derived-345 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-346 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-347 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            new Scenario("sample-derived-348 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-349 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold4", "id")
            )),

            new Scenario("sample-derived-350 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-351 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book4", "id")
            )),

            new Scenario("sample-derived-352 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-353 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-354 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            new Scenario("sample-derived-355 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("deleteHold").require("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-356 (9 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-357 (9 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-358 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user4", "userId").require("book2", "bookId").bind("hold1", "id")
            )),

            new Scenario("sample-derived-359 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-360 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createLoan").require("user3", "userId").require("book1", "bookId"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-361 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-362 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold2", "id")
            ))
        );
    }

    private static List<Scenario> scenarios16() {
        return List.of(
            new Scenario("sample-derived-363 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold4", "id"),
                    step("deleteHold").require("hold4", "id")
            )),

            new Scenario("sample-derived-364 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-365 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteHold").require("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold3", "id")
            )),

            new Scenario("sample-derived-366 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-367 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user1", "userId").require("book4", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-368 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id")
            )),

            new Scenario("sample-derived-369 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold3", "id"),
                    step("createBook").bind("book2", "id")
            )),

            new Scenario("sample-derived-370 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-371 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("deleteLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createUser").bind("user4", "id")
            )),

            new Scenario("sample-derived-372 (10 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold3", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-373 (10 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            new Scenario("sample-derived-374 (11 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold4", "id")
            )),

            new Scenario("sample-derived-375 (11 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user4", "userId").require("book2", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-376 (11 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book4", "id")
            )),

            new Scenario("sample-derived-377 (11 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-378 (11 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user4", "id")
            )),

            new Scenario("sample-derived-379 (12 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user3", "userId").require("book3", "bookId").bind("hold2", "id")
            )),

            new Scenario("sample-derived-380 (12 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-381 (12 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id")
            )),

            new Scenario("sample-derived-382 (12 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-383 (13 steps)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user3", "id")
            )),

            new Scenario("sample-derived-384 (13 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            new Scenario("sample-derived-385 (14 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createHold").require("user4", "userId").require("book4", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id")
            )),

            new Scenario("sample-derived-386 (14 steps)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("deleteUser").require("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id")
            )),

            expectBlocked("sample-derived-blocked-48 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-49 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-50 (4 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-51 (10 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createHold").require("user3", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            expectBlocked("sample-derived-blocked-52 (9 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteUser").require("user3", "id")
            )),

            expectBlocked("sample-derived-blocked-53 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteBook").require("book1", "id")
            ))
        );
    }

    private static List<Scenario> scenarios17() {
        return List.of(
            expectBlocked("sample-derived-blocked-54 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-55 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-56 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-57 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-58 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

            expectBlocked("sample-derived-blocked-59 (9 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-60 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-61 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-62 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-63 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-64 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

            expectBlocked("sample-derived-blocked-65 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-66 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id")
            )),

            expectBlocked("sample-derived-blocked-67 (8 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold3", "id"),
                    step("deleteHold").require("hold3", "id"),
                    step("deleteUser").require("user1", "id")
            )),

            expectBlocked("sample-derived-blocked-68 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            ))
        );
    }

    private static List<Scenario> scenarios18() {
        return List.of(
            expectBlocked("sample-derived-blocked-69 (4 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-70 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-71 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-72 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-73 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-74 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-75 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-76 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user2", "id")
            )),

expectBlocked("sample-derived-blocked-77 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-78 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-79 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user3", "id")
            )),

expectBlocked("sample-derived-blocked-80 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-81 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id")
            )),

expectBlocked("sample-derived-blocked-82 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-83 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-84 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id")
            )),

expectBlocked("sample-derived-blocked-85 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id")
            )),

expectBlocked("sample-derived-blocked-86 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteHold").require("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-87 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-88 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

expectBlocked("sample-derived-blocked-89 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-90 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-92 (9 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createUser").bind("user4", "id"),
                    step("deleteUser").require("user3", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-93 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-94 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-95 (4 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-96 (4 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-97 (4 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book1", "bookId"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-98 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-99 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-100 (8 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createBook").bind("book4", "id"),
                    step("deleteBook").require("book4", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-101 (8 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book4", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createLoan").require("user1", "userId").require("book2", "bookId"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book3", "id")
            )),

expectBlocked("sample-derived-blocked-102 (4 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-103 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-104 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book3", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-105 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-106 (6 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("deleteBook").require("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-107 (8 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user4", "id"),
                    step("createHold").require("user4", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user4", "id")
            )),

expectBlocked("sample-derived-blocked-108 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("deleteBook").require("book1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book3", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-109 (6 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteBook").require("book2", "id")
            )),

expectBlocked("sample-derived-blocked-110 (8 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createBook").bind("book3", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-111 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user1", "id"),
                    step("createHold").require("user1", "userId").require("book2", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("deleteUser").require("user1", "id")
            )),

expectBlocked("sample-derived-blocked-112 (4 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user2", "id")
            )),

expectBlocked("sample-derived-blocked-113 (5 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteBook").require("book1", "id")
            )),

expectBlocked("sample-derived-blocked-114 (7 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createUser").bind("user3", "id"),
                    step("deleteUser").require("user2", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createHold").require("user1", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user3", "userId").require("book1", "bookId").bind("hold2", "id"),
                    step("deleteUser").require("user3", "id")
            )),

expectBlocked("sample-derived-blocked-115 (5 prefix steps, deleteUser should be BLOCKED)", List.of(
                    step("createUser").bind("user1", "id"),
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createLoan").require("user2", "userId").require("book1", "bookId"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("deleteUser").require("user2", "id")
            )),

expectBlocked("sample-derived-blocked-116 (7 prefix steps, deleteBook should be BLOCKED)", List.of(
                    step("createBook").bind("book1", "id"),
                    step("createUser").bind("user1", "id"),
                    step("deleteUser").require("user1", "id"),
                    step("createBook").bind("book2", "id"),
                    step("createUser").bind("user2", "id"),
                    step("createHold").require("user2", "userId").require("book1", "bookId").bind("hold1", "id"),
                    step("createHold").require("user2", "userId").require("book2", "bookId").bind("hold2", "id"),
                    step("deleteBook").require("book1", "id")
            ))
        );
    }

    private static final List<Scenario> SCENARIOS = java.util.stream.Stream.of(
            scenarios18(),
            scenarios1(),
            scenarios2(),
            scenarios3(),
            scenarios4(),
            scenarios5(),
            scenarios6(),
            scenarios7(),
            scenarios8(),
            scenarios9(),
            scenarios10(),
            scenarios11(),
            scenarios12(),
            scenarios13(),
            scenarios14(),
            scenarios15(),
            scenarios16(),
            scenarios17()
    ).flatMap(List::stream).collect(java.util.stream.Collectors.toList());


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
     * Identity fields (id/userId/bookId/...) of an event -- from event.data.parameters directly
     * for a concrete REST event, from event.data.model.parameters for a single-sync action's
     * combined chooser+REST event, or from event.data.variant.parameters for a genuine two-phase
     * action's lightweight chooser event (requestOneOf -- e.g. createLoan; see isTwoPhaseChooser).
     */
    private static Map<String, Object> extractParameters(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data == null) return null;
        Map<String, Object> direct = asMap(data.get("parameters"));
        if (direct != null) return direct;
        Map<String, Object> model = asMap(data.get("model"));
        if (model != null) return asMap(model.get("parameters"));
        Map<String, Object> variant = asMap(data.get("variant"));
        if (variant != null) return asMap(variant.get("parameters"));
        return null;
    }

    /**
     * A two-phase action's lightweight chooser event (requestOneOf: bp.Event(name, {variant: v})
     * in interfaces.library.js). Winning this only means the action was CHOSEN, not yet actually
     * sent -- the real REST call is a SEPARATE, later synchronization (see isRawRestSend). A
     * single-sync action's event (requestOneOfDirect) carries data.model instead and IS already
     * the real REST send, so it doesn't need this two-step tracking.
     */
    private static boolean isTwoPhaseChooser(BEvent event) {
        Map<String, Object> data = eventData(event);
        return data != null && data.get("model") == null && data.get("variant") != null;
    }

    /**
     * The actual REST send of a two-phase action (RESTSession's plain ___apiBody___/svc.post path,
     * as opposed to interfaces.library.js's buildRestEvent) -- the event whose real HTTP response
     * is what dal.js's effects and the SUT itself react to. Named after the bare HTTP verb
     * ("POST"/"DELETE"), not descriptively, and carries no data.model -- that's what distinguishes
     * it from a single-sync action's own combined chooser+REST event.
     */
    private static boolean isRawRestSend(BEvent event) {
        Map<String, Object> data = eventData(event);
        return data != null && "REST".equals(data.get("lib")) && data.get("model") == null;
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

    /**
     * True if this event's own expectedResponseCodes marks it as an intentional-rejection test
     * (expects 400), regardless of its "valid"-labeled name. A well-formed request that's supposed
     * to fail (e.g. tryToCreateLoanAndExpectError, spawned once a pair becomes ineligible) gets the
     * SAME descriptive chooser name as a well-formed request that's supposed to succeed ("valid"
     * only ever describes the request's SHAPE, not its expected outcome) -- so name matching alone
     * can't tell them apart. Both live copies can be pending at once for the very same
     * userId/bookId once a pair goes from eligible to ineligible mid-scenario, so this check is
     * what keeps this checker from mistaking a correctly-rejected request for the target action
     * actually succeeding.
     */
    private static boolean expectsRejection(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data == null) return false;
        Object codes = data.get("expectedResponseCodes");
        if (codes == null) {
            Map<String, Object> variant = asMap(data.get("variant"));
            if (variant != null) codes = variant.get("expectedResponseCodes");
        }
        if (codes instanceof List) {
            for (Object c : (List<?>) codes) {
                if (c instanceof Number && ((Number) c).intValue() == 400) return true;
            }
        }
        return false;
    }

    /** Is this event a well-formed, success-intended offer of the step's action with matching identity? */
    private static boolean matchesChooser(BEvent event, Step step, Map<String, Double> bindings) {
        return chooserNameMatches(chooserName(event), step.action)
                && !expectsRejection(event)
                && matchesIdentity(event, step, bindings);
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
        // True between a two-phase action's chooser winning and its actual REST send being
        // confirmed (see isTwoPhaseChooser/isRawRestSend) -- the current step isn't reached yet,
        // even though its chooser already won, until the real send happens too.
        final boolean[] awaitingConfirmation = {false};

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
                if (awaitingConfirmation[0]) {
                    // The current step's chooser already won (isTwoPhaseChooser); now only its own
                    // real REST send counts -- same identity check as the step itself, since the
                    // step hasn't advanced and bindings haven't changed since the chooser won.
                    for (BEvent e : offered) {
                        if (isRawRestSend(e) && !expectsRejection(e) && matchesIdentity(e, current, bindings)) matches.add(e);
                    }
                } else {
                    for (BEvent e : offered) {
                        if (matchesChooser(e, current, bindings)) matches.add(e);
                    }
                }
                if (matches.isEmpty() && System.getenv("GUIDEDRUN_TRACE") != null) {
                    List<String> names = new ArrayList<>();
                    for (BEvent e : offered) names.add(chooserName(e));
                    java.util.Collections.sort(names);
                    System.out.println("      [trace] wanted " + current.action
                            + (awaitingConfirmation[0] ? " (awaiting REST confirmation)" : "")
                            + ", offered this round (" + offered.size() + " total): " + names);
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

                if (awaitingConfirmation[0]) {
                    if (isRawRestSend(event) && !expectsRejection(event) && matchesIdentity(event, current, bindings)) {
                        awaitingConfirmation[0] = false;
                        int reached = step[0] + 1;
                        step[0] = reached;
                        eventsSinceProgress[0] = 0;
                        System.out.println("  >>> step " + reached + "/" + scenario.steps.size()
                                + " reached via: " + current.action + " (two-phase, REST send confirmed)"
                                + "   bindings=" + bindings);
                        if (reached >= scenario.steps.size()) {
                            System.out.println("  >>> full sequence reached, halting.");
                            runner.halt();
                        }
                        return;
                    }
                } else if (matchesChooser(event, current, bindings)) {
                    applyBinds(event, current, bindings);
                    if (isTwoPhaseChooser(event)) {
                        // Chooser won, but the action isn't complete yet -- wait for its actual
                        // REST send (see selectableEvents' awaitingConfirmation branch) before
                        // counting this step as reached. A stillRelevant recheck inside the story
                        // (e.g. createLoan's) can still abort it before that send ever happens.
                        awaitingConfirmation[0] = true;
                        eventsSinceProgress[0] = 0;
                        System.out.println("  >>> step " + (step[0] + 1) + "/" + scenario.steps.size()
                                + " chooser won: " + chooserName(event) + "   bindings=" + bindings
                                + "  (awaiting REST confirmation)");
                        return;
                    }
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
