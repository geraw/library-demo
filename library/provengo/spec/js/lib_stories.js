//@provengo summon ctrl

const NUMBER_OF_USERS = 4;
const NUMBER_OF_BOOKS = 4;

const RANDOM = new java.util.Random();
// AtomicInteger, not a plain JS `var n = 1; n++`: BPjs runs b-thread steps concurrently on a
// thread pool, and a JS ++ on a shared global is not atomic, so two ctx.bthreads (e.g. two
// createHold instances) could be handed the same id.
const nextUserId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextBookId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextLoanId = new java.util.concurrent.atomic.AtomicInteger(1);
const nextHoldId = new java.util.concurrent.atomic.AtomicInteger(1);

function randomInt() {
  return RANDOM.nextInt(999999);
}

function generateUserId() {
  return nextUserId.getAndIncrement();
}

// Gera: random names/titles make the events differ from run to run (and between samples), though
// they never affect behavior. Does that hurt reproducing a failing run or computing coverage? A
// deterministic "User name " + id would do.
function generateUserName() {
  return "User name " + randomInt();
}

function generateBookId() {
  return nextBookId.getAndIncrement();
}

function generateBookTitle() {
  return "Book title " + randomInt();
}

function generateLoanId() {
  return nextLoanId.getAndIncrement();
}

function generateHoldId() {
  return nextHoldId.getAndIncrement();
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

// The verify*Exists b-threads below need no guard against a concurrent deletion of their entity:
// COBP ends a ctx.bthread at the very event that removes its entity from the query it was spawned
// for, so none of them can ever run against an entity that no longer exists.
ctx.bthread("verifyUserExistsAfterCreation", "User.All", function (user) {
  verifyUserExists(user.userid);
});

ctx.bthread("verifyCannotDeleteUser", "User.CannotDelete", function (user) {
  tryToDeleteUserAndExpectError(user.userid);
});

// Claude: ctx.bthread with no query - the function lands in the query slot. It happens to work,
// but shouldn't this be a plain bthread, like verifyBookDeletion/verifyHoldDeletion below?
ctx.bthread("verifyUserDeletion", function () {
  on(matchAnyUserDeleted(), function (e) {
    let id = extractEventData(e).id;

    verifyUserAbsentFromAllLists(id);
    tryToDeleteDeletedUserAndExpectError(id);
  });
});

ctx.bthread("verifyBookExistsAfterCreation", "Book.All", function (book) {
  verifyBookExists(book.bookid);
  verifyBookDetailExists(book.bookid);
});

// Gera: on() only waits for the next deletion between handler runs - while a handler is busy with
// its own syncs, a second deletion of the same kind is not waited for and never gets verified
// (here and in the other on(matchAny*Deleted(), ...) verifies). Spawn a b-thread per deletion?
bthread("verifyBookDeletion", function () {
  on(matchAnyBookDeleted(), function (e) {
    let id = extractEventData(e).id;

    verifyBookAbsentFromAllLists(id);
    verifyMissingEntityReadIsRejected("Book", id, "/books/" + sutBookIdRef(id));
    tryToDeleteDeletedBookAndExpectError(id);
  });
});

ctx.bthread("verifyLoanExists", "Loan.All", function (loan) {
  verifyLoanExists(loan.bookid, loan.userid);
});

// Unlike users/books/holds, a loan's identity is its userId/bookId pair, so the same loan can be
// re-created while these checks wait their turn. Wait for that too: once it happens the loan
// exists again, so the absence checks no longer apply (verifyLoanExists covers the new loan).
bthread("verifyLoanDeletion", function () {
  on(matchAnyLoanDeleted(), function (e) {
    let loan = extractEventData(e);
    let reloaned = matchLoanAdded(loan.userId, loan.bookId);

    waitFor(reloaned, function () {
      if (!reloaned.contains(verifyLoanAbsentFromAllLists(loan.bookId, loan.userId)))
        tryToDeleteDeletedLoanAndExpectError(loan.userId, loan.bookId);
    });
  });
});

ctx.bthread("verifyHoldExistsAfterCreation", "Hold.All", function (hold) {
  verifyHoldExists(hold.holdid);
});

bthread("verifyHoldDeletion", function () {
  on(matchAnyHoldDeleted(), function (e) {
    let id = extractEventData(e).id;

    verifyHoldAbsentFromAllLists(id);
    tryToDeleteDeletedHoldAndExpectError(id);
  });
});

  
// Claude: this is the same b-thread as verifyCannotCreateLoan below (same query, same call), so
// every busy pair gets the rejection test twice. Drop one?
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
ctx.bthread("createLoan", "UserBook.CanCreateLoan", function (userbook) {
  createLoan(userbook.userid, userbook.bookid, generateLoanId());
});

ctx.bthread("verifyCannotCreateLoan", "UserBook.CannotCreateLoan", function (userbook) {
    tryToCreateLoanAndExpectError(userbook.userid, userbook.bookid, generateLoanId());
});

ctx.bthread("createHold", "UserBook.CanCreateHold", function (userbook) {
    createHold(userbook.bookid, generateHoldId(), userbook.userid);
});

// Claude: here, above deleteUser, and above verifyCannotCreateBookWithBadParameters - do we need
// obituaries for removed code? git log keeps that history.
// verifyCannotCreateHold was removed: the SUT now assigns the hold's id itself and silently
// ignores any client-supplied "id" field, so there is no client-chosen id left that could
// collide with an existing one. See the RTV helpers (sutHoldIdRef etc.) in interfaces.library.js.
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
// existing one. See the RTV helpers (sutBookIdRef etc.) in interfaces.library.js.

// Claude: the *WithBadParameters b-threads (book, loan, hold) send the same invalid bodies that
// createBook/createLoan/createHold already fuzz in their own loops. They're also spawned once per
// book/pair/hold, though a rejected create doesn't depend on which entity exists. Needed at all?
ctx.bthread("verifyCannotCreateBookWithBadParameters", "Book.All", function (book) {
  tryToCreateBookWithBadParametersAndExpectError(book.bookid);
});

ctx.bthread("verifyCannotDeleteBook", "Book.CannotDelete", function (book) {
  tryToDeleteBookAndExpectError(book.bookid);
});

// Claude: User.CannotDelete/Book.CannotDelete already include "has a hold", so
// verifyCannotDeleteUser/verifyCannotDeleteBook send these same rejected deletes. Redundant?
ctx.bthread("verifyHoldOnlyBlocksUserAndBookDeletion", "Hold.All", function (hold) {
  tryToDeleteUserAndExpectError(hold.userid);
  tryToDeleteBookAndExpectError(hold.bookid);

  // The general deleteHold bthread is the single valid deletion path for this
  // hold. Doing an extra delete here creates a second valid delete on the same
  // resource, which can race and turn a valid 200 into an unexpected 404.
});

// Claude: only userId is passed, and the helper reuses it as the bookId value in its bodies.
ctx.bthread("verifyCannotCreateLoanWithBadParameters", "UserBook.All", function (userbook) {
  tryToCreateLoanWithBadParametersAndExpectError(userbook.userid);
});

ctx.bthread("verifyCannotCreateLoanWithNonexistentForeignKeys", "UserBook.All", function (userbook) {
  let missingUserId = generateMissingId(userbook.userid);
  let missingBookId = generateMissingId(userbook.bookid);


  // Gera: I think trying all three is too much, enough to try one of the three nondeterministically?
  // Claude: also, this runs once per user-book pair (N*M copies), but a nonexistent-foreign-key
  // check only needs some existing user and some existing book. Same for holds below.
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
// Claude: generateMissingId(generateUserId()) burns a real id from the counter just to add 1e9 to
// it. SUT ids are random 6-digit numbers, so a fixed out-of-range id would do.
bthread("tryToDeleteNonexistingUser", function () {
  tryToDeleteNonexistingUserAndExpectError(generateMissingId(generateUserId()));
});

bthread("tryToDeleteNonexistingBook", function () {
  tryToDeleteNonexistingBookAndExpectError(generateMissingId(generateBookId()));
});

bthread("tryToDeleteNonexistingLoan", function () {
  tryToDeleteNonexistingLoanAndExpectError(generateMissingId(generateUserId()), generateMissingId(generateBookId()));
});

bthread("tryToDeleteNonexistingHold", function () {
  tryToDeleteNonexistingHoldAndExpectError(generateMissingId(generateHoldId()));
});

//////////////////////////////////////////////////////////////////////////
// Coverage markers for ensemble ranking (state+parameter coverage).
//
// These bthreads don't drive any behavior - they just emit a lightweight
// "StateFeature" event whenever one of six hand-picked domain states becomes
// true, by reusing the DAL's own queries so the detection logic isn't
// duplicated here (feature list and rationale per Gera's 2026-10-15 review).
// meta-spec/ensemble-code.js's stateParamRankingFunction reads these events
// back out of sampled traces to score ensembles by how many distinct features
// (not raw occurrences) they exercise - see STATE_FEATURES there, which must
// stay in sync with the names marked here.
//
// markStateFeature uses Ctrl.doMark (per Gera's suggestion) instead of a plain
// bp.sync({request:...}) offer: a plain offer competes on equal footing with every other event
// any other bthread offers at that sync point, and loses most of the time at high-competition
// moments (e.g. every single loan/hold create) - a measured 45-78% miss rate across all six
// original features. Ctrl.doMark requests its event with eventPriority:1010 (controlLib.js),
// which wins selection instead of competing as an equal offer.
//
// This changes the marker event's shape from the old bp.Event("StateFeature", {feature: name})
// to Ctrl.markEvent's own: name "marker: " + name, data {lib:"Ctrl", verb:"marker", value: name,
// eventPriority: 1010} - ensemble-code.js's distinctStateFeaturesHit reads this shape (data.lib
// === "Ctrl" && data.verb === "marker", feature name in data.value), not the old one.
//////////////////////////////////////////////////////////////////////////

function markStateFeature(name) {
  Ctrl.doMark(name);
}

// Phase 4 (2026-11-06) reliability fix for the dual-trigger marker race: MULTI_USER_BOOK_RELATIONS
// and USER_WITH_TWO_BOOKS below are each spawned from two independent ctx.bthreads (one per
// Loan.All, one per Hold.All) that can both become eligible in the same synchronization round and
// both call Ctrl.doMark for the same feature name - the measured ~10-11% marker-miss source
// (RESEARCH_SUMMARY.md §11). markStateFeatureOnce replaces markStateFeature at exactly those four
// call sites (and is used by every new marker added below) to close that race: only the first of
// several concurrently-racing callers for a given name ever proceeds to call Ctrl.doMark, so the
// two bthreads stop competing for the same sync slot instead of leaving one to possibly lose it.
//
// ConcurrentHashMap.putIfAbsent, not a plain JS Set's has()+add(): BPjs runs b-thread callbacks
// concurrently on a thread pool (see nextUserId's AtomicInteger comment at the top of this file
// for the same reasoning), so a plain Set's two non-atomic steps would still race; putIfAbsent is
// a single atomic check-and-set.
//
// Scoping this at module level (rather than per-trace-scoped ctx state) was verified, not
// assumed: replaying both saved 10-trace sample pools shows every trace's user/book ids restart at
// 1 (max id seen across all 20 traces is 6, from the few extra ids
// tryToDeleteNonexisting{User,Book}'s generateMissingId() calls burn within a single trace - never
// the dozens+ a run of several traces sharing one counter would produce), the same evidence
// nextUserId/nextBookId/etc. above already rely on - so this map is effectively fresh per
// generated trace, same as the rest of this file's module state.
const markedFeaturesThisTrace = new java.util.concurrent.ConcurrentHashMap();

function markStateFeatureOnce(name) {
  if (markedFeaturesThisTrace.putIfAbsent(name, true) === null) {
    Ctrl.doMark(name);
  }
}

ctx.bthread("markBookDeleteEligible", "Book.CanDelete", function (book) {
  markStateFeature("BOOK_DELETE_ELIGIBLE");
});

ctx.bthread("markUserDeleteEligible", "User.CanDelete", function (user) {
  markStateFeature("USER_DELETE_ELIGIBLE");
});

ctx.bthread("markLoanCreatable", "UserBook.CanCreateLoan", function (userbook) {
  markStateFeature("LOAN_CREATABLE");
});

// HOLD_CREATABLE (UserBook.CanCreateHold) deliberately dropped from the feature list: that query
// is `e.type === 'user-book'` with no other condition, so it's true for every user-book pair the
// instant it exists - it measures "a user and a book exist", not any interesting/restrictive
// state, so it can't discriminate between scenarios (confirmed: independently true in 20/20
// traces in earlier measurements). Not replaced with a different hold-related condition - no
// other well-defined "hold not yet possible" business concept exists in the model to measure.

// Hold.WithoutLoan was previously dead code (defined, never consumed) - this is its first use.
ctx.bthread("markHoldWithoutLoan", "Hold.WithoutLoan", function (hold) {
  markStateFeature("HOLD_WITHOUT_LOAN");
});

// At least two users each tied to a different book through a loan or a hold - the one feature
// here with no existing single-entity DAL query, so it's computed directly over Loan.All +
// Hold.All rather than added as a new registerQuery (nothing else needs this combined view).
function hasMultiUserBookRelations() {
  var relations = ctx.runQuery('Loan.All').concat(ctx.runQuery('Hold.All'));
  for (var i = 0; i < relations.length; i++) {
    for (var j = i + 1; j < relations.length; j++) {
      if (!sameId(relations[i].userid, relations[j].userid) && !sameId(relations[i].bookid, relations[j].bookid)) {
        return true;
      }
    }
  }
  return false;
}

ctx.bthread("markMultiUserBookRelationsViaLoan", "Loan.All", function (loan) {
  if (hasMultiUserBookRelations()) markStateFeatureOnce("MULTI_USER_BOOK_RELATIONS");
});

ctx.bthread("markMultiUserBookRelationsViaHold", "Hold.All", function (hold) {
  if (hasMultiUserBookRelations()) markStateFeatureOnce("MULTI_USER_BOOK_RELATIONS");
});

// Mirror of hasMultiUserBookRelations: one user tied to two different books through a loan or a
// hold, instead of two different users each tied to a different book.
function hasUserWithTwoBooks() {
  var relations = ctx.runQuery('Loan.All').concat(ctx.runQuery('Hold.All'));
  for (var i = 0; i < relations.length; i++) {
    for (var j = i + 1; j < relations.length; j++) {
      if (sameId(relations[i].userid, relations[j].userid) && !sameId(relations[i].bookid, relations[j].bookid)) {
        return true;
      }
    }
  }
  return false;
}

ctx.bthread("markUserWithTwoBooksViaLoan", "Loan.All", function (loan) {
  if (hasUserWithTwoBooks()) markStateFeatureOnce("USER_WITH_TWO_BOOKS");
});

ctx.bthread("markUserWithTwoBooksViaHold", "Hold.All", function (hold) {
  if (hasUserWithTwoBooks()) markStateFeatureOnce("USER_WITH_TWO_BOOKS");
});

//////////////////////////////////////////////////////////////////////////
// Phase 4 (2026-11-06): experimental new State Feature markers.
//
// The six markers below (A-F, naming/predicates per the Phase 1-3 research reports) are emitted
// the same way as the six features above, but are NOT added to meta-spec/ensemble-code.js's
// STATE_FEATURES/rankingFunction yet - this phase instruments and validates detection only, it
// does not change what the production ranking function scores. A marker name absent from
// STATE_FEATURES is harmlessly ignored by distinctStateFeaturesHit (it only matches names in that
// array), so adding these here cannot affect any existing measurement.
//////////////////////////////////////////////////////////////////////////

// --- A/B/C: loan-blocked sub-conditions -------------------------------------------------------
// UserBook.CannotCreateLoan (dal.js) is `hasLoanForUser(e.userid) || hasLoanForBook(e.bookid)` -
// true both when a DIFFERENT pair's loan blocks this one (the interesting cross-pair case) and
// when this exact pair already holds the loan itself (excluded below, per the Phase 2/3 finding
// that collapsing the two would hide the trivial case inside the interesting one).
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
  // Neither viaUser nor viaBook shouldn't be reachable given this query's own condition, but no
  // marker fires in that case rather than assuming it can't happen.
});

// Fix (2026-11-06, live-run finding): the bthread above fires only once per pair, at the moment
// UserBook.CannotCreateLoan's query first matches that pair - i.e. the instant whichever
// condition (viaUser/viaBook) flips true FIRST. If the pair enters as USER_ONLY or BOOK_ONLY and
// only later does the OTHER condition also become true (via an unrelated loan elsewhere), that
// transition to BOTH is invisible to the one-shot trigger above: confirmed by direct trace
// inspection in the Phase 4 live run (3/3 ground-truth LOAN_BLOCKED_VIA_BOTH occurrences were
// exactly this case - e.g. user5/book2 entered CannotCreateLoan via viaUser alone when user5 first
// borrowed book1; only when book2 was separately loaned to a different user did viaBook also
// become true, with no re-evaluation of the already-consumed trigger), so the marker's live recall
// was 0/3. Loan.All is the only event type that can ever flip hasLoanForUser/hasLoanForBook (holds
// don't participate in this condition at all - see UserBook.CannotCreateLoan's definition in
// dal.js), so a single rescan triggered on every new loan - re-checking ALL currently-blocked
// pairs, not just the one that just got loaned - is enough to catch the transition regardless of
// which side completes it second, without needing BOOK_LOANED_WITH_ACTIVE_HOLD's two-trigger-type
// structure (that feature needs both Loan.All and Hold.All because either relationship type can
// establish it; this one only ever changes via loans).
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

// --- D: a book with both an active loan and an active hold simultaneously --------------------
// Needs two trigger paths (Loan.All, Hold.All) since either relationship can be created first;
// markStateFeatureOnce's guard (above) is what makes this safe instead of racing the way the
// existing MULTI_USER_BOOK_RELATIONS/USER_WITH_TWO_BOOKS dual-trigger markers used to.
ctx.bthread("markBookLoanedWithActiveHoldViaLoan", "Loan.All", function (loan) {
  if (hasHoldForBook(loan.bookid)) markStateFeatureOnce("BOOK_LOANED_WITH_ACTIVE_HOLD");
});

ctx.bthread("markBookLoanedWithActiveHoldViaHold", "Hold.All", function (hold) {
  if (hasLoanForBook(hold.bookid)) markStateFeatureOnce("BOOK_LOANED_WITH_ACTIVE_HOLD");
});

// --- E: a book with >=2 active holds -----------------------------------------------------------
// Confirmed generator-reachable only via distinct user-book pairs sharing a book: createHold's
// ctx.bthread (above) spawns once per UserBook.CanCreateHold-matching pair and never refires for
// that same pair, so "the same pair held twice" is not exercised by the current generator even
// though UserBook.CanCreateHold itself has no guard against it (Phase 2/3 finding) - not claimed
// or instrumented here. Single trigger type (Hold.All only), so no dual-trigger race is possible:
// each hold's bthread instance evaluates once, at its own creation moment, and those moments are
// naturally staggered (holds are created one at a time, not within the same event).
ctx.bthread("markBookWithMultipleActiveHolds", "Hold.All", function (hold) {
  var holdsForThisBook = ctx.runQuery('Hold.All').filter(function (h) {
    return sameId(h.bookid, hold.bookid);
  });
  if (holdsForThisBook.length >= 2) markStateFeatureOnce("BOOK_WITH_MULTIPLE_ACTIVE_HOLDS");
});

// --- F: a book or user undeletable solely because of an active hold (no active loan) ----------
// Merged book+user into one feature per the Phase 3 finding that the two variants are ~95%
// redundant in practice (a hold ties exactly one user to one book) and don't justify separate
// features.
//
// Two entry paths, per the Phase 2 finding that a simple query-trigger bthread alone only catches
// the first of these:
//
// Path 1 (this bthread): a hold is newly created on a book/user that has no active loan - a NEW
// entity (the hold) enters Hold.All, so a ctx.bthread query trigger works here.
ctx.bthread("markDeleteBlockedByHoldOnlyViaHoldCreation", "Hold.All", function (hold) {
  if (!hasLoanForBook(hold.bookid) || !hasLoanForUser(hold.userid)) {
    markStateFeatureOnce("DELETE_BLOCKED_BY_HOLD_ONLY");
  }
});

// Path 2: an existing loan is deleted while a hold on that same book or user remains - no NEW
// entity enters any ctx query here (the hold already existed before the deletion), so a
// ctx.bthread query trigger cannot catch this path at all; needs a plain bthread keyed off the
// deletion event itself, mirroring verifyLoanDeletion's on(matchAnyLoanDeleted(), ...) pattern
// above. Inherits that same bthread's documented limitation (Gera's comment near
// verifyBookDeletion above): on() only re-arms after its own callback finishes, so a second loan
// deletion arriving while this callback is still running would be missed - accepted here for the
// same reason it was accepted there, not a new issue introduced by this marker.
bthread("markDeleteBlockedByHoldOnlyViaLoanDeletion", function () {
  on(matchAnyLoanDeleted(), function (e) {
    var loan = extractEventData(e);
    if (hasHoldForBook(loan.bookId) || hasHoldForUser(loan.userId)) {
      markStateFeatureOnce("DELETE_BLOCKED_BY_HOLD_ONLY");
    }
  });
});

// =========================================================================
// Step 1: The Fuzzing Interface Layer Contract
// =========================================================================
// Whenever a story requests an action (create, delete, or retrieve an object),
// the interface layer executes a pre-flight fuzzing and verification sequence
// IF the SUT actually defines rejection semantics for that action. Some reads
// (see point 4) have no invalid variant to fuzz and skip straight to the request.
// Gera: there is no point 4, and the "Point 3's synchronization rule" mentioned in point 3 itself
// doesn't exist either - stale references?
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
