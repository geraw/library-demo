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
// 2. EventSets such as AnyBookAdded and matchAnyUserDeleted that classify events.
// 3. extractEventData(), which converts a concrete event into semantic fields.
//
// Stories use action functions and EventSets to describe behavior. The DAL uses
// EventSets plus extractEventData() to update the Context model without parsing
// URLs, bodies, or transport parameters itself.
//
// Every action function sends exactly one REST request: one call, one event.
// Negative checks (tryTo*AndExpectError) are separate functions that likewise
// send one request, with the rejecting response code as the expected one.
//////////////////////////////////////////////////////////////////////////

// The model addresses each entity by the small id a story picks at creation; the SUT's own,
// server-assigned id is tracked separately via RTVs at the REST boundary. See the handoff and
// remaining verification work in the repository's TODO.md.

var host = (typeof host !== 'undefined') ? host : 'localhost';
var port = (typeof port !== 'undefined') ? port : 23242;
var protocol = (typeof protocol !== 'undefined') ? protocol : 'http';
var path = '';

const svc = new RESTSession(protocol + "://" + host + ":" + port + path, "provengo-client", { headers: { "Content-Type": "application/json", "api_key": "special-key" } });

function modelFail(msg) { bp.log.error(msg); throw new Error(msg); }

// expectedCode arguments are optional everywhere below; this applies the per-action default.
function codeOrDefault(expectedCode, fallback) {
  return expectedCode === undefined || expectedCode === null ? fallback : asInteger(expectedCode);
}

function optionalInteger(value) {
  return value === undefined || value === null ? null : asInteger(value);
}

// asInteger, asString, the *Description builders, getExpectedResponseCodes, hasExpectedCode,
// getRequestPath, getJsonBody, readSutList, tryToUpdateAndExpectError, and
// verifyMissingEntityReadIsRejected live in lib/utils.js.

// Boundary adapter from concrete REST events to semantic event data.
// Consumers can depend on fields like id, userId, bookId, title, and
// loanNumber without knowing whether the values came from a JSON body
// or from request metadata.
//
// parameters win over body: actions that address an RTV-mapped entity (see the RTV helpers below)
// attach the logical id as a parameter, while their body/URL carries a sutIdRef "@{...}"
// reference. Every event the DAL and the stories pass here (the Any*Added/Any*Deleted events)
// carries its ids in parameters, so the body is only a fallback.
function extractEventData(e) {
  var body = getJsonBody(e) || {};
  var data = e && e.data ? e.data : e;
  var parameters = data && data.parameters ? data.parameters : {};
  function firstDefined(primary, fallback) { return primary !== undefined && primary !== null ? primary : fallback; }

  return {
    id: firstDefined(parameters.id, body.id),
    title: body.title,
    name: body.name,
    userId: firstDefined(parameters.userId, body.userId),
    bookId: firstDefined(parameters.bookId, body.bookId),
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
// key ("USER1", "BOOK1", "LOAN1", "HOLD1", ...). Every wire-level use is a
// late-bound `@{...}` expression; parameters retain that id for the DAL.
//////////////////////////////////////////////////////////////////////////

function rtvKey(entityType, id) {
  return entityType + asInteger(id);
}

// Returns a late-bound "@{...}" expression, substituted with the SUT id by Provengo's
// runtime only once the sampled scenario actually executes the request that carries it.
//
// Pass missing = true for an id that was deliberately never created (e.g. via
// generateMissingId()): its RTV key was never set, so resolving `@{...}` for it would
// throw a ReferenceError at actuation time. In that case the plain id is used as-is - it
// already can't collide with any SUT-assigned id, so no lookup is needed.
function sutIdRef(entityType, id, missing) {
  return missing === true ? asInteger(id) : "@{" + rtvKey(entityType, id) + "}";
}

function sutUserIdRef(id, missing) { return sutIdRef("USER", id, missing); }
function sutBookIdRef(id, missing) { return sutIdRef("BOOK", id, missing); }
function sutHoldIdRef(id, missing) { return sutIdRef("HOLD", id, missing); }

// Callback functions execute later than model generation. Constructing a callback
// with the key embedded in its source avoids closing over a generation-time local.
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

//////////////////////////////////////////////////////////////////////////
// Interface action functions.
//
// These functions are the only place stories should actuate the SUT. They
// normalize argument types, build URLs/bodies, and attach semantic parameters
// that extractEventData() can later expose to other layers.
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

// Sends one malformed create request (the required field is missing) and expects it rejected.
// `id` only labels the event; the SUT never sees it.
function tryToCreateBookWithBadParametersAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("Book", id, "create", "required parameters are missing or invalid");
  return svc.post("/books", { body: JSON.stringify({}), expectedResponseCodes: [expectedCode], parameters: { description: description } });
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

function tryToUpdateBookAndExpectError(id, body, expectedCode) {
  id = asInteger(id);
  expectedCode = codeOrDefault(expectedCode, 405);
  tryToUpdateAndExpectError("Book", id, "/books/" + sutBookIdRef(id), body, expectedCode);
}

// The verify*Exists/verify*AbsentFromAllLists reads below only check that the SUT answers 200 -
// see readSutList. Checking the list's contents would need a REST callback.
// Gera: yet their descriptions ("Verify: Book 3 is absent from loans list") claim a content check
// that never happens. Should the descriptions say what is actually tested?
function verifyBookExists(id) {
  id = asInteger(id);
  return readSutList("/books", { q: asString(sutBookIdRef(id)), description: verifyExistsDescription("Book", id, "books") });
}

function verifyBookAbsentFromAllLists(id) {
  id = asInteger(id);
  var bookIdRef = asString(sutBookIdRef(id));
  readSutList("/books", { q: bookIdRef, description: verifyAbsentDescription("Book", id, "books") });
  readSutList("/loans", { bookId: bookIdRef, description: verifyAbsentDescription("Book", id, "loans") });
  return readSutList("/holds", { q: bookIdRef, description: verifyAbsentDescription("Book", id, "holds") });
}

function tryToDeleteBookAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("Book", id, "delete", "the operation is not allowed in this state");
  svc.delete("/books/" + sutBookIdRef(id), { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedBookAndExpectError(id) {
  tryToDeleteBookAndExpectError(id, 404);
}

// id was never created (see generateMissingId()), so it has no RTV entry: build the request
// directly with the plain id instead of going through tryToDeleteBookAndExpectError/sutBookIdRef.
function tryToDeleteNonexistingBookAndExpectError(id) {
  id = asInteger(id);
  var description = verifyRejectedDescription("Book", id, "delete", "the operation is not allowed in this state");
  svc.delete("/books/" + id, { expectedResponseCodes: [404], parameters: { description: description } });
}

// Pass-throughs to the Any*Deleted EventSets above, used by lib_stories.js's
// on(matchAny*Deleted(), ...) verify-after-deletion bthreads.
// Claude: do we need these pass-throughs, or can the stories use AnyBookDeleted etc. directly?
function matchAnyBookDeleted() {
  return AnyBookDeleted;
}

//////////////////////////////////////////////////////////////////////////
// Loans
//////////////////////////////////////////////////////////////////////////

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

// Claude: rememberCreatedId("LOAN", ...) stores a LOAN<n> RTV that nothing ever reads (loans are
// addressed by their user/book pair), so loanNumber only feeds descriptions. Needed?
//
// userId/bookId in the body are late-bound "@{...}" placeholders (see the sutIdRef doc comment
// above). userIdMissing/bookIdMissing are true when the caller is deliberately exercising a
// nonexistent foreign key (see tryToCreateLoanWithNonexistent{User,Book,UserAndBook}AndExpectError):
// that id was never created and has no RTV entry.
function createLoan(userId, bookId, loanNumber, expectedCode, description, userIdMissing, bookIdMissing) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  loanNumber = optionalInteger(loanNumber);
  expectedCode = codeOrDefault(expectedCode, 201);

  var reqDescription = description || (createDescription("Loan", userId + "/" + bookId) + (loanNumber === null ? "" : " number " + loanNumber));
  var parameters = { description: reqDescription, userId: userId, bookId: bookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;

  var options = {
    body: JSON.stringify({ userId: sutUserIdRef(userId, userIdMissing), bookId: sutBookIdRef(bookId, bookIdMissing) }),
    expectedResponseCodes: [expectedCode],
    parameters: parameters
  };
  if (expectedCode === 201 && loanNumber !== null) options.callback = rememberCreatedId("LOAN", loanNumber);
  return svc.post("/loans", options);
}

function tryToCreateLoanAndExpectError(userId, bookId, loanNumber, expectedCode) {
  expectedCode = codeOrDefault(expectedCode, 400);
  return createLoan(userId, bookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", userId + "/" + bookId, "create", "the operation is not allowed in this state"));
}

// missingUserId/bookId/missingBookId were never created (see generateMissingId()), so they have no
// RTV entry; createLoan is told which argument(s) to send as a plain id instead of resolving one.
function tryToCreateLoanWithNonexistentUserAndExpectError(missingUserId, bookId, loanNumber, expectedCode) {
  expectedCode = codeOrDefault(expectedCode, 400);
  return createLoan(missingUserId, bookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", missingUserId + "/" + bookId, "create", "the operation is not allowed in this state"), true, false);
}

function tryToCreateLoanWithNonexistentBookAndExpectError(userId, missingBookId, loanNumber, expectedCode) {
  expectedCode = codeOrDefault(expectedCode, 400);
  return createLoan(userId, missingBookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", userId + "/" + missingBookId, "create", "the operation is not allowed in this state"), false, true);
}

function tryToCreateLoanWithNonexistentUserAndBookAndExpectError(missingUserId, missingBookId, loanNumber, expectedCode) {
  expectedCode = codeOrDefault(expectedCode, 400);
  return createLoan(missingUserId, missingBookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", missingUserId + "/" + missingBookId, "create", "the operation is not allowed in this state"), true, true);
}

// Sends one malformed create request (both required fields missing) and expects it rejected.
// `userId` only labels the event; the SUT never sees it.
function tryToCreateLoanWithBadParametersAndExpectError(userId, expectedCode) {
  userId = asInteger(userId);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("Loan", userId, "create", "required parameters are missing or invalid");
  return svc.post("/loans", { body: JSON.stringify({}), expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function deleteLoan(userId, bookId, loanNumber) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  loanNumber = optionalInteger(loanNumber);

  var reqDescription = deleteDescription("Loan", userId + "/" + bookId, loanNumber === null ? "" : "number " + loanNumber);
  var parameters = { description: reqDescription, userId: userId, bookId: bookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  return svc.delete("/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), {
    expectedResponseCodes: [200],
    parameters: parameters
  });
}

function tryToUpdateLoanAndExpectError(userId, bookId, body, expectedCode) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  expectedCode = codeOrDefault(expectedCode, 405);
  tryToUpdateAndExpectError("Loan", userId + "/" + bookId, "/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), body, expectedCode);
}

// Gera: (bookId, userId) here and in verifyLoanAbsentFromAllLists, but (userId, bookId) in
// createLoan/deleteLoan, and (bookId, id, userId) in createHold. Mixed argument orders already
// caused one swapped-ids bug (d242a26) - one order everywhere?
function verifyLoanExists(bookId, userId) {
  bookId = asInteger(bookId);
  userId = asInteger(userId);
  return readSutList("/loans", {
    userId: sutUserIdRef(userId),
    bookId: sutBookIdRef(bookId),
    description: verifyExistsDescription("Loan", userId + "/" + bookId, "loans")
  });
}

// Gera: reads one list, not "all lists", and its only caller always passes bookId, so the
// bookId === null branch is dead. Rename to verifyLoanAbsent and drop the branch?
function verifyLoanAbsentFromAllLists(bookId, userId) {
  var bookIdRef = bookId === undefined || bookId === null ? null : sutBookIdRef(bookId);
  userId = asInteger(userId);
  var loanId = userId + (bookIdRef === null ? "" : "/" + bookIdRef);
  var parameters = { userId: sutUserIdRef(userId), description: verifyAbsentDescription("Loan", loanId, "loans") };
  if (bookIdRef !== null) parameters.bookId = asString(bookIdRef);
  return readSutList("/loans", parameters);
}

function tryToDeleteLoanAndExpectError(userId, bookId, expectedCode) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("Loan", userId + "/" + bookId, "delete", "the operation is not allowed in this state");
  svc.delete("/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedLoanAndExpectError(userId, bookId) {
  tryToDeleteLoanAndExpectError(userId, bookId, 404);
}

// userId/bookId were never created (see generateMissingId()), so neither has an RTV entry: build
// the request directly with the plain ids instead of going through
// tryToDeleteLoanAndExpectError/sutUserIdRef/sutBookIdRef.
function tryToDeleteNonexistingLoanAndExpectError(userId, bookId) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  var description = verifyRejectedDescription("Loan", userId + "/" + bookId, "delete", "the operation is not allowed in this state");
  svc.delete("/loans/" + userId + "/" + bookId, { expectedResponseCodes: [404], parameters: { description: description } });
}

function matchAnyLoanDeleted() {
  return AnyLoanDeleted;
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

// Sends one malformed create request (the required field is missing) and expects it rejected.
// `id` only labels the event; the SUT never sees it.
function tryToCreateUserWithBadParametersAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("User", id, "create", "required parameters are missing or invalid");
  return svc.post("/users", { body: JSON.stringify({}), expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function deleteUser(id) {
  id = asInteger(id);
  return svc.delete("/users/" + sutUserIdRef(id), {
    expectedResponseCodes: [200],
    parameters: { description: deleteDescription("User", id), id: id }
  });
}

function tryToUpdateUserAndExpectError(id, body, expectedCode) {
  id = asInteger(id);
  expectedCode = codeOrDefault(expectedCode, 405);
  tryToUpdateAndExpectError("User", id, "/users/" + sutUserIdRef(id), body, expectedCode);
}

function verifyUserExists(id) {
  id = asInteger(id);
  return readSutList("/users", { q: sutUserIdRef(id), description: verifyExistsDescription("User", id, "users") });
}

function verifyUserAbsentFromAllLists(id) {
  id = asInteger(id);
  readSutList("/users", { q: sutUserIdRef(id), description: verifyAbsentDescription("User", id, "users") });
  readSutList("/loans", { userId: sutUserIdRef(id), description: verifyAbsentDescription("User", id, "loans") });
  return readSutList("/holds", { q: sutUserIdRef(id), description: verifyAbsentDescription("User", id, "holds") });
}

function tryToDeleteUserAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("User", id, "delete", "the operation is not allowed in this state");
  svc.delete("/users/" + sutUserIdRef(id), { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedUserAndExpectError(id) {
  tryToDeleteUserAndExpectError(id, 404);
}

// id was never created (see generateMissingId()), so it has no RTV entry: build the request
// directly with the plain id instead of going through tryToDeleteUserAndExpectError/sutUserIdRef.
function tryToDeleteNonexistingUserAndExpectError(id) {
  id = asInteger(id);
  var description = verifyRejectedDescription("User", id, "delete", "the operation is not allowed in this state");
  svc.delete("/users/" + id, { expectedResponseCodes: [404], parameters: { description: description } });
}

function matchAnyUserDeleted() {
  return AnyUserDeleted;
}

//////////////////////////////////////////////////////////////////////////
// Holds
//////////////////////////////////////////////////////////////////////////

// The SUT assigns the hold's id itself (see sut.py's POST /holds, which reads only userId/bookId
// from the payload); `id` is this story's bookkeeping handle, like a book's id in createBook.
// userId/bookId in the body are late-bound "@{...}" placeholders (see the sutIdRef doc comment
// above). bookIdMissing/userIdMissing are true when the caller is deliberately exercising a
// nonexistent foreign key (see tryToCreateHoldWithNonexistent{User,Book,UserAndBook}AndExpectError):
// that id was never created and has no RTV entry.
function createHold(bookId, id, userId, expectedCode, description, bookIdMissing, userIdMissing) {
  bookId = asInteger(bookId);
  id = asInteger(id);
  userId = asInteger(userId);
  expectedCode = codeOrDefault(expectedCode, 201);

  var reqDescription = description || (createDescription("Hold", id) + " for User " + userId + " and Book " + bookId);
  var options = {
    body: JSON.stringify({ userId: sutUserIdRef(userId, userIdMissing), bookId: sutBookIdRef(bookId, bookIdMissing) }),
    expectedResponseCodes: [expectedCode],
    parameters: { description: reqDescription, id: id, userId: userId, bookId: bookId }
  };
  if (expectedCode === 201) options.callback = rememberCreatedId("HOLD", id);
  return svc.post("/holds", options);
}

// missingBookId/userId/missingUserId were never created (see generateMissingId()), so they have no
// RTV entry; createHold is told which argument(s) to send as a plain id instead of resolving one.
function tryToCreateHoldWithNonexistentUserAndExpectError(bookId, id, missingUserId, expectedCode) {
  expectedCode = codeOrDefault(expectedCode, 400);
  return createHold(bookId, id, missingUserId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the operation is not allowed in this state"), false, true);
}

function tryToCreateHoldWithNonexistentBookAndExpectError(missingBookId, id, userId, expectedCode) {
  expectedCode = codeOrDefault(expectedCode, 400);
  return createHold(missingBookId, id, userId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the operation is not allowed in this state"), true, false);
}

function tryToCreateHoldWithNonexistentUserAndBookAndExpectError(missingBookId, id, missingUserId, expectedCode) {
  expectedCode = codeOrDefault(expectedCode, 400);
  return createHold(missingBookId, id, missingUserId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the operation is not allowed in this state"), true, true);
}

// Sends one malformed create request (both required fields missing) and expects it rejected.
// `id`/`userId` only label the event; the SUT never sees them.
function tryToCreateHoldWithBadParametersAndExpectError(id, userId, expectedCode) {
  id = asInteger(id);
  userId = asInteger(userId);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("Hold", id, "create", "required parameters are missing or invalid");
  return svc.post("/holds", { body: JSON.stringify({}), expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function deleteHold(id, userId, bookId) {
  id = asInteger(id);
  userId = optionalInteger(userId);
  bookId = optionalInteger(bookId);

  var reqDescription = deleteDescription("Hold", id, userId === null || bookId === null ? "" : "for User " + userId + " and Book " + bookId);
  var parameters = { description: reqDescription, id: id };
  if (userId !== null) parameters.userId = userId;
  if (bookId !== null) parameters.bookId = bookId;
  return svc.delete("/holds/" + sutHoldIdRef(id), { expectedResponseCodes: [200], parameters: parameters });
}

// Claude: userId/bookId are normalized and then never used.
function tryToUpdateHoldAndExpectError(id, userId, bookId, body, expectedCode) {
  id = asInteger(id);
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  expectedCode = codeOrDefault(expectedCode, 405);
  tryToUpdateAndExpectError("Hold", id, "/holds/" + sutHoldIdRef(id), body, expectedCode);
}

function verifyHoldExists(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutHoldIdRef(id), description: verifyExistsDescription("Hold", id, "holds") });
}

// Gera: one list, not "all lists" - rename?
function verifyHoldAbsentFromAllLists(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutHoldIdRef(id), description: verifyAbsentDescription("Hold", id, "holds") });
}

function tryToDeleteHoldAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = codeOrDefault(expectedCode, 400);
  var description = verifyRejectedDescription("Hold", id, "delete", "the operation is not allowed in this state");
  svc.delete("/holds/" + sutHoldIdRef(id), { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedHoldAndExpectError(id) {
  tryToDeleteHoldAndExpectError(id, 404);
}

// id was never created (see generateMissingId()), so it has no RTV entry: build the request
// directly with the plain id instead of going through tryToDeleteHoldAndExpectError/sutHoldIdRef.
function tryToDeleteNonexistingHoldAndExpectError(id) {
  id = asInteger(id);
  var description = verifyRejectedDescription("Hold", id, "delete", "the operation is not allowed in this state");
  svc.delete("/holds/" + id, { expectedResponseCodes: [404], parameters: { description: description } });
}

function matchAnyHoldDeleted() {
  return AnyHoldDeleted;
}
