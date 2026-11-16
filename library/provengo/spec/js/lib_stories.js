const NUMBER_OF_USERS = 4;
const NUMBER_OF_BOOKS = 4;

// Ids and labels. AtomicInteger, not a plain JS `var n = 1; n++`: BPjs runs b-thread steps
// concurrently on a thread pool, and a JS ++ on a shared global is not atomic, so two
// ctx.bthreads could be handed the same number. The counters make numbers unique, not
// repeatable: which pair gets which hold number depends on scheduling, so a scenario's identity
// is its reader/book pairs, not its hold and loan numbers (those are labels that reach the DAL
// and the trace descriptions only, never the wire).
const nextUserId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextBookId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextLoanId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextHoldId = new java.util.concurrent.atomic.AtomicInteger(1);
// Reader and book ids that are deliberately never created, for the nonexistent-foreign-key and
// nonexistent-delete checks. They are sent on the wire as plain ids, and start far above anything
// the counters above or the SUT will ever issue, so they can never collide with a real entity.
const nextMissingId = new java.util.concurrent.atomic.AtomicInteger(1000000001);

function generateUserId() { return nextUserId.getAndIncrement(); }
function generateBookId() { return nextBookId.getAndIncrement(); }
function generateLoanId() { return nextLoanId.getAndIncrement(); }
function generateHoldId() { return nextHoldId.getAndIncrement(); }
function generateMissingId() { return nextMissingId.getAndIncrement(); }

// Names and titles are derived from the id, so a given reader or book is created by the same
// request in every run and sample.
function userName(id) { return "User name " + id; }
function bookTitle(id) { return "Book title " + id; }

//////////////////////////////////////////////////////////////////////////
// Story layer.
//
// This file describes test behavior: which operations should be attempted,
// blocked, verified, or repeated under different domain states. It should use
// the public APIs exposed by the interface layer and the query API exposed by
// the DAL. It should not update Context entities directly and should avoid
// duplicating the DAL's domain rules.
//
// Separation of concerns in this model:
// - interfaces.library.js owns REST calls, EventSets, and event-data extraction.
// - dal.js owns Context entities, effects, and queries over the model.
// - lib_stories.js owns behavioral scenarios and verification timing.
//
// Two structural rules keep every check reachable on its own:
// - Independent checks are independent b-threads. A b-thread that chains two
//   requests makes the second reachable only after the first.
// - A rule that holds while some relation exists is re-checked after every change
//   to the relations it depends on (recheckAfterEveryRelationChange), so a
//   rejection remains reachable after an unrelated relation was removed.
//////////////////////////////////////////////////////////////////////////

// Runs `handler` for every event in `eventSet`, each in a b-thread of its own. Unlike on(), the
// watcher is back at waitFor() as soon as it has spawned the handler, so a second event of the
// same kind is never missed while the handler for the first one is still syncing.
function forEachEvent(name, eventSet, handler) {
  bthread(name, function () {
    while (true) {
      let e = waitFor(eventSet);
      bthread(name + " [" + e.data.parameters.description + "]", function () { handler(e); });
    }
  });
}

// Re-issues `check` after every event in `changes`, for as long as this b-thread lives. Used
// inside a ctx.bthread: COBP ends the live copy in the very sync that selects the event removing
// its entity from the query (see __sync__ in Provengo's context library), so no check is ever
// issued for a relation that is already gone. Two live copies that issue an equal request (same
// name and data) are both satisfied by one selection, which is why "once per relation" would not
// be enough: after the loan-based and hold-based checks of one book were satisfied together by a
// single rejected delete, cancelling the hold must re-offer the loan-based check.
function recheckAfterEveryRelationChange(changes, check) {
  while (true) {
    check();
    waitFor(changes);
  }
}

//////////////////////////////////////////////////////////////////////////
// Verification bthreads that check system behavior depending on whether
// objects exist in the system.
// These bthreads are triggered by object creation and deletion, and verify
// that the system behaves correctly based on that state.
/////////////////////////////////////////////////////////////////////////

// The verify*Exists b-threads below need no guard against a concurrent deletion of their entity:
// COBP ends a ctx.bthread at the very event that removes its entity from the query it was spawned
// for, so none of them can ever run against an entity that no longer exists.
ctx.bthread("verifyUserExistsAfterCreation", "User.All", function (user) {
  verifyUserExists(user.userid);
});

// A reader or a book cannot be deleted while a loan or a hold refers to it: one check per
// blocking relation, re-issued after every change to the loans and holds.
ctx.bthread("verifyLoanBlocksUserDeletion", "Loan.All", function (loan) {
  recheckAfterEveryRelationChange(AnyRelationChanged, function () { tryToDeleteUserAndExpectError(loan.userid); });
});

ctx.bthread("verifyHoldBlocksUserDeletion", "Hold.All", function (hold) {
  recheckAfterEveryRelationChange(AnyRelationChanged, function () { tryToDeleteUserAndExpectError(hold.userid); });
});

// After a deletion, each check is its own b-thread (see forEachEvent): the reads of each list,
// the 404 on a detail read, and the 404 on a repeated delete are independent, so none of them
// is reachable only after another.
forEachEvent("verifyUserAbsentFromUsersAfterDeletion", AnyUserDeleted, function (e) {
  verifyUserAbsentFromUsers(extractEventData(e).id);
});

forEachEvent("verifyUserAbsentFromLoansAfterDeletion", AnyUserDeleted, function (e) {
  verifyUserAbsentFromLoans(extractEventData(e).id);
});

forEachEvent("verifyUserAbsentFromHoldsAfterDeletion", AnyUserDeleted, function (e) {
  verifyUserAbsentFromHolds(extractEventData(e).id);
});

forEachEvent("verifyDeletedUserCannotBeDeletedAgain", AnyUserDeleted, function (e) {
  tryToDeleteDeletedUserAndExpectError(extractEventData(e).id);
});

ctx.bthread("verifyBookExistsAfterCreation", "Book.All", function (book) {
  verifyBookExists(book.bookid);
});

ctx.bthread("verifyBookDetailExistsAfterCreation", "Book.All", function (book) {
  verifyBookDetailExists(book.bookid);
});

ctx.bthread("verifyLoanBlocksBookDeletion", "Loan.All", function (loan) {
  recheckAfterEveryRelationChange(AnyRelationChanged, function () { tryToDeleteBookAndExpectError(loan.bookid); });
});

ctx.bthread("verifyHoldBlocksBookDeletion", "Hold.All", function (hold) {
  recheckAfterEveryRelationChange(AnyRelationChanged, function () { tryToDeleteBookAndExpectError(hold.bookid); });
});

forEachEvent("verifyBookAbsentFromBooksAfterDeletion", AnyBookDeleted, function (e) {
  verifyBookAbsentFromBooks(extractEventData(e).id);
});

forEachEvent("verifyBookAbsentFromLoansAfterDeletion", AnyBookDeleted, function (e) {
  verifyBookAbsentFromLoans(extractEventData(e).id);
});

forEachEvent("verifyBookAbsentFromHoldsAfterDeletion", AnyBookDeleted, function (e) {
  verifyBookAbsentFromHolds(extractEventData(e).id);
});

forEachEvent("verifyDeletedBookDetailIsRejected", AnyBookDeleted, function (e) {
  let id = extractEventData(e).id;
  verifyMissingEntityReadIsRejected("Book", id, "/books/" + sutBookIdRef(id));
});

forEachEvent("verifyDeletedBookCannotBeDeletedAgain", AnyBookDeleted, function (e) {
  tryToDeleteDeletedBookAndExpectError(extractEventData(e).id);
});

ctx.bthread("verifyLoanExists", "Loan.All", function (loan) {
  verifyLoanExists(loan.userid, loan.bookid);
});

// A loan the rules forbid stays forbidden until the loans change (holds never affect loans).
ctx.bthread("verifyCannotCreateLoan", "UserBook.CannotCreateLoan", function (userbook) {
  recheckAfterEveryRelationChange(AnyLoanChanged, function () { tryToCreateLoanAndExpectError(userbook.userid, userbook.bookid, generateLoanId()); });
});

// Unlike users/books/holds, a loan's identity is its userId/bookId pair, so the same loan can be
// re-created while these checks wait their turn. Wait for that too: once it happens the loan
// exists again, so the absence checks no longer apply (verifyLoanExists covers the new loan).
forEachEvent("verifyLoanAbsentAfterDeletion", AnyLoanDeleted, function (e) {
  let loan = extractEventData(e);
  waitFor(matchLoanAdded(loan.userId, loan.bookId), function () {
    verifyLoanAbsent(loan.userId, loan.bookId);
  });
});

forEachEvent("verifyDeletedLoanCannotBeDeletedAgain", AnyLoanDeleted, function (e) {
  let loan = extractEventData(e);
  waitFor(matchLoanAdded(loan.userId, loan.bookId), function () {
    tryToDeleteDeletedLoanAndExpectError(loan.userId, loan.bookId);
  });
});

ctx.bthread("verifyHoldExistsAfterCreation", "Hold.All", function (hold) {
  verifyHoldExists(hold.holdid);
});

forEachEvent("verifyHoldAbsentAfterDeletion", AnyHoldDeleted, function (e) {
  verifyHoldAbsent(extractEventData(e).id);
});

forEachEvent("verifyDeletedHoldCannotBeDeletedAgain", AnyHoldDeleted, function (e) {
  tryToDeleteDeletedHoldAndExpectError(extractEventData(e).id);
});

/////////////////////////////////////////////////////////////////////////
// Bthreads that create the stand-alone objects: users and books.
// These objects can be created without preconditions and are then used by
// other bthreads to create more complex objects such as loans and holds.
/////////////////////////////////////////////////////////////////////////

bthread("createUsers", function () {
  for (let i = 0; i < NUMBER_OF_USERS; i++) {
    let id = generateUserId();
    createUser(id, userName(id));
  }
});

bthread("createBooks", function () {
  for (let i = 0; i < NUMBER_OF_BOOKS; i++) {
    let id = generateBookId();
    createBook(id, bookTitle(id));
  }
});

//////////////////////////////////////////////////////////////////////////
// Bthreads that create more complex objects, such as loans and holds,
// based on the existence of simpler objects like users and books.
// These bthreads are triggered by user and book creation and then create
// loans and holds from those existing objects.
//////////////////////////////////////////////////////////////////////////

ctx.bthread("createLoan", "UserBook.CanCreateLoan", function (userbook) {
  createLoan(userbook.userid, userbook.bookid, generateLoanId());
});

ctx.bthread("createHold", "UserBook.CanCreateHold", function (userbook) {
  createHold(generateHoldId(), userbook.userid, userbook.bookid);
});

/////////////////////////////////////////////////////////////////////////
// Bthreads that delete objects from the system, based on their existence.
// These bthreads are triggered by the existence of objects and then delete
// those objects, which in turn triggers the verification bthreads to check
// that the system behaves correctly after deletion.
//
// The sampler is eager to delete: a deletion is offered as soon as an entity
// exists, so many samples delete readers and books before any loan or hold was
// created (measured in campaign-v013's sampling coverage). Lowering the weight
// of the deletion events in the sampler is the remedy; the model itself does
// not need to change.
/////////////////////////////////////////////////////////////////////////

ctx.bthread("deleteUser", "User.CanDelete", function (user) {
  deleteUser(user.userid);
});

ctx.bthread("deleteBook", "Book.CanDelete", function (book) {
  deleteBook(book.bookid);
});

ctx.bthread("deleteLoan", "Loan.All", function (loan) {
  deleteLoan(loan.userid, loan.bookid, loan.loanid);
});

ctx.bthread("deleteHold", "Hold.All", function (hold) {
  deleteHold(hold.holdid, hold.userid, hold.bookid);
});

//////////////////////////////////////////////////////////////////////////
// Entities that do not exist.
//
// A nonexistent foreign key only needs some existing entity on the other side
// of the pair, so each check runs once per user, once per book, or once per
// run - not once per user-book pair. Loan and hold numbers passed here are
// labels for the rejected request; the SUT never sees them.
//////////////////////////////////////////////////////////////////////////

ctx.bthread("verifyCannotCreateLoanWithNonexistentBook", "User.All", function (user) {
  tryToCreateLoanWithNonexistentBookAndExpectError(user.userid, generateMissingId(), generateLoanId());
});

ctx.bthread("verifyCannotCreateLoanWithNonexistentUser", "Book.All", function (book) {
  tryToCreateLoanWithNonexistentUserAndExpectError(generateMissingId(), book.bookid, generateLoanId());
});

bthread("verifyCannotCreateLoanWithNonexistentUserAndBook", function () {
  tryToCreateLoanWithNonexistentUserAndBookAndExpectError(generateMissingId(), generateMissingId(), generateLoanId());
});

ctx.bthread("verifyCannotCreateHoldWithNonexistentBook", "User.All", function (user) {
  tryToCreateHoldWithNonexistentBookAndExpectError(generateHoldId(), user.userid, generateMissingId());
});

ctx.bthread("verifyCannotCreateHoldWithNonexistentUser", "Book.All", function (book) {
  tryToCreateHoldWithNonexistentUserAndExpectError(generateHoldId(), generateMissingId(), book.bookid);
});

bthread("verifyCannotCreateHoldWithNonexistentUserAndBook", function () {
  tryToCreateHoldWithNonexistentUserAndBookAndExpectError(generateHoldId(), generateMissingId(), generateMissingId());
});

bthread("tryToDeleteNonexistingUser", function () {
  tryToDeleteNonexistingUserAndExpectError(generateMissingId());
});

bthread("tryToDeleteNonexistingBook", function () {
  tryToDeleteNonexistingBookAndExpectError(generateMissingId());
});

bthread("tryToDeleteNonexistingLoan", function () {
  tryToDeleteNonexistingLoanAndExpectError(generateMissingId(), generateMissingId());
});

bthread("tryToDeleteNonexistingHold", function () {
  tryToDeleteNonexistingHoldAndExpectError(generateMissingId());
});

// =========================================================================
// The interface layer contract
// =========================================================================
// Whenever a story requests an action (create, delete, or retrieve an object),
// the interface layer sends exactly one REST request for it, with the response
// code the SUT is expected to answer: 201/200 for the action functions, 400/404
// for the rejection checks (tryTo*AndExpectError and
// verifyMissingEntityReadIsRejected). One call in a story is one event in the
// trace. Negative stories only exercise business rules (blocked deletes,
// forbidden loans, nonexistent or deleted entities); the model never sends a
// malformed request or calls a route the service does not expose.
//
// Known gap: the model never attempts a loan or a hold for an entity that was
// DELETED (its user-book row disappears with it); "a loan for a nonexistent
// entity is rejected" is exercised with ids that were never created instead.

// =========================================================================
// Coverage
// =========================================================================
// Once the model generates all the tests we care about, coverage criteria select
// a small suite from the full set. Three kinds apply to this CRUD service:
//
// 1) State coverage: the abstract states of the system (readers, books, loans,
//    holds, and their relations) that the suite visits.
// 2) Rule coverage: every business-rule rejection exercised at least once.
// 3) Sequence coverage: the orders of events that lead to the same state.
//
// For CRUD, state coverage combined with rule coverage is what matters; the
// order of events matters less than the states and the rules exercised in them.
// campaign-v013 measures all three (guided reachability, trigger reachability,
// abstract-state saturation).
