import java.util.List;

/**
 * Scenarios added in v013 on top of the frozen 542-scenario catalog. They use the same Step /
 * Scenario model and the same strict selection; the catalog itself is untouched.
 *
 * Two lists:
 *  - COMMON: legal under the original library rules (one active loan per reader) AND under the
 *    experiment contract. They add what the catalog lacks: read steps (readBookDetail, readLoans,
 *    readHolds, readBooks, readUsers) and the ISSTA triggers that need no multi-loan reader.
 *  - CONTRACT: legal only under the experiment contract (no per-reader loan cap), i.e. with the
 *    "contract" model profile of prepare_model_v013.py. Under the "original" profile they are
 *    expected to come out STUCK at the second loan for the same reader.
 *
 * Read steps carry no identity constraint on list reads (the list query parameters are
 * late-bound SUT ids, not logical ids); readBookDetail is constrained by its logical book id.
 */
public final class V013Scenarios {

    private V013Scenarios() {}

    private static StrictGuidedRun.Step step(String action) { return new StrictGuidedRun.Step(action); }
    private static StrictGuidedRun.Scenario reach(String name, StrictGuidedRun.Step... steps) {
        return new StrictGuidedRun.Scenario(name, List.of(steps));
    }

    private static StrictGuidedRun.Step user(String var) { return step("createUser").bind(var, "id"); }
    private static StrictGuidedRun.Step user(String var, String... distinct) { return step("createUser").bindDistinctFrom(var, "id", distinct); }
    private static StrictGuidedRun.Step book(String var) { return step("createBook").bind(var, "id"); }
    private static StrictGuidedRun.Step book(String var, String... distinct) { return step("createBook").bindDistinctFrom(var, "id", distinct); }
    private static StrictGuidedRun.Step loan(String user, String book) { return step("createLoan").require(user, "userId").require(book, "bookId"); }
    private static StrictGuidedRun.Step returnLoan(String user, String book) { return step("deleteLoan").require(user, "userId").require(book, "bookId"); }
    private static StrictGuidedRun.Step hold(String var, String user, String book) { return step("createHold").require(user, "userId").require(book, "bookId").bind(var, "id"); }
    private static StrictGuidedRun.Step hold(String var, String user, String book, String... distinct) { return step("createHold").require(user, "userId").require(book, "bookId").bindDistinctFrom(var, "id", distinct); }
    private static StrictGuidedRun.Step cancelHold(String var) { return step("deleteHold").require(var, "id"); }
    private static StrictGuidedRun.Step deleteUser(String var) { return step("deleteUser").require(var, "id"); }
    private static StrictGuidedRun.Step deleteBook(String var) { return step("deleteBook").require(var, "id"); }
    private static StrictGuidedRun.Step readBook(String var) { return step("readBookDetail").require(var, "id"); }
    private static StrictGuidedRun.Step readLoans() { return step("readLoans"); }
    private static StrictGuidedRun.Step readHolds() { return step("readHolds"); }
    private static StrictGuidedRun.Step readBooks() { return step("readBooks"); }
    private static StrictGuidedRun.Step readUsers() { return step("readUsers"); }

    public static final List<StrictGuidedRun.Scenario> COMMON = List.of(
            reach("v013-ISSTA-4 Create a book, then read its detail (an existing book reads 200)",
                    book("b"), readBook("b")),
            reach("v013-ISSTA-4b Read the detail of a book that is on hold",
                    user("u"), book("b"), hold("h", "u", "b"), readBook("b")),
            reach("v013-ISSTA-4c Read the detail of a book that is on loan",
                    user("u"), book("b"), loan("u", "b"), readBook("b")),
            reach("v013-ISSTA-2 Borrow, return, borrow, return, borrow the same pair (third borrowing)",
                    user("u"), book("b"), loan("u", "b"), returnLoan("u", "b"), loan("u", "b"), returnLoan("u", "b"), loan("u", "b"), readLoans()),
            reach("v013-ISSTA-5 Reader with two holds cancels one; the other must survive",
                    user("u"), book("b1"), book("b2", "b1"), hold("h1", "u", "b1"), hold("h2", "u", "b2", "h1"), cancelHold("h1"), readHolds()),
            reach("v013-ISSTA-5b Two readers hold the same book; one cancels",
                    user("u1"), user("u2", "u1"), book("b"), hold("h1", "u1", "b"), hold("h2", "u2", "b", "h1"), cancelHold("h1"), readHolds()),
            reach("v013-ISSTA-5c Cancel the second of two holds (LIFO), the first must survive",
                    user("u"), book("b1"), book("b2", "b1"), hold("h1", "u", "b1"), hold("h2", "u", "b2", "h1"), cancelHold("h2"), readHolds()),
            reach("v013-3.13 Loans list read after a loan and again after its return",
                    user("u"), book("b"), loan("u", "b"), readLoans(), returnLoan("u", "b"), readLoans()),
            reach("v013-3.19 Holds list read right after a hold is cancelled",
                    user("u"), book("b"), hold("h", "u", "b"), cancelHold("h"), readHolds()),
            reach("v013-3.4 Re-borrow after return, then return again",
                    user("u"), book("b"), loan("u", "b"), returnLoan("u", "b"), loan("u", "b"), returnLoan("u", "b"), readLoans()),
            reach("v013-3.11-reads Full happy path with a read after every write",
                    user("u"), readUsers(), book("b"), readBooks(), readBook("b"), hold("h", "u", "b"), readHolds(), loan("u", "b"), readLoans(),
                    returnLoan("u", "b"), readLoans(), cancelHold("h"), readHolds(), deleteBook("b"), readBooks(), deleteUser("u"), readUsers()),
            reach("v013-2.4 Reader deletable once the only hold is cancelled",
                    user("u"), book("b"), hold("h", "u", "b"), cancelHold("h"), deleteUser("u"), readUsers()),
            reach("v013-2.7 Book deletable once its loan is returned",
                    user("u"), book("b"), loan("u", "b"), returnLoan("u", "b"), deleteBook("b"), readBooks()),
            reach("v013-bounded Five readers each borrow a distinct book at the same time",
                    user("u1"), user("u2", "u1"), user("u3", "u1", "u2"), user("u4", "u1", "u2", "u3"), user("u5", "u1", "u2", "u3", "u4"),
                    book("b1"), book("b2", "b1"), book("b3", "b1", "b2"), book("b4", "b1", "b2", "b3"), book("b5", "b1", "b2", "b3", "b4"),
                    loan("u1", "b1"), loan("u2", "b2"), loan("u3", "b3"), loan("u4", "b4"), loan("u5", "b5"), readLoans()),
            reach("v013-bounded Five readers queue on the same book",
                    user("u1"), user("u2", "u1"), user("u3", "u1", "u2"), user("u4", "u1", "u2", "u3"), user("u5", "u1", "u2", "u3", "u4"), book("b"),
                    hold("h1", "u1", "b"), hold("h2", "u2", "b", "h1"), hold("h3", "u3", "b", "h1", "h2"), hold("h4", "u4", "b", "h1", "h2", "h3"),
                    hold("h5", "u5", "b", "h1", "h2", "h3", "h4"), readHolds()),
            reach("v013-handover Book returned by one reader is borrowed by another, both reads",
                    user("u1"), user("u2", "u1"), book("b"), loan("u1", "b"), readLoans(), returnLoan("u1", "b"), loan("u2", "b"), readLoans())
    );

    public static final List<StrictGuidedRun.Scenario> CONTRACT = List.of(
            reach("v013-ISSTA-1-ladder Second distinct active loan for one reader",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), loan("u", "b2"), readLoans()),
            reach("v013-ISSTA-1-ladder Third distinct active loan for one reader",
                    user("u"), book("b1"), book("b2", "b1"), book("b3", "b1", "b2"), loan("u", "b1"), loan("u", "b2"), loan("u", "b3"), readLoans()),
            reach("v013-ISSTA-1 Fourth distinct active loan for one reader",
                    user("u"), book("b1"), book("b2", "b1"), book("b3", "b1", "b2"), book("b4", "b1", "b2", "b3"),
                    loan("u", "b1"), loan("u", "b2"), loan("u", "b3"), loan("u", "b4"), readLoans()),
            reach("v013-ISSTA-1b Fourth active loan where the first book was borrowed twice",
                    user("u"), book("b1"), book("b2", "b1"), book("b3", "b1", "b2"), book("b4", "b1", "b2", "b3"),
                    loan("u", "b1"), returnLoan("u", "b1"), loan("u", "b1"), loan("u", "b2"), loan("u", "b3"), loan("u", "b4"), readLoans()),
            reach("v013-ISSTA-3 Return one of two active loans of a reader; the other must survive",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), loan("u", "b2"), returnLoan("u", "b1"), readLoans()),
            reach("v013-ISSTA-3b Return the middle one of three active loans",
                    user("u"), book("b1"), book("b2", "b1"), book("b3", "b1", "b2"), loan("u", "b1"), loan("u", "b2"), loan("u", "b3"), returnLoan("u", "b2"), readLoans()),
            reach("v013-ISSTA-3c Reader with two loans and a hold returns one loan",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), loan("u", "b2"), hold("h", "u", "b1"), returnLoan("u", "b2"), readLoans(), readHolds()),
            reach("v013-ISSTA-5d Reader with two loans and two holds cancels one hold",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), loan("u", "b2"), hold("h1", "u", "b1"), hold("h2", "u", "b2", "h1"), cancelHold("h1"), readHolds(), readLoans()),
            reach("v013-contract Reader with two loans is deletable only after both returns",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), loan("u", "b2"), returnLoan("u", "b1"), returnLoan("u", "b2"), deleteUser("u"), readUsers()),
            reach("v013-contract Two readers with two loans each, cross returns",
                    user("u1"), user("u2", "u1"), book("b1"), book("b2", "b1"), book("b3", "b1", "b2"), book("b4", "b1", "b2", "b3"),
                    loan("u1", "b1"), loan("u2", "b2"), loan("u1", "b3"), loan("u2", "b4"), returnLoan("u1", "b1"), returnLoan("u2", "b4"), readLoans())
    );

    // ---- Rejection steps: a business-rule rejection check as a scenario step. The model must
    // offer the rejecting request (expected 400/404) at exactly that point; nothing else is
    // selectable. The step name "rejectDeleteUser" matches any code, "rejectDeleteUser404" one.
    private static StrictGuidedRun.Step rejectDeleteUser(String var, String code) { return step("rejectDeleteUser" + code).require(var, "id"); }
    private static StrictGuidedRun.Step rejectDeleteBook(String var, String code) { return step("rejectDeleteBook" + code).require(var, "id"); }
    private static StrictGuidedRun.Step rejectDeleteHold(String var, String code) { return step("rejectDeleteHold" + code).require(var, "id"); }
    private static StrictGuidedRun.Step rejectDeleteLoan(String user, String book, String code) { return step("rejectDeleteLoan" + code).require(user, "userId").require(book, "bookId"); }
    private static StrictGuidedRun.Step rejectLoan(String user, String book) { return step("rejectCreateLoan400").require(user, "userId").require(book, "bookId"); }
    private static StrictGuidedRun.Step rejectLoanMissingBook(String user) { return step("rejectCreateLoan400").require(user, "userId"); }
    private static StrictGuidedRun.Step rejectLoanMissingUser(String book) { return step("rejectCreateLoan400").require(book, "bookId"); }
    private static StrictGuidedRun.Step rejectHoldMissingBook(String user) { return step("rejectCreateHold400").require(user, "userId"); }
    private static StrictGuidedRun.Step rejectHoldMissingUser(String book) { return step("rejectCreateHold400").require(book, "bookId"); }
    private static StrictGuidedRun.Step rejectReadBook(String var) { return step("rejectReadBookDetail404").require(var, "id"); }

    /** Rejection sequences legal under both profiles (bug-mapping chapters 2-3). */
    public static final List<StrictGuidedRun.Scenario> NEGATIVE = List.of(
            reach("v013-N-2.4.2 Reader with a hold: delete must be rejected",
                    user("u"), book("b"), hold("h", "u", "b"), rejectDeleteUser("u", "400")),
            reach("v013-N-2.4.3 Reader with a loan: delete must be rejected",
                    user("u"), book("b"), loan("u", "b"), rejectDeleteUser("u", "400")),
            reach("v013-N-2.7.3 Held book: delete must be rejected",
                    user("u"), book("b"), hold("h", "u", "b"), rejectDeleteBook("b", "400")),
            reach("v013-N-2.7.4 Loaned book: delete must be rejected",
                    user("u"), book("b"), loan("u", "b"), rejectDeleteBook("b", "400")),
            reach("v013-N-2.9.4 Loaned book: a loan by another reader must be rejected",
                    user("u1"), user("u2", "u1"), book("b"), loan("u1", "b"), rejectLoan("u2", "b")),
            reach("v013-N-2.9.2 Same pair twice: the second loan must be rejected",
                    user("u"), book("b"), loan("u", "b"), rejectLoan("u", "b")),
            reach("v013-N-3.6 Loan rejected on a loaned book, then a hold by the same reader succeeds",
                    user("u1"), user("u2", "u1"), book("b"), loan("u1", "b"), rejectLoan("u2", "b"), hold("h", "u2", "b")),
            reach("v013-N-handover Loan rejected while loaned; after the return the same reader borrows it",
                    user("u1"), user("u2", "u1"), book("b"), loan("u1", "b"), rejectLoan("u2", "b"), returnLoan("u1", "b"), loan("u2", "b")),
            reach("v013-N-3.7-then-ok Reader with a hold: delete rejected, hold cancelled, delete succeeds",
                    user("u"), book("b"), hold("h", "u", "b"), rejectDeleteUser("u", "400"), cancelHold("h"), deleteUser("u")),
            reach("v013-N-2.7.4-then-ok Loaned book: delete rejected, returned, delete succeeds",
                    user("u"), book("b"), loan("u", "b"), rejectDeleteBook("b", "400"), returnLoan("u", "b"), deleteBook("b")),
            reach("v013-N-404 Deleted reader: deleting again must answer 404",
                    user("u"), deleteUser("u"), rejectDeleteUser("u", "404")),
            reach("v013-N-404 Deleted book: the detail read must answer 404",
                    book("b"), deleteBook("b"), rejectReadBook("b")),
            reach("v013-N-404 Deleted book: deleting again must answer 404",
                    book("b"), deleteBook("b"), rejectDeleteBook("b", "404")),
            reach("v013-N-404 Returned loan: returning again must answer 404",
                    user("u"), book("b"), loan("u", "b"), returnLoan("u", "b"), rejectDeleteLoan("u", "b", "404")),
            reach("v013-N-404 Cancelled hold: cancelling again must answer 404",
                    user("u"), book("b"), hold("h", "u", "b"), cancelHold("h"), rejectDeleteHold("h", "404")),
            reach("v013-N-FK Loan for a nonexistent book must be rejected",
                    user("u"), rejectLoanMissingBook("u")),
            reach("v013-N-FK Loan for a nonexistent reader must be rejected",
                    book("b"), rejectLoanMissingUser("b")),
            reach("v013-N-FK Hold for a nonexistent book must be rejected",
                    user("u"), rejectHoldMissingBook("u")),
            reach("v013-N-FK Hold for a nonexistent reader must be rejected",
                    book("b"), rejectHoldMissingUser("b")),
            reach("v013-N-404 Never-created reader, book, loan and hold: each delete must answer 404",
                    step("rejectDeleteUser404"), step("rejectDeleteBook404"), step("rejectDeleteLoan404"), step("rejectDeleteHold404")),
            reach("v013-N-mixed Hold and loan on one book by two readers: every delete is rejected until the relations are gone",
                    user("u1"), user("u2", "u1"), book("b"), hold("h", "u1", "b"), loan("u2", "b"),
                    rejectDeleteUser("u1", "400"), rejectDeleteUser("u2", "400"), rejectDeleteBook("b", "400"),
                    cancelHold("h"), rejectDeleteBook("b", "400"), returnLoan("u2", "b"), deleteBook("b"))
    );

    /** Rejection sequences that need a multi-loan reader (contract profile only). */
    public static final List<StrictGuidedRun.Scenario> NEGATIVE_CONTRACT = List.of(
            reach("v013-N-contract Reader with two loans: delete rejected after one return, allowed after both",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), loan("u", "b2"),
                    rejectDeleteUser("u", "400"), returnLoan("u", "b1"), rejectDeleteUser("u", "400"), returnLoan("u", "b2"), deleteUser("u")),
            reach("v013-N-contract Reader with two loans: deleting either book is rejected",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), loan("u", "b2"), rejectDeleteBook("b1", "400"), rejectDeleteBook("b2", "400"))
    );

    /** Rejection sequences that hold only under the original one-loan-per-reader rule. */
    public static final List<StrictGuidedRun.Scenario> NEGATIVE_ORIGINAL = List.of(
            reach("v013-N-original 2.9.3 Reader with a loan: a loan on another book must be rejected",
                    user("u"), book("b1"), book("b2", "b1"), loan("u", "b1"), rejectLoan("u", "b2")),
            reach("v013-N-original Busy reader rejected, another reader takes the other book",
                    user("u1"), user("u2", "u1"), book("b1"), book("b2", "b1"), loan("u1", "b1"), rejectLoan("u1", "b2"), loan("u2", "b2"))
    );

    /** Known model gaps, kept out of the default sets: the model never attempts a loan or hold
     *  for a DELETED entity (its user-book row disappears with it), so these come out STUCK. */
    public static final List<StrictGuidedRun.Scenario> GAPS = List.of(
            reach("v013-gap-3.17 Loan for a deleted book must be rejected (not generated by the model)",
                    user("u"), book("b"), deleteBook("b"), rejectLoan("u", "b")),
            reach("v013-gap-3.17-hold Hold for a deleted reader must be rejected (not generated by the model)",
                    user("u"), book("b"), deleteUser("u"), step("rejectCreateHold400").require("u", "userId").require("b", "bookId"))
    );

    /** Transport self-check: one real loan with server-assigned ids (same as the v011 smoke). */
    public static StrictGuidedRun.Scenario smoke() {
        return reach("v013-transport-smoke", user("reader"), book("book"), loan("reader", "book"));
    }
}
