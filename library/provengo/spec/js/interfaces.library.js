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
// no id of its own on the wire (the service addresses it by its reader/book pair),
// so loan functions take (userId, bookId, loanNumber); loanNumber is the story's
// label for the loan and reaches the DAL and the trace descriptions only.
//////////////////////////////////////////////////////////////////////////

var host = (typeof host !== 'undefined') ? host : 'localhost';
var port = (typeof port !== 'undefined') ? port : 23242;
var protocol = (typeof protocol !== 'undefined') ? protocol : 'http';
var path = '';

const svc = new RESTSession(protocol + "://" + host + ":" + port + path, "provengo-client", { headers: { "Content-Type": "application/json", "api_key": "special-key" } });

function modelFail(msg) { bp.log.error(msg); throw new Error(msg); }

function optionalInteger(value) {
  return value === undefined || value === null ? null : asInteger(value);
}

// asInteger, asString, the *Description builders, getExpectedResponseCodes, hasExpectedCode,
// getRequestPath, getJsonBody, readSutList, and verifyMissingEntityReadIsRejected live in
// lib/utils.js.

// Boundary adapter from concrete REST events to semantic event data. Consumers depend on
// fields like id, userId, bookId, title and loanNumber without knowing where they came from:
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
    bookId: parameters.bookId,
    loanNumber: parameters.loanNumber
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
// Pass missing = true for an id that was deliberately never created (generateMissingId() in
// lib_stories.js, 1000000001 and up): its RTV key was never set, so resolving `@{...}` for it
// would throw a ReferenceError at actuation time. The plain id is sent instead; it cannot
// collide with any SUT-assigned id, so no lookup is needed.
function sutIdRef(entityType, id, missing) {
  return missing === true ? asInteger(id) : "@{" + rtvKey(entityType, id) + "}";
}

function sutUserIdRef(id, missing) { return sutIdRef("USER", id, missing); }
function sutBookIdRef(id, missing) { return sutIdRef("BOOK", id, missing); }
function sutHoldIdRef(id, missing) { return sutIdRef("HOLD", id, missing); }

// A JSON body with reader and book ids. The references are written unquoted, so after
// Provengo substitutes the SUT id the body carries JSON numbers, not numeric strings.
function pairBody(userRef, bookRef) {
  return '{"userId":' + userRef + ',"bookId":' + bookRef + '}';
}

// The callback runs at actuation time, when the create response is available; it stores the
// SUT id under this entity's RTV key.
function rememberCreatedId(entityType, id) {
  var key = rtvKey(entityType, id);
  return function (response) {
    var body = JSON.parse(response.body);
    if (body.id === undefined || body.id === null) modelFail("Create response did not contain id");
    pvg.rtv.set(key, body.id);
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
// The list reads (verify*Exists / verify*AbsentFrom*) only check that the SUT
// answers 200 - see readSutList. Checking the list's contents would need a REST
// callback, so their descriptions say "Read:", not "Verify:". verifyBookDetailExists
// is the one real existence check: GET /books/{id} answers 200 only for a book
// that exists.
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
    parameters: { description: verifyExistsDescription("Book", id, "book detail"), id: id }
  });
}

function verifyBookExists(id) {
  id = asInteger(id);
  return readSutList("/books", { q: sutBookIdRef(id), description: readListAfterCreateDescription("Book", id, "books") });
}

function verifyBookAbsentFromBooks(id) {
  id = asInteger(id);
  return readSutList("/books", { q: sutBookIdRef(id), description: readListAfterDeleteDescription("Book", id, "books") });
}

function verifyBookAbsentFromLoans(id) {
  id = asInteger(id);
  return readSutList("/loans", { bookId: sutBookIdRef(id), description: readListAfterDeleteDescription("Book", id, "loans") });
}

function verifyBookAbsentFromHolds(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutBookIdRef(id), description: readListAfterDeleteDescription("Book", id, "holds") });
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

// 404: the id was never created (see generateMissingId()), so it has no RTV entry and is sent
// as a plain id.
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
  return readSutList("/users", { q: sutUserIdRef(id), description: readListAfterCreateDescription("User", id, "users") });
}

function verifyUserAbsentFromUsers(id) {
  id = asInteger(id);
  return readSutList("/users", { q: sutUserIdRef(id), description: readListAfterDeleteDescription("User", id, "users") });
}

function verifyUserAbsentFromLoans(id) {
  id = asInteger(id);
  return readSutList("/loans", { userId: sutUserIdRef(id), description: readListAfterDeleteDescription("User", id, "loans") });
}

function verifyUserAbsentFromHolds(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutUserIdRef(id), description: readListAfterDeleteDescription("User", id, "holds") });
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

function createLoan(userId, bookId, loanNumber) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  loanNumber = optionalInteger(loanNumber);
  var parameters = { description: createDescription("Loan", userId + "/" + bookId) + (loanNumber === null ? "" : " number " + loanNumber), userId: userId, bookId: bookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  return svc.post("/loans", {
    body: pairBody(sutUserIdRef(userId), sutBookIdRef(bookId)),
    expectedResponseCodes: [201],
    parameters: parameters
  });
}

// A loan request the rules reject (400). userIdMissing/bookIdMissing are true when the caller is
// deliberately exercising a nonexistent foreign key: that id was never created and has no RTV
// entry, so it is sent as a plain id (see sutIdRef).
function rejectedLoan(userId, bookId, loanNumber, reason, userIdMissing, bookIdMissing) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  loanNumber = optionalInteger(loanNumber);
  var parameters = { description: verifyRejectedDescription("Loan", userId + "/" + bookId, "create", reason), userId: userId, bookId: bookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  return svc.post("/loans", {
    body: pairBody(sutUserIdRef(userId, userIdMissing), sutBookIdRef(bookId, bookIdMissing)),
    expectedResponseCodes: [400],
    parameters: parameters
  });
}

function tryToCreateLoanAndExpectError(userId, bookId, loanNumber) {
  return rejectedLoan(userId, bookId, loanNumber, "the book is on loan", false, false);
}

function tryToCreateLoanWithNonexistentUserAndExpectError(missingUserId, bookId, loanNumber) {
  return rejectedLoan(missingUserId, bookId, loanNumber, "the reader does not exist", true, false);
}

function tryToCreateLoanWithNonexistentBookAndExpectError(userId, missingBookId, loanNumber) {
  return rejectedLoan(userId, missingBookId, loanNumber, "the book does not exist", false, true);
}

function tryToCreateLoanWithNonexistentUserAndBookAndExpectError(missingUserId, missingBookId, loanNumber) {
  return rejectedLoan(missingUserId, missingBookId, loanNumber, "neither the reader nor the book exists", true, true);
}

function deleteLoan(userId, bookId, loanNumber) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  loanNumber = optionalInteger(loanNumber);
  var parameters = { description: deleteDescription("Loan", userId + "/" + bookId, loanNumber === null ? "" : "number " + loanNumber), userId: userId, bookId: bookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  return svc.delete("/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), {
    expectedResponseCodes: [200],
    parameters: parameters
  });
}

function verifyLoanExists(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return readSutList("/loans", {
    userId: sutUserIdRef(userId),
    bookId: sutBookIdRef(bookId),
    description: readListAfterCreateDescription("Loan", userId + "/" + bookId, "loans")
  });
}

function verifyLoanAbsent(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return readSutList("/loans", {
    userId: sutUserIdRef(userId),
    bookId: sutBookIdRef(bookId),
    description: readListAfterDeleteDescription("Loan", userId + "/" + bookId, "loans")
  });
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

// A hold request the rules reject (400); see rejectedLoan for the *Missing flags.
function rejectedHold(id, userId, bookId, reason, userIdMissing, bookIdMissing) {
  id = asInteger(id);
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  return svc.post("/holds", {
    body: pairBody(sutUserIdRef(userId, userIdMissing), sutBookIdRef(bookId, bookIdMissing)),
    expectedResponseCodes: [400],
    parameters: { description: verifyRejectedDescription("Hold", id, "create", reason), id: id, userId: userId, bookId: bookId }
  });
}

function tryToCreateHoldWithNonexistentUserAndExpectError(id, missingUserId, bookId) {
  return rejectedHold(id, missingUserId, bookId, "the reader does not exist", true, false);
}

function tryToCreateHoldWithNonexistentBookAndExpectError(id, userId, missingBookId) {
  return rejectedHold(id, userId, missingBookId, "the book does not exist", false, true);
}

function tryToCreateHoldWithNonexistentUserAndBookAndExpectError(id, missingUserId, missingBookId) {
  return rejectedHold(id, missingUserId, missingBookId, "neither the reader nor the book exists", true, true);
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
  return readSutList("/holds", { q: sutHoldIdRef(id), description: readListAfterCreateDescription("Hold", id, "holds") });
}

function verifyHoldAbsent(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutHoldIdRef(id), description: readListAfterDeleteDescription("Hold", id, "holds") });
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
