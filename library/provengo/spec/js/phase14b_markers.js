//////////////////////////////////////////////////////////////////////////
// Phase 14B (2026-11-07): additive experimental StateFeature markers.
//
// This file is loaded alongside lib_stories.js (every .js file under spec/js/
// shares one global Rhino scope - see dal.js's and ensemble-code.js's own
// comments on this). It adds NEW marker bthreads only; it does not modify,
// remove, or re-trigger any existing bthread in lib_stories.js, dal.js, or
// interfaces.library.js, and does not send any new SUT request or change any
// existing business guard. Markers reuse markStateFeatureOnce (defined in
// lib_stories.js) and dal.js's existing hasLoanForBook/hasLoanForUser/
// hasHoldForBook/hasHoldForUser/entityExists/sameId/loanId helpers exactly as
// the Phase 4 markers in lib_stories.js already do - no new query logic is
// duplicated here beyond what those helpers already expose.
//
// Predicates implemented here are the Phase 14 Stage A suspicious-state
// catalog, reconciled and corrected in Phase 14B (see
// meta-spec/tests/phase14b_features/canonical_feature_specs.json for the
// frozen, machine-readable version of every predicate, alias, and the
// equivalence/implication findings below). Two features from Stage A's
// original 15-item list are NOT instrumented here because Phase 14B's
// dependency analysis proved them logically EQUIVALENT to features that
// already exist (see canonical_feature_specs.json's "dropped_as_redundant"
// section) - BOOK_DELETE_BLOCKED_BOTH (== the already-instrumented
// BOOK_LOANED_WITH_ACTIVE_HOLD) and USER_DELETE_BLOCKED_BOTH (== the OR of
// two other features instrumented here, LOAN_AND_HOLD_SAME_PAIR and
// USER_LOAN_PLUS_HOLD_DIFFERENT_BOOKS). Adding a marker for a feature already
// provably equivalent to an existing or other-new feature would not change
// any Set-based coverage score, so it was not implemented, per Section 11's
// instruction to report (not silently implement) a proven equivalence.
//////////////////////////////////////////////////////////////////////////

// --- Split of the original USER_WITH_TWO_BOOKS (lib_stories.js) --------------------------------
// Phase 14B dependency check (see canonical_feature_specs.json "user_two_books_split"): these two
// are OR-equivalent to the original USER_WITH_TWO_BOOKS (so no coverage information is lost
// relative to it), because the per-user loan cap (sut.py add_loan) means any same-user,
// different-book RELATION PAIR is either a hold/hold pair or a loan/hold pair - never a
// loan/loan pair. They are NOT mutually exclusive in general, though: a user with one loan and
// TWO holds on two further distinct books satisfies both predicates simultaneously (the
// hold/hold pair and the loan/hold pair both exist at once). That counterexample is reachable
// (loan on book A, hold on book B, hold on book C, same user) and is documented, not hidden.

ctx.bthread("markUserTwoBooksViaHoldsOnlyViaHold", "Hold.All", function (hold) {
  if (hasUserTwoBooksViaHoldsOnly()) markStateFeatureOnce("USER_TWO_BOOKS_VIA_HOLDS_ONLY");
});

function hasUserTwoBooksViaHoldsOnly() {
  var holds = ctx.runQuery('Hold.All');
  for (var i = 0; i < holds.length; i++) {
    for (var j = i + 1; j < holds.length; j++) {
      if (sameId(holds[i].userid, holds[j].userid) && !sameId(holds[i].bookid, holds[j].bookid)) {
        return true;
      }
    }
  }
  return false;
}

ctx.bthread("markUserLoanPlusHoldDifferentBooksViaLoan", "Loan.All", function (loan) {
  if (hasUserLoanPlusHoldDifferentBooks(loan.userid)) markStateFeatureOnce("USER_LOAN_PLUS_HOLD_DIFFERENT_BOOKS");
});

ctx.bthread("markUserLoanPlusHoldDifferentBooksViaHold", "Hold.All", function (hold) {
  if (hasUserLoanPlusHoldDifferentBooks(hold.userid)) markStateFeatureOnce("USER_LOAN_PLUS_HOLD_DIFFERENT_BOOKS");
});

// A single shared user id is enough: the per-user loan cap means there is at most one loan to
// check against this user's holds.
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

// --- LOAN_AND_HOLD_SAME_PAIR: same user+book connected by BOTH an active loan and an active hold.
// Needs two trigger paths (either relationship can be created first), same race-safety reasoning
// as lib_stories.js's existing BOOK_LOANED_WITH_ACTIVE_HOLD dual-trigger marker.
ctx.bthread("markLoanAndHoldSamePairViaLoan", "Loan.All", function (loan) {
  if (hasHoldForUser(loan.userid) && samePairHasHold(loan.userid, loan.bookid)) {
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

// --- Entity-specific deletion states (book side) ------------------------------------------------
// Canonical names per canonical_feature_specs.json: BOOK_DELETE_BLOCKED_BY_HOLD_ONLY /
// BOOK_DELETE_BLOCKED_BY_LOAN_ONLY (Phase 14B's own task text used BOOK_DELETE_BLOCKED_HOLD_ONLY /
// _LOAN_ONLY without "BY" - documented there as an alias of the same predicate, not a different
// one). BOOK_DELETE_BLOCKED_BOTH is proven equivalent to BOOK_LOANED_WITH_ACTIVE_HOLD (already
// instrumented in lib_stories.js) and is deliberately NOT re-instrumented here.
//
// NOTE on an implementation mistake caught and fixed before freezing (keeping the dead end
// visible for the record, per the project's negative-result-reporting norm): an earlier draft of
// this file triggered these four markers on "Book.All"/"User.All" (entity CREATION). That is
// wrong - a ctx.bthread query trigger fires once, the instant a NEW entity enters the query's
// result set, and a freshly created book/user has no loan or hold yet, so hasHoldForBook/
// hasLoanForBook are always both false at that exact moment. That would have made these four
// markers almost entirely dead code, repeating exactly the one-shot-trigger bug Phase 4 already
// found and fixed for LOAN_BLOCKED_VIA_BOTH (see lib_stories.js's comment above
// markLoanBlockedViaBothRescan). Fixed by triggering on the RELEVANT relationship events instead
// (Hold.All/Loan.All creation, plus the matching deletion event for the "was BOTH, now ONLY"
// transition), mirroring lib_stories.js's own markDeleteBlockedByHoldOnlyViaHoldCreation /
// ViaLoanDeletion dual-path structure exactly.
//
// Hold deletion carries userId/bookId: confirmed from interfaces.library.js's deleteHold(id,
// expectedCode, userId, bookId) - lib_stories.js's "deleteHold" ctx.bthread calls it as
// deleteHold(hold.holdid, hold.userid, hold.bookid), which deleteHold's own argument-shuffle (for
// its single caller) turns into parameters {id, userId, bookId} on the request - so
// extractEventData(e) on a hold-deletion event returns a real {userId, bookId}, not just {id}.
ctx.bthread("markBookDeleteBlockedByHoldOnlyViaHoldCreation", "Hold.All", function (hold) {
  if (hasHoldForBook(hold.bookid) && !hasLoanForBook(hold.bookid)) {
    markStateFeatureOnce("BOOK_DELETE_BLOCKED_BY_HOLD_ONLY");
  }
});

bthread("markBookDeleteBlockedByHoldOnlyViaLoanDeletion", function () {
  on(matchAnyLoanDeleted(), function (e) {
    var loan = extractEventData(e);
    if (hasHoldForBook(loan.bookId) && !hasLoanForBook(loan.bookId)) {
      markStateFeatureOnce("BOOK_DELETE_BLOCKED_BY_HOLD_ONLY");
    }
  });
});

ctx.bthread("markBookDeleteBlockedByLoanOnlyViaLoanCreation", "Loan.All", function (loan) {
  if (hasLoanForBook(loan.bookid) && !hasHoldForBook(loan.bookid)) {
    markStateFeatureOnce("BOOK_DELETE_BLOCKED_BY_LOAN_ONLY");
  }
});

bthread("markBookDeleteBlockedByLoanOnlyViaHoldDeletion", function () {
  on(matchAnyHoldDeleted(), function (e) {
    var hold = extractEventData(e);
    if (hold.bookId !== undefined && hold.bookId !== null &&
        hasLoanForBook(hold.bookId) && !hasHoldForBook(hold.bookId)) {
      markStateFeatureOnce("BOOK_DELETE_BLOCKED_BY_LOAN_ONLY");
    }
  });
});

// --- Entity-specific deletion states (user side) -------------------------------------------------
// USER_DELETE_BLOCKED_BOTH is proven equivalent to (LOAN_AND_HOLD_SAME_PAIR OR
// USER_LOAN_PLUS_HOLD_DIFFERENT_BOOKS) - deliberately NOT re-instrumented here either.
ctx.bthread("markUserDeleteBlockedByHoldOnlyViaHoldCreation", "Hold.All", function (hold) {
  if (hasHoldForUser(hold.userid) && !hasLoanForUser(hold.userid)) {
    markStateFeatureOnce("USER_DELETE_BLOCKED_BY_HOLD_ONLY");
  }
});

bthread("markUserDeleteBlockedByHoldOnlyViaLoanDeletion", function () {
  on(matchAnyLoanDeleted(), function (e) {
    var loan = extractEventData(e);
    if (hasHoldForUser(loan.userId) && !hasLoanForUser(loan.userId)) {
      markStateFeatureOnce("USER_DELETE_BLOCKED_BY_HOLD_ONLY");
    }
  });
});

ctx.bthread("markUserDeleteBlockedByLoanOnlyViaLoanCreation", "Loan.All", function (loan) {
  if (hasLoanForUser(loan.userid) && !hasHoldForUser(loan.userid)) {
    markStateFeatureOnce("USER_DELETE_BLOCKED_BY_LOAN_ONLY");
  }
});

bthread("markUserDeleteBlockedByLoanOnlyViaHoldDeletion", function () {
  on(matchAnyHoldDeleted(), function (e) {
    var hold = extractEventData(e);
    if (hold.userId !== undefined && hold.userId !== null &&
        hasLoanForUser(hold.userId) && !hasHoldForUser(hold.userId)) {
      markStateFeatureOnce("USER_DELETE_BLOCKED_BY_LOAN_ONLY");
    }
  });
});

// --- ALL_BOOKS_ON_LOAN: global saturation - every book currently in the model's fixed population
// (NUMBER_OF_BOOKS, declared in lib_stories.js, reused here as a shared global per the same
// convention ensemble-code.js's own comment documents - a second top-level `const` of the same
// name in this shared Rhino scope would be a redeclaration error) has an active loan.
//
// Requires the full population to still exist (Book.All.length === NUMBER_OF_BOOKS), not just
// "every book that currently exists happens to be loaned" - without that count check, deleting
// books down to a small remaining set would trivially satisfy "every existing book is loaned"
// without ever reflecting genuine full-catalog saturation. This resolves the ambiguity the Phase
// 14B task flagged in its Section 7.
ctx.bthread("markAllBooksOnLoan", "Loan.All", function (loan) {
  var allBooks = ctx.runQuery('Book.All');
  if (allBooks.length !== NUMBER_OF_BOOKS) return;
  for (var i = 0; i < allBooks.length; i++) {
    if (!hasLoanForBook(allBooks[i].bookid)) return;
  }
  markStateFeatureOnce("ALL_BOOKS_ON_LOAN");
});
