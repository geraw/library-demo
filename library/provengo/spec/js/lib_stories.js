const NUMBER_OF_USERS = 4;
const NUMBER_OF_BOOKS = 4;

// AtomicInteger, not a plain JS `var n = 1; n++`: BPjs runs b-thread steps concurrently on a
// thread pool, and a JS ++ on a shared global is not atomic, so two ctx.bthreads (e.g. two
// createHold instances) could be handed the same id.
const nextUserId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextBookId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextLoanId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextHoldId = new java.util.concurrent.atomic.AtomicInteger(1);
// Ids that are deliberately never created. They start far above anything the counters above or
// the SUT will ever issue, so a "missing" id can never collide with a real entity.
const nextMissingId = new java.util.concurrent.atomic.AtomicInteger(1000000001);

function generateUserId() { return nextUserId.getAndIncrement(); }
function generateBookId() { return nextBookId.getAndIncrement(); }
function generateLoanId() { return nextLoanId.getAndIncrement(); }
function generateHoldId() { return nextHoldId.getAndIncrement(); }
function generateMissingId() { return nextMissingId.getAndIncrement(); }

// Names and titles are derived from the id, so the same scenario produces the same events in
// every run and sample: failing runs reproduce and coverage is comparable across samples.
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

ctx.bthread("verifyCannotDeleteUser", "User.CannotDelete", function (user) {
  tryToDeleteUserAndExpectError(user.userid);
});

forEachEvent("verifyUserDeletion", AnyUserDeleted, function (e) {
  let id = extractEventData(e).id;

  verifyUserAbsent(id);
  tryToDeleteDeletedUserAndExpectError(id);
});

ctx.bthread("verifyBookExistsAfterCreation", "Book.All", function (book) {
  verifyBookExists(book.bookid);
  verifyBookDetailExists(book.bookid);
});

ctx.bthread("verifyCannotDeleteBook", "Book.CannotDelete", function (book) {
  tryToDeleteBookAndExpectError(book.bookid);
});

forEachEvent("verifyBookDeletion", AnyBookDeleted, function (e) {
  let id = extractEventData(e).id;

  verifyBookAbsent(id);
  verifyMissingEntityReadIsRejected("Book", id, "/books/" + sutBookIdRef(id));
  tryToDeleteDeletedBookAndExpectError(id);
});

ctx.bthread("verifyLoanExists", "Loan.All", function (loan) {
  verifyLoanExists(loan.userid, loan.bookid);
});

ctx.bthread("verifyCannotCreateLoan", "UserBook.CannotCreateLoan", function (userbook) {
  tryToCreateLoanAndExpectError(userbook.userid, userbook.bookid, generateLoanId());
});

// Unlike users/books/holds, a loan's identity is its userId/bookId pair, so the same loan can be
// re-created while these checks wait their turn. Wait for that too: once it happens the loan
// exists again, so the absence checks no longer apply (verifyLoanExists covers the new loan).
forEachEvent("verifyLoanDeletion", AnyLoanDeleted, function (e) {
  let loan = extractEventData(e);
  let reloaned = matchLoanAdded(loan.userId, loan.bookId);

  waitFor(reloaned, function () {
    if (!reloaned.contains(verifyLoanAbsent(loan.userId, loan.bookId)))
      tryToDeleteDeletedLoanAndExpectError(loan.userId, loan.bookId);
  });
});

ctx.bthread("verifyHoldExistsAfterCreation", "Hold.All", function (hold) {
  verifyHoldExists(hold.holdid);
});

forEachEvent("verifyHoldDeletion", AnyHoldDeleted, function (e) {
  let id = extractEventData(e).id;

  verifyHoldAbsent(id);
  tryToDeleteDeletedHoldAndExpectError(id);
});

/////////////////////////////////////////////////////////////////////////
// Bthreads that create random stand-alone objects: users and books.
// These objects can be created without preconditions and are then used by
// other bthreads to create more complex objects such as loans and holds.
/////////////////////////////////////////////////////////////////////////

bthread("createRandomUsers", function () {
  for (let i = 0; i < NUMBER_OF_USERS; i++) {
    let id = generateUserId();
    createUser(id, userName(id));
  }
});

bthread("createRandomBooks", function () {
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
// There is an issue with the sampling mechanism here because it is eager
// to delete objects, which can lead to a situation where all objects are deleted
// before complex scenarios can be fully explored. A more sophisticated sampling.
// A poor-man remedy for this is to decrease the probability of deletion, which can
// be done by adding a random chance to the deletion bthreads.
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
// run - not once per user-book pair.
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
// Step 1: The Interface Layer Contract
// =========================================================================
// Whenever a story requests an action (create, delete, or retrieve an object),
// the interface layer sends exactly one REST request for it, with the response
// code the SUT is expected to answer (201/200 for the action functions, 400/404
// for the tryTo*AndExpectError functions). One call in a story is one event in
// the trace. Negative stories only exercise business rules (blocked deletes,
// forbidden loans, nonexistent or deleted entities); the model never sends a
// malformed request or calls an unsupported route.
//


// =========================================================================
// Step two: Coverage
// =========================================================================
// Once we have a full tested model for all possible tetsts, we can add coverage
// criteria to chose a small set of tests that cover all the possible scenarios.
//
// We see three different types of coverage criteria that we can use to select a small set of tests from the full set of tests:
//
// 1) Parameter Coverage: We can select a small set of tests that cover all the possible parameters to an endpoint.
//
// 2) State Coverage: We can select a small set of tests that cover all the possible states of the system.
//
// 3) Sequence Coverage: We can select a small set of tests that cover all the possible sequences of events that lead to the same styate.
//
// For CRUD, we believe that state + (or \times)  parameter coverage is sufficient, since the sequence of events does not matter as much as the state and parameters.
