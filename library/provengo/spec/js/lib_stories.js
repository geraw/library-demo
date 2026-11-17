//@provengo summon ctrl

const NUMBER_OF_USERS = 4;
const NUMBER_OF_BOOKS = 4;

// Ids are derived from the entities they belong to, never drawn from a shared counter: BPjs
// runs b-thread steps concurrently between sync points, so a counter shared by several
// b-threads would hand out numbers in an order that depends on scheduling, and the same event
// selection would then produce different traces. With everything derived, the trace is a
// function of the selected events alone.
//
// - Readers and books are numbered 1..NUMBER_OF_* by the single b-thread that creates them.
// - A hold's id is derived from its reader/book pair and from how many holds that pair created
//   before (the DAL's hold records): pair index + occurrence * NUMBER_OF_USERS * NUMBER_OF_BOOKS.
//   A pair creates at most one hold at a time, so the occurrence is read when the hold is
//   requested, and an id never repeats even when a pair holds again after a cancellation.
// - A loan has no number: the service and the model both identify it by its pair.
// - Ids that are deliberately never created (nonexistent-foreign-key and nonexistent-delete
//   checks) are 1000000000 plus the id of the entity on the other side, or a small constant;
//   they are sent as plain ids and can never collide with a real entity.
function holdIdFor(userId, bookId) {
  var pairIndex = (asInteger(userId) - 1) * NUMBER_OF_BOOKS + asInteger(bookId);
  return pairIndex + holdsCreatedFor(userId, bookId) * NUMBER_OF_USERS * NUMBER_OF_BOOKS;
}
function missingId(n) { return 1000000000 + asInteger(n); }

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

// Some existing entity of `query`, to pair a deleted entity with, or null when none exists.
// Which one is immaterial: the request is rejected for the deleted side. Readers and books are
// created once (1..N), so when none is left the check is skipped rather than waited for.
function anyExisting(query) {
  let all = ctx.runQuery(query);
  return all.length > 0 ? all[0] : null;
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

// A deleted reader can neither borrow nor hold; its user-book rows are gone, so these checks
// pair it with whichever book exists (skipped when no book is left).
forEachEvent("verifyDeletedUserCannotLoan", AnyUserDeleted, function (e) {
  let book = anyExisting('Book.All');
  if (book) tryToCreateLoanWithDeletedUserAndExpectError(extractEventData(e).id, book.bookid);
});

forEachEvent("verifyDeletedUserCannotHold", AnyUserDeleted, function (e) {
  let book = anyExisting('Book.All');
  if (book) tryToCreateHoldWithDeletedUserAndExpectError(extractEventData(e).id, book.bookid);
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

forEachEvent("verifyDeletedBookCannotBeLoaned", AnyBookDeleted, function (e) {
  let user = anyExisting('User.All');
  if (user) tryToCreateLoanWithDeletedBookAndExpectError(user.userid, extractEventData(e).id);
});

forEachEvent("verifyDeletedBookCannotBeHeld", AnyBookDeleted, function (e) {
  let user = anyExisting('User.All');
  if (user) tryToCreateHoldWithDeletedBookAndExpectError(user.userid, extractEventData(e).id);
});

ctx.bthread("verifyLoanExists", "Loan.All", function (loan) {
  verifyLoanExists(loan.userid, loan.bookid);
});

// A loan the rules forbid stays forbidden until the loans change (holds never affect loans).
ctx.bthread("verifyCannotCreateLoan", "UserBook.CannotCreateLoan", function (userbook) {
  recheckAfterEveryRelationChange(AnyLoanChanged, function () { tryToCreateLoanAndExpectError(userbook.userid, userbook.bookid); });
});

// Recheck surviving loans after relationship removals, not only at creation.
// One Context-managed bthread per Loan.All incarnation avoids detached checks:
// Context ends it when that loan disappears, including return/recreation of the
// same user/book pair. A new incarnation receives its own fresh bthread.
// Do not spawn a new bthread per removal: that can accumulate duplicate checks
// and leave reads pending for loans that have already been returned.
// Reads remain ordinary selectable events; no block forces an immediate GET.
// While a read is pending, further removals coalesce into that check. This bounds
// pending work, but deliberately does not promise one check per removal.
// GETs do not trigger this story, so verification cannot trigger itself.
// In the compact model verifyLoanExists emits only the valid read; full response
// comparison belongs to the replay oracle, not to this scheduling story.
ctx.bthread("verifyActiveLoanAfterRelationshipRemoval", "Loan.All", function (loan) {
  var relationshipRemoved = bp.EventSet("Loan or hold removed", function (event) {
    return matchAnyHoldDeleted().contains(event) ||
           matchAnyLoanDeleted().contains(event);
  });

  while (true) {
    waitFor(relationshipRemoved);
    verifyLoanExists(loan.bookid, loan.userid);
  }
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
  for (let id = 1; id <= NUMBER_OF_USERS; id++) {
    createUser(id, userName(id));
  }
});

bthread("createBooks", function () {
  for (let id = 1; id <= NUMBER_OF_BOOKS; id++) {
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
  createLoan(userbook.userid, userbook.bookid);
});

ctx.bthread("createHold", "UserBook.CanCreateHold", function (userbook) {
  createHold(holdIdFor(userbook.userid, userbook.bookid), userbook.userid, userbook.bookid);
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
  deleteLoan(loan.userid, loan.bookid);
});

ctx.bthread("deleteHold", "Hold.All", function (hold) {
  deleteHold(hold.holdid, hold.userid, hold.bookid);
});

//////////////////////////////////////////////////////////////////////////
// Entities that do not exist.
//
// A nonexistent foreign key only needs some existing entity on the other side
// of the pair, so each check runs once per user, once per book, or once per
// run - not once per user-book pair. The missing id is derived from the
// existing side (missingId(u) is "the book reader u asks for that does not
// exist"); the once-per-run checks use small constants.
//////////////////////////////////////////////////////////////////////////

ctx.bthread("verifyCannotCreateLoanWithNonexistentBook", "User.All", function (user) {
  tryToCreateLoanWithNonexistentBookAndExpectError(user.userid, missingId(user.userid));
});

ctx.bthread("verifyCannotCreateLoanWithNonexistentUser", "Book.All", function (book) {
  tryToCreateLoanWithNonexistentUserAndExpectError(missingId(book.bookid), book.bookid);
});

bthread("verifyCannotCreateLoanWithNonexistentUserAndBook", function () {
  tryToCreateLoanWithNonexistentUserAndBookAndExpectError(missingId(1), missingId(2));
});

ctx.bthread("verifyCannotCreateHoldWithNonexistentBook", "User.All", function (user) {
  tryToCreateHoldWithNonexistentBookAndExpectError(user.userid, missingId(user.userid));
});

ctx.bthread("verifyCannotCreateHoldWithNonexistentUser", "Book.All", function (book) {
  tryToCreateHoldWithNonexistentUserAndExpectError(missingId(book.bookid), book.bookid);
});

bthread("verifyCannotCreateHoldWithNonexistentUserAndBook", function () {
  tryToCreateHoldWithNonexistentUserAndBookAndExpectError(missingId(1), missingId(2));
});

bthread("tryToDeleteNonexistingUser", function () {
  tryToDeleteNonexistingUserAndExpectError(missingId(1));
});

bthread("tryToDeleteNonexistingBook", function () {
  tryToDeleteNonexistingBookAndExpectError(missingId(1));
});

bthread("tryToDeleteNonexistingLoan", function () {
  tryToDeleteNonexistingLoanAndExpectError(missingId(1), missingId(2));
});

bthread("tryToDeleteNonexistingHold", function () {
  tryToDeleteNonexistingHoldAndExpectError(missingId(1));
});

//////////////////////////////////////////////////////////////////////////
// Coverage markers for ensemble ranking (state coverage).
//
// These bthreads don't drive any behavior - they emit a marker event whenever
// a hand-picked domain state becomes true, reusing the DAL's own queries so
// the detection logic isn't duplicated here. meta-spec/ensemble-code.js reads
// these markers back out of sampled traces to score ensembles by how many
// distinct features (STATE_FEATURES there) they exercise. Ctrl.doMark is used
// instead of a plain event offer so markers reliably win selection at busy
// synchronization points.
//////////////////////////////////////////////////////////////////////////

// Guards against two bthreads racing to mark the same feature (e.g. reachable via either a loan
// or a hold path): only the first caller for a given name emits the marker per trace.
const markedFeaturesThisTrace = new java.util.concurrent.ConcurrentHashMap();

function markStateFeatureOnce(name) {
  if (markedFeaturesThisTrace.putIfAbsent(name, true) === null) {
    Ctrl.doMark(name);
  }
}
////////////////////////////////////////////////////////////////

// Loan-blocked sub-conditions: distinguishes whether a loan attempt is blocked because of the
// user, the book, or both.
ctx.bthread("markLoanBlockedSubConditions", "UserBook.CannotCreateLoan", function (userbook) {
  if (entityExists('Loan.All', loanId(userbook.userid, userbook.bookid))) return;

  var viaUser = hasLoanForUser(userbook.userid);
  var viaBook = hasLoanForBook(userbook.bookid);
  if (viaUser && viaBook) {
    markStateFeatureOnce("LOAN_BLOCKED_VIA_BOTH");
  } else if (viaUser) {
    markStateFeatureOnce("LOAN_BLOCKED_VIA_USER_ONLY");
  } else if (viaBook) {
    markStateFeatureOnce("LOAN_BLOCKED_VIA_BOOK_ONLY");
  }
});

// Rescans all currently-blocked pairs on every new loan, so a transition into "blocked by both"
// is caught even if the user-side and book-side conditions become true at different times.
ctx.bthread("markLoanBlockedViaBothRescan", "Loan.All", function (loan) {
  var blocked = ctx.runQuery('UserBook.CannotCreateLoan');
  for (var i = 0; i < blocked.length; i++) {
    var pair = blocked[i];
    if (entityExists('Loan.All', loanId(pair.userid, pair.bookid))) continue;
    if (hasLoanForUser(pair.userid) && hasLoanForBook(pair.bookid)) {
      markStateFeatureOnce("LOAN_BLOCKED_VIA_BOTH");
      break;
    }
  }
});

// A book with both an active loan and an active hold at the same time.
ctx.bthread("markBookLoanedWithActiveHoldViaLoan", "Loan.All", function (loan) {
  if (hasHoldForBook(loan.bookid)) markStateFeatureOnce("BOOK_LOANED_WITH_ACTIVE_HOLD");
});

ctx.bthread("markBookLoanedWithActiveHoldViaHold", "Hold.All", function (hold) {
  if (hasLoanForBook(hold.bookid)) markStateFeatureOnce("BOOK_LOANED_WITH_ACTIVE_HOLD");
});

// A book with two or more active holds at the same time.
ctx.bthread("markBookWithMultipleActiveHolds", "Hold.All", function (hold) {
  var holdsForThisBook = ctx.runQuery('Hold.All').filter(function (h) {
    return sameId(h.bookid, hold.bookid);
  });
  if (holdsForThisBook.length >= 2) markStateFeatureOnce("BOOK_WITH_MULTIPLE_ACTIVE_HOLDS");
});

// Same user and book connected by both an active loan and an active hold.
ctx.bthread("markLoanAndHoldSamePairViaLoan", "Loan.All", function (loan) {
  if (samePairHasHold(loan.userid, loan.bookid)) {
    markStateFeatureOnce("LOAN_AND_HOLD_SAME_PAIR");
  }
});

ctx.bthread("markLoanAndHoldSamePairViaHold", "Hold.All", function (hold) {
  if (entityExists('Loan.All', loanId(hold.userid, hold.bookid))) {
    markStateFeatureOnce("LOAN_AND_HOLD_SAME_PAIR");
  }
});

function samePairHasHold(userIdValue, bookIdValue) {
  var holds = ctx.runQuery('Hold.All');
  for (var i = 0; i < holds.length; i++) {
    if (sameId(holds[i].userid, userIdValue) && sameId(holds[i].bookid, bookIdValue)) return true;
  }
  return false;
}

// One user with an active loan on one book and an active hold on a different book.
ctx.bthread("markUserLoanPlusHoldDifferentBooksViaLoan", "Loan.All", function (loan) {
  if (hasUserLoanPlusHoldDifferentBooks(loan.userid)) markStateFeatureOnce("USER_LOAN_PLUS_HOLD_DIFFERENT_BOOKS");
});

ctx.bthread("markUserLoanPlusHoldDifferentBooksViaHold", "Hold.All", function (hold) {
  if (hasUserLoanPlusHoldDifferentBooks(hold.userid)) markStateFeatureOnce("USER_LOAN_PLUS_HOLD_DIFFERENT_BOOKS");
});

function hasUserLoanPlusHoldDifferentBooks(userIdValue) {
  if (!hasLoanForUser(userIdValue)) return false;
  var loans = ctx.runQuery('Loan.All');
  var loanBookId = null;
  for (var i = 0; i < loans.length; i++) {
    if (sameId(loans[i].userid, userIdValue)) { loanBookId = loans[i].bookid; break; }
  }
  if (loanBookId === null) return false;
  var holds = ctx.runQuery('Hold.All');
  for (var j = 0; j < holds.length; j++) {
    if (sameId(holds[j].userid, userIdValue) && !sameId(holds[j].bookid, loanBookId)) {
      return true;
    }
  }
  return false;
}

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
// malformed request or calls a route the service does not expose. Every read
// checks the response contents against the SUT ids recorded at creation.

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
