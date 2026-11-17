//@provengo summon rest
//@provengo summon rtv
//////////////////////////////////////////////////////////////////////////
// Interface layer for the library REST service.
//
// This file is the only layer that should know the concrete transport shape:
// REST URLs, HTTP verbs, request/response-code conventions, and JSON payloads.
// It exposes three kinds of API to the rest of the model:
//
// 1. Action functions such as createBook/deleteLoan that send REST requests.
// 2. EventSets such as AnyBookAdded and AnyRelationChanged that classify events.
// 3. extractEventData(), which converts a concrete event into semantic fields.
//
// Stories use action functions and EventSets to describe behavior. The DAL uses
// EventSets plus extractEventData() to update the Context model without parsing
// URLs, bodies, or transport parameters itself.
//
// Every function below sends exactly one REST request: one call, one event.
// Negative checks (tryTo*AndExpectError) likewise send one request, with the
// rejecting response code as the expected one. They cover business-rule
// rejections only (a delete blocked by a loan or hold, a loan the rules forbid,
// an entity that does not exist or no longer exists); the model sends no
// malformed request and never calls a route the service does not expose.
//
// Every event, rejection checks included, carries the logical ids it is about in
// `parameters` (id, or userId/bookId), so stories, matchers and external checkers
// bind identity without parsing descriptions or URLs. Provengo also sends
// `parameters` as the query string; the service ignores the keys it does not use.
//
// Argument order: an entity's own id first, then userId, then bookId. A loan has
// no id of its own (the service and the model both address it by its reader/book
// pair), so loan functions take (userId, bookId).
//////////////////////////////////////////////////////////////////////////

var host = (typeof host !== 'undefined') ? host : 'localhost';
var port = (typeof port !== 'undefined') ? port : 23242;
var protocol = (typeof protocol !== 'undefined') ? protocol : 'http';
var path = '';

const svc = new RESTSession(protocol + "://" + host + ":" + port + path, "provengo-client", { headers: { "Content-Type": "application/json", "api_key": "special-key" } });

function optionalInteger(value) {
  return value === undefined || value === null ? null : asInteger(value);
}

// asInteger, asString, the *Description builders, getExpectedResponseCodes, hasExpectedCode,
// getRequestPath, getJsonBody, readSutList, and verifyMissingEntityReadIsRejected live in
// lib/utils.js.

// Boundary adapter from concrete REST events to semantic event data. Consumers depend on
// fields like id, userId, bookId and title without knowing where they came from:
// ids come from `parameters` (the logical ids; the body and URL carry SUT ids or late-bound
// "@{...}" references), the client-supplied name and title from the body.
function extractEventData(e) {
  var data = e && e.data ? e.data : e;
  var parameters = data && data.parameters ? data.parameters : {};
  var body = getJsonBody(e) || {};
  return {
    id: parameters.id,
    title: body.title,
    name: body.name,
    userId: parameters.userId,
    bookId: parameters.bookId
  };
}

//////////////////////////////////////////////////////////////////////////
// SUT-id mapping (RTV).
//
// The SUT assigns entity ids instead of accepting a client choice. Stories,
// EventSets, and the DAL keep addressing each entity by the small id the
// story picked when it asked for creation, so traces and context stay
// readable; only the REST calls in this file need the id the SUT
// actually assigned (the "SUT id"). The mapping is written once, right after a successful
// create response into Provengo's runtime-variable store under a per-entity
// key ("USER1", "BOOK1", "HOLD1", ...). Every wire-level use is a late-bound
// `@{...}` expression; parameters retain the logical id for the DAL. Loans need
// no entry: the SUT addresses a loan by its user/book pair.
//////////////////////////////////////////////////////////////////////////

function rtvKey(entityType, id) {
  return entityType + asInteger(id);
}

// Returns a late-bound "@{...}" expression, substituted with the SUT id by Provengo's
// runtime only once the sampled scenario actually executes the request that carries it.
//
// Pass missing = true for an id that was deliberately never created (missingId() in
// lib_stories.js, 1000000001 and up): its RTV key was never set, so resolving `@{...}` for it
// would throw a ReferenceError at actuation time. The plain id is sent instead; it cannot
// collide with any SUT-assigned id, so no lookup is needed.
function sutIdRef(entityType, id, missing) {
  return missing === true ? asInteger(id) : "@{" + rtvKey(entityType, id) + "}";
}

function sutUserIdRef(id, missing) { return sutIdRef("USER", id, missing); }
function sutBookIdRef(id, missing) { return sutIdRef("BOOK", id, missing); }
function sutHoldIdRef(id, missing) { return sutIdRef("HOLD", id, missing); }

// A JSON body with reader and book ids. A late-bound "@{...}" reference has to sit inside a JSON
// string: the body must be valid JSON before Provengo substitutes the SUT id, because the sampler
// (which never actuates) silently ends a scenario at an event whose body it cannot parse. The
// service accepts numeric-string ids, so after substitution the body carries "userId":"288673".
function pairBody(userRef, bookRef) {
  return JSON.stringify({ userId: userRef, bookId: bookRef });
}

//////////////////////////////////////////////////////////////////////////
// REST callbacks.
//
// A callback runs at actuation time, in Provengo's run-code scope, with the
// HTTP response (`response.code`, `response.body`). It is serialized with the
// event, so it must be self-contained: JavaScript built-ins, the `pvg` object
// (`pvg.rtv.set` / `pvg.rtv.get` for the run-time variables), and the strings
// closed over at construction time. Throwing fails the actuation, and with it
// the scenario, the same way an unexpected response code does.
//////////////////////////////////////////////////////////////////////////

// Stores the SUT id from a create response under this entity's RTV key.
function rememberCreatedId(entityType, id) {
  var key = rtvKey(entityType, id);
  return function (response) {
    var body = JSON.parse(response.body);
    if (body.id === undefined || body.id === null) throw new Error("Create response did not contain id");
    pvg.rtv.set(key, body.id);
    return true;
  };
}

// Content checks for list and detail reads: the response is compared with the SUT id that
// rememberCreatedId recorded for the entity the read is about. A deleted entity's key still
// resolves (the SUT never reuses an id, and the model never reuses a logical id), which is what
// the absence checks rely on.

// The list contains an element whose `id` is this entity's SUT id.
function expectListed(entityType, id) {
  var key = rtvKey(entityType, id);
  return function (response) {
    var sut = String(pvg.rtv.get(key));
    var list = JSON.parse(response.body);
    for (var i = 0; i < list.length; i++) if (String(list[i].id) === sut) return true;
    throw new Error(key + " (SUT id " + sut + ") is missing from the list: " + response.body);
  };
}

// No element of the list has this entity's SUT id in `field` ("id", "userId" or "bookId").
function expectNotListed(entityType, id, field) {
  var key = rtvKey(entityType, id);
  return function (response) {
    var sut = String(pvg.rtv.get(key));
    var list = JSON.parse(response.body);
    for (var i = 0; i < list.length; i++) {
      if (String(list[i][field]) === sut) throw new Error(key + " (SUT id " + sut + ") is still in the list: " + response.body);
    }
    return true;
  };
}

// The list is exactly the one loan of this reader/book pair.
function expectLoanListed(userId, bookId) {
  var userKey = rtvKey("USER", userId), bookKey = rtvKey("BOOK", bookId);
  return function (response) {
    var user = String(pvg.rtv.get(userKey)), book = String(pvg.rtv.get(bookKey));
    var list = JSON.parse(response.body);
    if (list.length !== 1 || String(list[0].userId) !== user || String(list[0].bookId) !== book) {
      throw new Error("Expected exactly the loan of " + userKey + "/" + bookKey + " (SUT ids " + user + "/" + book + "), got: " + response.body);
    }
    return true;
  };
}

// The list is empty. Used for reads filtered by the service (GET /loans?userId=...&bookId=...):
// anything the filter lets through is wrong, not only the entity the read is about - a filter
// that ignores one of its parameters is exactly the kind of fault this catches.
function expectEmptyList(what) {
  return function (response) {
    var list = JSON.parse(response.body);
    if (list.length !== 0) throw new Error("Expected no " + what + ", got: " + response.body);
    return true;
  };
}

// The detail response is this book.
function expectBookDetail(id) {
  var key = rtvKey("BOOK", id);
  return function (response) {
    var sut = String(pvg.rtv.get(key));
    var body = JSON.parse(response.body);
    if (String(body.id) !== sut) throw new Error("Expected " + key + " (SUT id " + sut + "), got: " + response.body);
    return true;
  };
}

//////////////////////////////////////////////////////////////////////////
// Broad event classifiers.
//
// These EventSets describe meaningful domain events in interface terms:
// "a book was successfully added", "a loan was successfully deleted", etc.
// Their predicates may inspect REST details, but callers should treat the
// EventSet names as the public contract.
//////////////////////////////////////////////////////////////////////////

var AnyBookAdded = bp.EventSet("Any Books Added", function (e) {
  // The request body carries no id (see createBook/the RTV helpers above) - title is the only
  // client-supplied field, so it is what marks this as a real book-create request.
  var body = getJsonBody(e);
  return e.name === "POST" && getRequestPath(e) === "/books" && hasExpectedCode(e, 201) && body && body.title !== undefined;
});

var AnyUserAdded = bp.EventSet("Any Users Added", function (e) {
  var body = getJsonBody(e);
  return e.name === "POST" && getRequestPath(e) === "/users" && hasExpectedCode(e, 201) && body && body.name !== undefined && e.data.parameters && e.data.parameters.id !== undefined;
});

var AnyLoanAdded = bp.EventSet("Any Loans Added", function (e) {
  var body = getJsonBody(e);
  return e.name === "POST" && getRequestPath(e) === "/loans" && hasExpectedCode(e, 201) && body && body.userId !== undefined && body.bookId !== undefined;
});

var AnyHoldAdded = bp.EventSet("Any Holds Added", function (e) {
  var body = getJsonBody(e);
  return e.name === "POST" && getRequestPath(e) === "/holds" && hasExpectedCode(e, 201) && body && e.data.parameters && e.data.parameters.id !== undefined;
});

var AnyBookDeleted = bp.EventSet("Any Books Deleted", function (e) {
  return e.name === "DELETE" && getRequestPath(e).startsWith("/books/") && hasExpectedCode(e, 200);
});

var AnyUserDeleted = bp.EventSet("Any Users Deleted", function (e) {
  return e.name === "DELETE" && getRequestPath(e).startsWith("/users/") && hasExpectedCode(e, 200);
});

var AnyLoanDeleted = bp.EventSet("Any Loans Deleted", function (e) {
  return e.name === "DELETE" && getRequestPath(e).startsWith("/loans/") && hasExpectedCode(e, 200);
});

var AnyHoldDeleted = bp.EventSet("Any Holds Deleted", function (e) {
  return e.name === "DELETE" && getRequestPath(e).startsWith("/holds/") && hasExpectedCode(e, 200);
});

// Trivial pass-throughs, restored from master: lib_stories.js's
// verifyActiveLoanAfterRelationshipRemoval bthread calls these by name.
function matchAnyBookDeleted() { return AnyBookDeleted; }
function matchAnyUserDeleted() { return AnyUserDeleted; }
function matchAnyLoanDeleted() { return AnyLoanDeleted; }
function matchAnyHoldDeleted() { return AnyHoldDeleted; }

// Any successful change to the loans: these are what decide whether a loan is allowed.
var AnyLoanChanged = bp.EventSet("Any Loan Changed", function (e) {
  return AnyLoanAdded.contains(e) || AnyLoanDeleted.contains(e);
});

// Any successful change to the loans or holds: these are what decide whether a reader or a
// book may be deleted.
var AnyRelationChanged = bp.EventSet("Any Relation Changed", function (e) {
  return AnyLoanChanged.contains(e) || AnyHoldAdded.contains(e) || AnyHoldDeleted.contains(e);
});

// A successful creation of the loan for this userId/bookId pair (logical ids, as createLoan
// carries them in its parameters).
function matchLoanAdded(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return bp.EventSet("Loan Added " + userId + "/" + bookId, function (e) {
    if (!AnyLoanAdded.contains(e)) return false;
    var loanData = extractEventData(e);
    return asInteger(loanData.userId) === userId && asInteger(loanData.bookId) === bookId;
  });
}

//////////////////////////////////////////////////////////////////////////
// Interface action functions.
//
// These functions are the only place stories should actuate the SUT. They
// normalize argument types, build URLs/bodies, and attach semantic parameters
// that extractEventData() can later expose to other layers.
//
// Every 200 read (verify*Exists / verify*AbsentFrom* / verifyBookDetailExists)
// checks the response contents with a REST callback (see the content checks
// above), not just the status code; the one 404 read
// (verifyMissingEntityReadIsRejected) is checked by its status code.
//////////////////////////////////////////////////////////////////////////

//////////////////////////////////////////////////////////////////////////
// Books
//////////////////////////////////////////////////////////////////////////

// The SUT assigns the book's id itself (title is the only client-supplied field). The id
// parameter below is this story's own bookkeeping handle: it never goes on the wire, only into
// `parameters` for the DAL/matchers, and into the BOOK<n> RTV once the SUT id comes back.
function createBook(id, title) {
  id = asInteger(id);
  return svc.post("/books", {
    body: JSON.stringify({ title: asString(title) }),
    expectedResponseCodes: [201],
    parameters: { description: createDescription("Book", id), id: id },
    callback: rememberCreatedId("BOOK", id)
  });
}

// sutBookIdRef() is an inert "@{...}" template until actuation, so it is safe to embed at
// construction time.
function deleteBook(id) {
  id = asInteger(id);
  return svc.delete("/books/" + sutBookIdRef(id), {
    expectedResponseCodes: [200],
    parameters: { description: deleteDescription("Book", id), id: id }
  });
}

function verifyBookDetailExists(id) {
  id = asInteger(id);
  return svc.get("/books/" + sutBookIdRef(id), {
    expectedResponseCodes: [200],
    parameters: { description: verifyExistsDescription("Book", id, "book detail"), id: id },
    callback: expectBookDetail(id)
  });
}

function verifyBookExists(id) {
  id = asInteger(id);
  return readSutList("/books", { q: sutBookIdRef(id), description: verifyListedDescription("Book", id, "books") }, expectListed("BOOK", id));
}

function verifyBookAbsentFromBooks(id) {
  id = asInteger(id);
  return readSutList("/books", { q: sutBookIdRef(id), description: verifyAbsentDescription("Book", id, "books") }, expectNotListed("BOOK", id, "id"));
}

function verifyBookAbsentFromLoans(id) {
  id = asInteger(id);
  return readSutList("/loans", { bookId: sutBookIdRef(id), description: verifyAbsentDescription("Book", id, "loans") }, expectEmptyList("loans of Book " + id));
}

function verifyBookAbsentFromHolds(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutBookIdRef(id), description: verifyAbsentDescription("Book", id, "holds") }, expectNotListed("BOOK", id, "bookId"));
}

// 400: the book is on loan or on hold.
function tryToDeleteBookAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/books/" + sutBookIdRef(id), {
    expectedResponseCodes: [400],
    parameters: { description: verifyRejectedDescription("Book", id, "delete", "the book is on loan or on hold"), id: id }
  });
}

// 404: the book existed and was deleted (its RTV entry still resolves to the old SUT id).
function tryToDeleteDeletedBookAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/books/" + sutBookIdRef(id), {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("Book", id, "delete", "the book no longer exists"), id: id }
  });
}

// 404: the id was never created (see missingId()), so it has no RTV entry and is sent as a
// plain id.
function tryToDeleteNonexistingBookAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/books/" + id, {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("Book", id, "delete", "the book does not exist"), id: id }
  });
}

//////////////////////////////////////////////////////////////////////////
// Users
//////////////////////////////////////////////////////////////////////////

function createUser(id, name) {
  id = asInteger(id);
  return svc.post("/users", {
    body: JSON.stringify({ name: asString(name) }),
    expectedResponseCodes: [201],
    parameters: { description: createDescription("User", id), id: id },
    callback: rememberCreatedId("USER", id)
  });
}

function deleteUser(id) {
  id = asInteger(id);
  return svc.delete("/users/" + sutUserIdRef(id), {
    expectedResponseCodes: [200],
    parameters: { description: deleteDescription("User", id), id: id }
  });
}

function verifyUserExists(id) {
  id = asInteger(id);
  return readSutList("/users", { q: sutUserIdRef(id), description: verifyListedDescription("User", id, "users") }, expectListed("USER", id));
}

function verifyUserAbsentFromUsers(id) {
  id = asInteger(id);
  return readSutList("/users", { q: sutUserIdRef(id), description: verifyAbsentDescription("User", id, "users") }, expectNotListed("USER", id, "id"));
}

function verifyUserAbsentFromLoans(id) {
  id = asInteger(id);
  return readSutList("/loans", { userId: sutUserIdRef(id), description: verifyAbsentDescription("User", id, "loans") }, expectEmptyList("loans of User " + id));
}

function verifyUserAbsentFromHolds(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutUserIdRef(id), description: verifyAbsentDescription("User", id, "holds") }, expectNotListed("USER", id, "userId"));
}

// 400: the reader has a loan or a hold.
function tryToDeleteUserAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/users/" + sutUserIdRef(id), {
    expectedResponseCodes: [400],
    parameters: { description: verifyRejectedDescription("User", id, "delete", "the reader has a loan or a hold"), id: id }
  });
}

// 404: the reader existed and was deleted.
function tryToDeleteDeletedUserAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/users/" + sutUserIdRef(id), {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("User", id, "delete", "the reader no longer exists"), id: id }
  });
}

// 404: the id was never created (plain id, see tryToDeleteNonexistingBookAndExpectError).
function tryToDeleteNonexistingUserAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/users/" + id, {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("User", id, "delete", "the reader does not exist"), id: id }
  });
}

//////////////////////////////////////////////////////////////////////////
// Loans
//////////////////////////////////////////////////////////////////////////

function createLoan(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return svc.post("/loans", {
    body: pairBody(sutUserIdRef(userId), sutBookIdRef(bookId)),
    expectedResponseCodes: [201],
    parameters: { description: createDescription("Loan", userId + "/" + bookId), userId: userId, bookId: bookId }
  });
}

// A loan request the rules reject (400). userIdMissing/bookIdMissing are true when the caller is
// deliberately exercising a nonexistent foreign key: that id was never created and has no RTV
// entry, so it is sent as a plain id (see sutIdRef).
function rejectedLoan(userId, bookId, reason, userIdMissing, bookIdMissing) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return svc.post("/loans", {
    body: pairBody(sutUserIdRef(userId, userIdMissing), sutBookIdRef(bookId, bookIdMissing)),
    expectedResponseCodes: [400],
    parameters: { description: verifyRejectedDescription("Loan", userId + "/" + bookId, "create", reason), userId: userId, bookId: bookId }
  });
}

// The pair is in UserBook.CannotCreateLoan: the book is on loan, or (under the original rules)
// the reader already has a loan.
function tryToCreateLoanAndExpectError(userId, bookId) {
  return rejectedLoan(userId, bookId, "the book or the reader already has a loan", false, false);
}

function tryToCreateLoanWithNonexistentUserAndExpectError(missingUserId, bookId) {
  return rejectedLoan(missingUserId, bookId, "the reader does not exist", true, false);
}

function tryToCreateLoanWithNonexistentBookAndExpectError(userId, missingBookId) {
  return rejectedLoan(userId, missingBookId, "the book does not exist", false, true);
}

function tryToCreateLoanWithNonexistentUserAndBookAndExpectError(missingUserId, missingBookId) {
  return rejectedLoan(missingUserId, missingBookId, "neither the reader nor the book exists", true, true);
}

// The reader or the book existed and was deleted; its RTV entry still resolves to the old SUT id.
function tryToCreateLoanWithDeletedUserAndExpectError(deletedUserId, bookId) {
  return rejectedLoan(deletedUserId, bookId, "the reader no longer exists", false, false);
}

function tryToCreateLoanWithDeletedBookAndExpectError(userId, deletedBookId) {
  return rejectedLoan(userId, deletedBookId, "the book no longer exists", false, false);
}

function deleteLoan(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return svc.delete("/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), {
    expectedResponseCodes: [200],
    parameters: { description: deleteDescription("Loan", userId + "/" + bookId), userId: userId, bookId: bookId }
  });
}

function verifyLoanExists(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return readSutList("/loans", {
    userId: sutUserIdRef(userId),
    bookId: sutBookIdRef(bookId),
    description: verifyListedDescription("Loan", userId + "/" + bookId, "loans")
  }, expectLoanListed(userId, bookId));
}

function verifyLoanAbsent(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return readSutList("/loans", {
    userId: sutUserIdRef(userId),
    bookId: sutBookIdRef(bookId),
    description: verifyAbsentDescription("Loan", userId + "/" + bookId, "loans")
  }, expectEmptyList("loan of " + userId + "/" + bookId));
}

// 404: the loan existed and was returned.
function tryToDeleteDeletedLoanAndExpectError(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  svc.delete("/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("Loan", userId + "/" + bookId, "delete", "the loan no longer exists"), userId: userId, bookId: bookId }
  });
}

// 404: neither id was ever created (plain ids).
function tryToDeleteNonexistingLoanAndExpectError(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  svc.delete("/loans/" + userId + "/" + bookId, {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("Loan", userId + "/" + bookId, "delete", "the loan does not exist"), userId: userId, bookId: bookId }
  });
}

//////////////////////////////////////////////////////////////////////////
// Holds
//////////////////////////////////////////////////////////////////////////

// The SUT assigns the hold's id itself (it reads only userId/bookId from the payload); `id` is
// this story's bookkeeping handle, like a book's id in createBook.
function createHold(id, userId, bookId) {
  id = asInteger(id);
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return svc.post("/holds", {
    body: pairBody(sutUserIdRef(userId), sutBookIdRef(bookId)),
    expectedResponseCodes: [201],
    parameters: { description: createDescription("Hold", id) + " for User " + userId + " and Book " + bookId, id: id, userId: userId, bookId: bookId },
    callback: rememberCreatedId("HOLD", id)
  });
}

// A hold request the rules reject (400); see rejectedLoan for the *Missing flags. A rejected
// hold gets no id: it never exists, so it is described by its reader/book pair.
function rejectedHold(userId, bookId, reason, userIdMissing, bookIdMissing) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return svc.post("/holds", {
    body: pairBody(sutUserIdRef(userId, userIdMissing), sutBookIdRef(bookId, bookIdMissing)),
    expectedResponseCodes: [400],
    parameters: { description: verifyRejectedDescription("Hold", "for User " + userId + " and Book " + bookId, "create", reason), userId: userId, bookId: bookId }
  });
}

function tryToCreateHoldWithNonexistentUserAndExpectError(missingUserId, bookId) {
  return rejectedHold(missingUserId, bookId, "the reader does not exist", true, false);
}

function tryToCreateHoldWithNonexistentBookAndExpectError(userId, missingBookId) {
  return rejectedHold(userId, missingBookId, "the book does not exist", false, true);
}

function tryToCreateHoldWithNonexistentUserAndBookAndExpectError(missingUserId, missingBookId) {
  return rejectedHold(missingUserId, missingBookId, "neither the reader nor the book exists", true, true);
}

function tryToCreateHoldWithDeletedUserAndExpectError(deletedUserId, bookId) {
  return rejectedHold(deletedUserId, bookId, "the reader no longer exists", false, false);
}

function tryToCreateHoldWithDeletedBookAndExpectError(userId, deletedBookId) {
  return rejectedHold(userId, deletedBookId, "the book no longer exists", false, false);
}

function deleteHold(id, userId, bookId) {
  id = asInteger(id);
  userId = optionalInteger(userId);
  bookId = optionalInteger(bookId);
  var parameters = { description: deleteDescription("Hold", id, userId === null || bookId === null ? "" : "for User " + userId + " and Book " + bookId), id: id };
  if (userId !== null) parameters.userId = userId;
  if (bookId !== null) parameters.bookId = bookId;
  return svc.delete("/holds/" + sutHoldIdRef(id), { expectedResponseCodes: [200], parameters: parameters });
}

function verifyHoldExists(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutHoldIdRef(id), description: verifyListedDescription("Hold", id, "holds") }, expectListed("HOLD", id));
}

function verifyHoldAbsent(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutHoldIdRef(id), description: verifyAbsentDescription("Hold", id, "holds") }, expectNotListed("HOLD", id, "id"));
}

// 404: the hold existed and was cancelled.
function tryToDeleteDeletedHoldAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/holds/" + sutHoldIdRef(id), {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("Hold", id, "delete", "the hold no longer exists"), id: id }
  });
}

// 404: the id was never created (plain id).
function tryToDeleteNonexistingHoldAndExpectError(id) {
  id = asInteger(id);
  svc.delete("/holds/" + id, {
    expectedResponseCodes: [404],
    parameters: { description: verifyRejectedDescription("Hold", id, "delete", "the hold does not exist"), id: id }
  });
}
