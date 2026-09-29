const NUMBER_OF_USERS = 3;
const NUMBER_OF_BOOKS = 3;

const RANDOM = new java.util.Random();
var nextUserId = 1;
var nextBookId = 1;
var nextLoanId = 1;
var nextHoldId = 1;

function randomInt() {
  return RANDOM.nextInt(999999);
}

function generateUserId() {
  return nextUserId++;
}

function generateUserName() {
  return "User name " + randomInt();
}

function generateBookId() {
  return nextBookId++;
}

function generateBookTitle() {
  return "Book title " + randomInt();
}

function generateLoanId() {
  return nextLoanId++;
}

function generateHoldId() {
  return nextHoldId++;
}

function generateMissingId(existingId) {
  return Number.parseInt(existingId, 10) + 1000000000;
}

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

//////////////////////////////////////////////////////////////////////////
// Verification bthreads that check system behavior depending on whether
// objects exist in the system.
// These bthreads are triggered by object creation and deletion, and verify
// that the system behaves correctly based on that state.
/////////////////////////////////////////////////////////////////////////

ctx.bthread("verifyUserExistsAfterCreation", "User.All", function (user) {
  // No block() guard: this verify can race a concurrent deletion of the same user. stillRelevant
  // lets verifyUserExists bail out quietly instead of failing when that happens.
  verifyUserExists(user.userid, function () { return entityExists('User.All', userId(user.userid)); });
});

ctx.bthread("verifyCannotDeleteUser", "User.CannotDelete", function (user) {
  tryToDeleteUserAndExpectError(user.userid);
});

ctx.bthread("verifyUserDeletion", function () {
  on(matchAnyUserDeleted(), function (e) {
    let id = extractEventData(e).id;

    verifyUserAbsentFromAllLists(id);
    tryToDeleteDeletedUserAndExpectError(id);
  });
});

ctx.bthread("verifyBookExistsAfterCreation", "Book.All", function (book) {
  // No block() guard: this verify can race a concurrent deletion of the same book. Observed in
  // practice: a book got deleted while verifyBookDetailExists's fuzz-retry loop was still
  // mid-flight, turning an expected 200 into an unexpected 404. stillRelevant lets the verify
  // functions bail out quietly instead of failing when the entity legitimately stopped existing
  // while we were waiting our turn.
  var stillExists = function () { return entityExists('Book.All', bookId(book.bookid)); };
  verifyBookExists(book.bookid, stillExists);
  verifyBookDetailExists(book.bookid, stillExists);
});

bthread("verifyBookDeletion", function () {
  on(matchAnyBookDeleted(), function (e) {
    let id = extractEventData(e).id;

    verifyBookAbsentFromAllLists(id);
    verifyMissingEntityReadIsRejected("Book", id, "/books/" + realBookId(id));
    tryToDeleteDeletedBookAndExpectError(id);
  });
});

ctx.bthread("verifyLoanExistsAfterCreation", "Loan.All", function (loan) {
  verifyLoanExists(loan.bookid, loan.userid, function () { return entityExists('Loan.All', loanId(loan.userid, loan.bookid)); });
});

bthread("verifyLoanDeletion", function () {
  on(matchAnyLoanDeleted(), function (e) {
    let loanData = extractEventData(e);

    verifyLoanAbsentFromAllLists(null, loanData.userId);
    if (loanData.bookId !== undefined && loanData.bookId !== null)
      tryToDeleteDeletedLoanAndExpectError(loanData.userId, loanData.bookId);
  });
});

ctx.bthread("verifyHoldExistsAfterCreation", "Hold.All", function (hold) {
  verifyHoldExists(hold.holdid, function () { return entityExists('Hold.All', holdId(hold.holdid)); });
});

bthread("verifyHoldDeletion", function () {
  on(matchAnyHoldDeleted(), function (e) {
    let id = extractEventData(e).id;

    verifyHoldAbsentFromAllLists(id);
    tryToDeleteDeletedHoldAndExpectError(id);
  });
});

  
ctx.bthread("verifyCannotCreateLoanForBusyUserOrBook", "UserBook.CannotCreateLoan", function (userbook) {
  tryToCreateLoanAndExpectError(userbook.userid, userbook.bookid, generateLoanId());
});


/////////////////////////////////////////////////////////////////////////
// Bthreads that create random stand-alone objects: users and books.
// These objects can be created without preconditions and are then used by
// other bthreads to create more complex objects such as loans and holds.
/////////////////////////////////////////////////////////////////////////

bthread("createRandomUsers", function () {
  for (let i = 0; i < NUMBER_OF_USERS; i++) {
    createUser(generateUserId(), generateUserName());
  }
});

bthread("createRandomBooks", function () {
  for (let i = 0; i < NUMBER_OF_BOOKS; i++) {
    createBook(generateBookId(), generateBookTitle());
  }
});


//////////////////////////////////////////////////////////////////////////
// Bthreads that create more complex objects, such as loans and holds,
// based on the existence of simpler objects like users and books.
// These bthreads are triggered by user and book creation and then create
// loans and holds from those existing objects.
//////////////////////////////////////////////////////////////////////////
// stillRelevant re-checks UserBook.CanCreateLoan for this pair right before the REST call fires,
// since this bthread only checks it once, when spawned for a pair that just became eligible.
ctx.bthread("createLoan", "UserBook.CanCreateLoan", function (userbook) {
    createLoan(userbook.userid, userbook.bookid, generateLoanId(), undefined, undefined, undefined, undefined,
        function () {
            return ctx.runQuery('UserBook.CanCreateLoan').some(function (pair) {
                return sameId(pair.userid, userbook.userid) && sameId(pair.bookid, userbook.bookid);
            });
        });
});

ctx.bthread("verifyCannotCreateLoan", "UserBook.CannotCreateLoan", function (userbook) {
    tryToCreateLoanAndExpectError(userbook.userid, userbook.bookid, generateLoanId());
});

ctx.bthread("createHold", "UserBook.CanCreateHold", function (userbook) {
    createHold(userbook.bookid, generateHoldId(), userbook.userid);
});

// verifyCannotCreateHold was removed: the SUT now assigns the hold's id itself and silently
// ignores any client-supplied "id" field, so there is no client-chosen id left that could
// collide with an existing one. See the RTV helpers (realHoldId etc.) in interfaces.library.js.
// (UserBook.CannotCreateHold has always returned false - unlike loans, nothing makes a user-book
// pair permanently ineligible to hold - so this bthread never actually fired.)


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

// deleteUser/deleteBook used to wrap their call in block(matchAddHoldOrLoanForUser/Book(...), ...)
// to guard against a concurrently-created hold/loan turning the delete's expected 200 into a 400.
// That guard matched on candidate (not-yet-sent) createLoan/createHold events by shape, so it
// vetoed those events' own valid-shaped variants for as long as this delete offer was merely
// pending -- and since User.CanDelete/Book.CanDelete become eligible the moment the entity is
// created, this permanently blocked a fresh user/book's own createLoan(...) from ever completing
// before the entity got deleted out from under it. Removed; no replacement guard yet.
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
// Additional negative verifiers.
//
// These bthreads cover entity-specific rejection cases that are supported by
// the interface layer and SUT but are not part of the basic CRUD flow above.
//////////////////////////////////////////////////////////////////////////

// verifyCannotCreateDuplicateBook was removed: the SUT now assigns book ids itself (see
// generate_unique_id in sut.py), so there is no client-chosen id left that could collide with an
// existing one. See the RTV helpers (realBookId etc.) in interfaces.library.js.

ctx.bthread("verifyCannotCreateBookWithBadParameters", "Book.All", function (book) {
  tryToCreateBookWithBadParametersAndExpectError(book.bookid);
});

ctx.bthread("verifyCannotDeleteBook", "Book.CannotDelete", function (book) {
  tryToDeleteBookAndExpectError(book.bookid);
});

ctx.bthread("verifyHoldOnlyBlocksUserAndBookDeletion", "Hold.All", function (hold) {
  tryToDeleteUserAndExpectError(hold.userid);
  tryToDeleteBookAndExpectError(hold.bookid);

  // The general deleteHold bthread is the single valid deletion path for this
  // hold. Doing an extra delete here creates a second valid delete on the same
  // resource, which can race and turn a valid 200 into an unexpected 404.
});

ctx.bthread("verifyCannotCreateLoanWithBadParameters", "UserBook.All", function (userbook) {
  tryToCreateLoanWithBadParametersAndExpectError(userbook.userid);
});

ctx.bthread("verifyCannotCreateLoanWithNonexistentForeignKeys", "UserBook.All", function (userbook) {
  let missingUserId = generateMissingId(userbook.userid);
  let missingBookId = generateMissingId(userbook.bookid);


  // Gera: I think trying all three is too much, enough to try one of the three nondeterministically?
  tryToCreateLoanWithNonexistentUserAndExpectError(missingUserId, userbook.bookid, generateLoanId());
  tryToCreateLoanWithNonexistentBookAndExpectError(userbook.userid, missingBookId, generateLoanId());
  tryToCreateLoanWithNonexistentUserAndBookAndExpectError(missingUserId, missingBookId, generateLoanId());
});

ctx.bthread("verifyCannotCreateHoldWithBadParameters", "Hold.All", function (hold) {
  tryToCreateHoldWithBadParametersAndExpectError(hold.holdid, hold.userid);
});

ctx.bthread("verifyCannotCreateHoldWithNonexistentForeignKeys", "UserBook.All", function (userbook) {
  let missingUserId = generateMissingId(userbook.userid);
  let missingBookId = generateMissingId(userbook.bookid);

  // Gera: I think trying all three is too much, enough to try one of the three nondeterministically?
  tryToCreateHoldWithNonexistentUserAndExpectError(userbook.bookid, generateHoldId(), missingUserId);
  tryToCreateHoldWithNonexistentBookAndExpectError(missingBookId, generateHoldId(), userbook.userid);
  tryToCreateHoldWithNonexistentUserAndBookAndExpectError(missingBookId, generateHoldId(), missingUserId);
});

//////////////////////////////////////////////////////////////////////////
// Read, malformed-delete, and unsupported-update API verifiers.
//
// The Library SUT exposes list reads for every entity and a detail read only
// for books. It does not expose update routes, so update coverage verifies
// that PUT attempts are rejected with 405.
//////////////////////////////////////////////////////////////////////////


// Gera: I think that trying nonexisting interfaces may be too much?
ctx.bthread("verifyCannotUpdateUser", "User.All", function (user) {
  tryToUpdateUserAndExpectError(user.userid, { id: user.userid, name: "Updated user " + user.userid }, 405);
});

ctx.bthread("verifyCannotUpdateBook", "Book.All", function (book) {
  tryToUpdateBookAndExpectError(book.bookid, { id: book.bookid, title: "Updated book " + book.bookid }, 405);
});

ctx.bthread("verifyCannotUpdateLoan", "Loan.All", function (loan) {
  tryToUpdateLoanAndExpectError(loan.userid, loan.bookid, { userId: loan.userid, bookId: loan.bookid }, 405);
});

ctx.bthread("verifyCannotUpdateHold", "Hold.All", function (hold) {
  tryToUpdateHoldAndExpectError(hold.holdid, hold.userid, hold.bookid, { id: hold.holdid, userId: hold.userid, bookId: hold.bookid }, 405);
});

// Gera: Why only users? Why not also books, loans and holds?
bthread("tryToDeleteNonexistingUser", function () {
  tryToDeleteNonexistingUserAndExpectError(generateMissingId(generateUserId()));
});

// =========================================================================
// The Fuzzing Interface Layer Contract
// =========================================================================
// Whenever a story requests an action (create, delete, or retrieve an object),
// the interface layer executes a pre-flight fuzzing and verification sequence
// IF the SUT actually defines rejection semantics for that action. Some reads
// (see point 4) have no invalid variant to fuzz and skip straight to the request.
//
// 1. Event Generation & Fuzzing:
//    The interface defines and requests a set of fuzzed request events:
//    - Valid Variants: Requests with parameters passed in different orders, types
//      (e.g., stringified integers), or padded values, which the SUT should accept.
//    - Invalid Variants: Requests with missing fields, incorrect types, nulls,
//      negatives, or empty values, designed to verify the SUT's rejection logic.
//
// 2. Fuzzing Loop execution:
//    The system enters a synchronization block requesting the union of all valid
//    and invalid events:
//    - If an invalid event is selected: The interface immediately executes a REST
//      request asserting that the SUT rejects it (expected code 400). It then loops
//      to request the event set again.
//    - If a valid event is selected: The interface executes the successful REST
//      request (expecting 200 or 201) and exits the loop.
//
// 3. Retrieve actions and the fuzzing loop:
//    A read only gets the fuzzing loop (points 1-2) when the SUT itself validates
//    the read's parameters and can reject it with 400:
//    - Book detail reads (GET /books/{id}) validate the id path segment, so
//      verifyBookDetailExists fuzzes it exactly like a delete action.
//    - Loan list reads (GET /loans) validate userId/bookId query parameters, so
//      verifyLoanExists fuzzes them the same way.
//    - Book/user/hold list reads (GET /books|/users|/holds) accept any `q` value
//      and always answer 200 - there is no invalid variant, so verifyBookExists,
//      verifyUserExists, and verifyHoldExists read the SUT list directly instead
//      of running the fuzzing loop. Point 3's synchronization rule does not apply
//      to these EventSets either, since nothing blocks or waits on a plain read.
//
