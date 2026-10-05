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
//////////////////////////////////////////////////////////////////////////

// The model addresses each entity by the small id a story picks at creation; the SUT's own,
// server-assigned id is tracked separately via RTVs at the REST boundary. See the handoff and
// remaining verification work in the repository's TODO.md.

var host = (typeof host !== 'undefined') ? host : 'localhost';
var port = (typeof port !== 'undefined') ? port : 23242;
var protocol = (typeof protocol !== 'undefined') ? protocol : 'http';
var path = '';

const svc = new RESTSession(protocol + "://" + host + ":" + port + path, "provengo-client", { headers: { "Content-Type": "application/json", "api_key": "special-key" } });

// Every action below sends one of several request variants (each with its own
// body/expectedResponseCodes/parameters) by offering them all to sync() at once via
// requestOneOfDirect, so the event selection mechanism (not this code) picks which single variant
// is actually sent - letting fuzzing/exploration choose the request shape instead of a scripted
// for-loop that sends every case every time.
//
// No staleness recheck is needed between offering and sending: a story's ctx.bthread is ended
// by COBP at the very event that removes its entity from the query it was spawned for (the REST
// event itself is the DAL effect - see dal.js), so it can never actuate against an entity that
// stopped existing while its variants were waiting to be selected.

// Mirrors RESTSession's private ___apiBody___ so a fully-formed, already-actuatable REST event
// can be built here instead of only inside svc[method]. Reads session defaults
// (headers/parameters/expectedResponseCodes/callback) off `svc` itself rather than duplicating
// their values.
// Claude: this copies a private RESTSession internal. Is there a public Provengo way to build an
// unsent REST event? If not, should we ask for one, rather than track private internals?
function buildRestEvent(session, httpMethod, url, options) {
  options = options || {};
  var headers = options.headers !== undefined ? options.headers : session.defaultHeaders;
  var parameters = options.parameters !== undefined ? options.parameters : session.defaultParameters;
  var expectedResponseCodes = options.expectedResponseCodes !== undefined ? options.expectedResponseCodes : session.defaultExpectedResponseCodes;
  var callback = options.callback !== undefined ? options.callback : session.defaultCallback;
  var data = {
    lib: "REST",
    method: httpMethod,
    url: session.baseURL + url,
    headers: headers,
    parameters: parameters,
    expectedResponseCodes: expectedResponseCodes,
    callback: callback
  };
  if (options.body !== undefined) data.body = JSON.stringify(options.body);
  return bp.Event(httpMethod, data);
}

// Each variant already carries its real, fully-resolved url/body (the sutIdRef()-embedded template
// is safe to bake in at construction time - see the RTV doc comment below), so the variants
// themselves are offered as the actuatable REST events - a single sync, with no separate
// "chooser" event. `url` is a fallback used by variants that don't set their own (e.g. all
// POST-create variants share one url; DELETE variants each set their own since the id is part of
// the path).
// Claude: "Direct" only contrasted with the two-sync requestOneOf, which is gone. Rename to requestOneOf?
function requestOneOfDirect(method, url, variants) {
  if (!variants || variants.length === 0) pvg.fail("requestOneOfDirect requires at least one variant");
  var httpMethod = method.toUpperCase();
  var events = variants.map(function (v) {
    var evt = buildRestEvent(svc, httpMethod, v.url || url, v);
    // buildRestEvent already copies url/body/parameters/expectedResponseCodes/callback from v
    // onto evt.data using the REST library's own field names - that part of evt.data is standard
    // REST-actuator territory. `name` (this variant's descriptive identity, since the event
    // itself is named after the HTTP verb) and `valid` (checked by every create/delete retry loop
    // below) belong to no one but us, so they live under their own `model` key instead of sitting
    // flat alongside the actuator's fields.
    evt.data.model = { name: v.name, valid: v.valid === true };
    return evt;
  });
  return sync({ request: events });
}

// Claude: this shadows Provengo's own pvg. The REST callbacks (rememberCreatedId) call pvg.rtv.set,
// which this object doesn't have - that only works because callbacks run in a different scope.
// Rename this one (e.g. modelFail)?
const pvg = { fail: function (msg) { bp.log.error(msg); throw new Error(msg); } };

// asInteger, asString, and the *Description builders now live in lib/utils.js.

// getExpectedResponseCodes, hasExpectedCode, getRequestPath, and getJsonBody now live in lib/utils.js.

// Boundary adapter from concrete REST events to semantic event data.
// Consumers can depend on fields like id, userId, bookId, title, and
// loanNumber without knowing whether the values came from a JSON body,
// REST path, query parameter, or request metadata.
function extractEventData(e) {
  var body = getJsonBody(e) || {};
  var data = e && e.data ? e.data : e;
  var parameters = data && data.parameters ? data.parameters : {};
  
  // parameters win over body: actions that address an RTV-mapped entity (see the RTV helpers below)
  // attach the logical id as a parameter, while their body/URL carries a sutIdRef "@{...}"
  // reference. For every other field, parameters were never set before, so this is a no-op.
  var id = parameters.id !== undefined && parameters.id !== null ? parameters.id : body.id;
  var userId = parameters.userId !== undefined && parameters.userId !== null ? parameters.userId : body.userId;
  var bookId = parameters.bookId !== undefined && parameters.bookId !== null ? parameters.bookId : body.bookId;

  // Claude: every event that reaches this function (the Any*Added/Any*Deleted effects and handlers,
  // matchLoanAdded) already carries id/userId/bookId in parameters, and a valid request's URL holds
  // an "@{...}" template that parseInt skips. So isn't this path fallback dead? (Also: title falls
  // back to body.name below - why?)
  // Try extracting from path if they are not in body/parameters
  var pathValue = data.path || data.url || "";
  if (pathValue) {
    pathValue = String(pathValue).replace(/^https?:\/\/[^\/]+/, "");
    var segments = pathValue.split("/").filter(function (s) { return s.length > 0; });
    if (segments.length >= 2) {
      var lastSegment = segments[segments.length - 1];
      var lastSegmentInt = Number.parseInt(lastSegment, 10);
      if (!isNaN(lastSegmentInt)) {
        if (segments[0] === "users") {
          if (id === undefined || id === null) id = lastSegmentInt;
        } else if (segments[0] === "books") {
          if (id === undefined || id === null) id = lastSegmentInt;
        } else if (segments[0] === "holds") {
          if (id === undefined || id === null) id = lastSegmentInt;
        } else if (segments[0] === "loans") {
          if (segments.length >= 3) {
            var userSeg = Number.parseInt(segments[1], 10);
            var bookSeg = Number.parseInt(segments[2], 10);
            if (!isNaN(userSeg) && (userId === undefined || userId === null)) userId = userSeg;
            if (!isNaN(bookSeg) && (bookId === undefined || bookId === null)) bookId = bookSeg;
          }
        }
      }
    }
  }

  return {
    id: id,
    title: body.title !== undefined && body.title !== null ? body.title : body.name,
    name: body.name,
    userId: userId,
    bookId: bookId,
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
    if (body.id === undefined || body.id === null) pvg.fail("Create response did not contain id");
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
  // The request body no longer carries an id (see createBook/the RTV helpers above) - title is
  // the only client-supplied field left, so it is what marks this as a real book-create request.
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


// Claude: this block, and the other "now live in lib/utils.js" / "were replaced by" notes in this
// file, describe code that isn't here. The last line below points at
// verifyListQueryFuzzIsAccepted/verifyLoanQueryFuzzIsRejected, which don't exist. Drop them?
// readSutList, tryToUpdateAndExpectError, and verifyMissingEntityReadIsRejected now live in
// lib/utils.js.

// Malformed-delete and malformed-read rejection cases are covered by the dynamic valid/invalid
// loops inside deleteBook/deleteUser/deleteLoan/deleteHold and verifyBookDetailExists, so this
// file has no separate verifyMalformedDeleteIsRejected/verifyMalformedReadIsRejected helpers.

// The /books, /users, and /holds search endpoints accept any `q` value and always answer 200 (no
// format validation), so verifyBookExists/verifyUserExists/verifyHoldExists below have no
// rejectable invalid variant to fuzz - they read the SUT list directly. /loans search does
// validate userId/bookId, so verifyLoanExists uses the same dynamic valid/invalid loop as the
// create/delete actions (verifyListQueryFuzzIsAccepted/verifyLoanQueryFuzzIsRejected below).


//////////////////////////////////////////////////////////////////////////
// Interface action functions.
//
// These functions are the only place stories should actuate the SUT. They
// normalize argument types, build URLs/bodies, and attach semantic parameters
// that extractEventData() can later expose to other layers.
//////////////////////////////////////////////////////////////////////////

// The SUT assigns the book's id itself (title is the only client-supplied field), so there
// is no client-chosen id left to fuzz or to duplicate. The id parameter below is this story's
// own bookkeeping handle: it never goes on the wire, only into `parameters` for the DAL/matchers, and into
// the BOOK<n> RTV once the SUT id comes back.
function createBook(id, title) {
  id = asInteger(id);
  title = asString(title);

  var reqDescription = createDescription("Book", id);
  var captureResponse = rememberCreatedId("BOOK", id);
  var idParameters = { description: reqDescription, id: id };
  var variants = [
    { name: "createBook (valid-standard): " + id, body: { title: title }, expectedResponseCodes: [201], parameters: idParameters, callback: captureResponse, valid: true },
    { name: "createBook (valid-spaced-title): " + id, body: { title: " " + title }, expectedResponseCodes: [201], parameters: idParameters, callback: captureResponse, valid: true },
    // Positive counterpart to the "no unexpected-field case" note in
    // tryToCreateBookWithBadParametersAndExpectError below: locks in that an unrecognized field
    // is accepted (silently ignored), not merely untested.
    { name: "createBook (valid-unexpected-field): " + id, body: { title: title, unexpected: "value" }, expectedResponseCodes: [201], parameters: idParameters, callback: captureResponse, valid: true }
  ];

  var invalidCases = [
    { label: "missing title", body: {} },
    { label: "title has wrong type", body: { "title": 12345 } },
    { label: "title is null", body: { "title": null } },
    { label: "title is empty", body: { "title": "" } }
  ];

  variants = variants.concat(invalidCases.map(function(c) {
    var description = "createBook (invalid - " + c.label + "): " + id;
    return { name: description, body: c.body, expectedResponseCodes: [400], parameters: { description: description } };
  }));

  while (true) {
    var response = requestOneOfDirect("post", "/books", variants);
    if (response.data.model.valid === true) return response;
  }
}

// Claude: same four cases as createBook's invalidCases above (and likewise for the user, loan and
// hold variants) - two copies of each list to keep in sync. The *WithBadParameters b-threads in
// lib_stories.js send requests the create* fuzz loops already send.
function tryToCreateBookWithBadParametersAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/books";
  var reqDescription = verifyRejectedDescription("Book", id, "create", "required parameters are missing or invalid");
  // No "unexpected field" case: the SUT ignores extra fields on this endpoint (only title is
  // read/validated), so a request with one succeeds rather than being rejected.
  var cases = [
    { name: "missing title", body: {} },
    { name: "title has wrong type", body: { "title": 12345 } },
    { name: "title is null", body: { "title": null } },
    { name: "title is empty", body: { "title": "" } }
  ];
  var variants = cases.map(function (c) {
    return { body: c.body, expectedResponseCodes: [expectedCode], description: reqDescription + " - " + c.name };
  });
  requestOneOfDirect("post", url, variants);
}

// Claude: the invalid variants here (/books/bad-id, /books/0, /books/-1) don't mention the book,
// yet every delete of every book re-offers them, as do deleteUser/deleteLoan/deleteHold. Would
// testing each entity-independent rejection once be enough?
function deleteBook(id) {
  id = asInteger(id);
  // The SUT id reference is embedded directly at construction time (safe - sutBookIdRef() is an inert
  // "@{...}" template until actuation), and requestOneOfDirect offers these variants as the
  // actuatable events themselves - a single sync per call instead of a chooser sync followed by
  // a second, separate REST sync.
  var variants = [
    { name: "deleteBook (valid): " + id, url: "/books/" + sutBookIdRef(id), expectedResponseCodes: [200], parameters: { description: deleteDescription("Book", id), id: id }, valid: true },
    { name: "deleteBook (invalid - bad-id): " + id, url: "/books/bad-id", expectedResponseCodes: [400] },
    { name: "deleteBook (invalid - zero): " + id, url: "/books/0", expectedResponseCodes: [400] },
    { name: "deleteBook (invalid - negative): " + id, url: "/books/-1", expectedResponseCodes: [400] }
  ];
  while (true) {
    var response = requestOneOfDirect("delete", null, variants);
    if (response.data.model.valid === true) return response;
  }
}

// The book detail endpoint validates its id path parameter (malformed/zero/negative id -> 400)
// before checking existence (valid-format-but-missing id -> 404), so it gets the same
// dynamic valid/invalid fuzzing loop as the create/delete actions. See the Fuzzing
// Interface Layer Contract at the bottom of lib_stories.js.
function verifyBookDetailExists(id) {
  id = asInteger(id);

  var description = verifyExistsDescription("Book", id, "book detail");
  // The SUT id reference is embedded directly at construction time - see the sutIdRef doc comment above.
  var variants = [
    { name: "readBookDetail (valid-standard): " + id, url: "/books/" + sutBookIdRef(id), expectedResponseCodes: [200], parameters: { description: description, id: id }, valid: true },
    { name: "readBookDetail (valid-padded-id): " + id, url: "/books/00" + sutBookIdRef(id), expectedResponseCodes: [200], parameters: { description: description, id: id }, valid: true },
    { name: "readBookDetail (invalid - bad-id): " + id, url: "/books/bad-id", expectedResponseCodes: [400] },
    { name: "readBookDetail (invalid - zero): " + id, url: "/books/0", expectedResponseCodes: [400] },
    { name: "readBookDetail (invalid - negative): " + id, url: "/books/-1", expectedResponseCodes: [400] }
  ];
  while (true) {
    var response = requestOneOfDirect("get", null, variants);
    if (response.data.model.valid === true) return response;
  }
}

// verifyBookReadFuzz and verifyBookDeleteFuzz (static per-field fuzz cases) were replaced by
// the dynamic valid/invalid loop inside createBook/deleteBook/verifyBookDetailExists above.

function tryToUpdateBookAndExpectError(id, body, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  tryToUpdateAndExpectError("Book", id, "/books/" + sutBookIdRef(id), body, expectedCode);
}

// The verify*Exists/verify*AbsentFromAllLists reads below only check that the SUT answers 200 -
// see readSutList. Checking the list's contents would need a REST callback.
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
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/books/" + sutBookIdRef(id);
  var description = verifyRejectedDescription("Book", id, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
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

//////////////////////////////////////////////////////////////////////////
// Broad-deletion reaction wrappers.
//
// Trivial pass-throughs to the Any*Deleted EventSets above, used by lib_stories.js's
// on(matchAny*Deleted(), ...) verify-after-deletion bthreads. Stories no longer block() or
// wait-for on any narrower, entity-specific matcher (those were removed along with the
// block() guards they existed for - see lib_stories.js).
//////////////////////////////////////////////////////////////////////////

// Claude: do we need these pass-throughs, or can the stories use AnyBookDeleted etc. directly?
function matchAnyBookDeleted() {
  return AnyBookDeleted;
}

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

function deleteLoan(userId, bookId, loanNumber) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  loanNumber = loanNumber === undefined || loanNumber === null ? null : asInteger(loanNumber);

  var invalidCases = [
    { label: "bad-user-id", url: "/loans/bad-user-id/" + bookId },
    { label: "bad-book-id", url: "/loans/" + userId + "/bad-book-id" },
    { label: "zero userId", url: "/loans/0/" + bookId },
    { label: "zero bookId", url: "/loans/" + userId + "/0" },
    { label: "negative userId", url: "/loans/-1/" + bookId },
    { label: "negative bookId", url: "/loans/" + userId + "/-1" }
  ];

  var reqDescription = deleteDescription("Loan", userId + "/" + bookId, loanNumber === null ? "" : "number " + loanNumber);
  var parameters = { description: reqDescription, userId: userId, bookId: bookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  // The SUT id references are embedded directly at construction time - see the sutIdRef doc comment above.
  var variants = [{ name: "deleteLoan (valid): " + userId + "/" + bookId, url: "/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), expectedResponseCodes: [200], parameters: parameters, valid: true }];
  variants = variants.concat(invalidCases.map(function(c) {
    return { name: "deleteLoan (invalid - " + c.label + "): " + userId + "/" + bookId, url: c.url, expectedResponseCodes: [400] };
  }));

  while (true) {
    var response = requestOneOfDirect("delete", null, variants);
    if (response.data.model.valid === true) return response;
  }
}

// verifyLoanReadFuzz and verifyLoanDeleteFuzz (static per-field fuzz cases) were replaced by the
// dynamic valid/invalid loop inside createLoan/deleteLoan/verifyLoanExists above.

function tryToUpdateLoanAndExpectError(userId, bookId, body, expectedCode) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  tryToUpdateAndExpectError("Loan", userId + "/" + bookId, "/loans/" + sutUserIdRef(userId) + "/" + sutBookIdRef(bookId), body, expectedCode);
}

// Claude: rememberCreatedId("LOAN", ...) stores a LOAN<n> RTV that nothing ever reads (loans are
// addressed by their user/book pair), so loanNumber only feeds descriptions. Needed? Also, when
// tryToCreateLoanAndExpectError passes expectedCode 400, the "valid" variants are still named
// "createLoan (valid-...)", which already confused StrictGuidedRun.
function createLoan(userId, bookId, loanNumber, expectedCode, description, userIdMissing, bookIdMissing) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  loanNumber = loanNumber === undefined || loanNumber === null ? null : asInteger(loanNumber);

  var reqDescription = description || (createDescription("Loan", userId + "/" + bookId) + (loanNumber === null ? "" : " number " + loanNumber));
  expectedCode = expectedCode === undefined || expectedCode === null ? 201 : asInteger(expectedCode);
  var parameters = { description: reqDescription, userId: userId, bookId: bookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  // bookId in each valid body is a late-bound "@{...}" placeholder (see the sutIdRef doc comment
  // above), substituted with the SUT id by Provengo's runtime only once the request actually
  // fires. userIdMissing/bookIdMissing are true when the caller is deliberately exercising a
  // nonexistent foreign key (see tryToCreateLoanWithNonexistent{User,Book,UserAndBook}AndExpectError):
  // that id was never created and has no RTV entry.
  var variants = [
    { name: "createLoan (valid-standard): " + userId + "/" + bookId, body: { userId: sutUserIdRef(userId, userIdMissing), bookId: sutBookIdRef(bookId, bookIdMissing) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 && loanNumber !== null ? rememberCreatedId("LOAN", loanNumber) : undefined, valid: true },
    { name: "createLoan (valid-swapped-order): " + userId + "/" + bookId, body: { bookId: sutBookIdRef(bookId, bookIdMissing), userId: sutUserIdRef(userId, userIdMissing) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 && loanNumber !== null ? rememberCreatedId("LOAN", loanNumber) : undefined, valid: true },
    // Positive counterpart to the "no unexpected-field case" note in
    // tryToCreateLoanWithBadParametersAndExpectError below: locks in that an unrecognized field
    // is accepted (silently ignored), not merely untested.
    { name: "createLoan (valid-unexpected-field): " + userId + "/" + bookId, body: { userId: sutUserIdRef(userId, userIdMissing), bookId: sutBookIdRef(bookId, bookIdMissing), unexpected: "value" }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 && loanNumber !== null ? rememberCreatedId("LOAN", loanNumber) : undefined, valid: true }
  ];

  var invalidCases = [
    { label: "missing bookId", body: { "userId": userId } },
    { label: "missing userId", body: { "bookId": bookId } },
    { label: "missing all required fields", body: {} },
    { label: "userId has wrong type", body: { "userId": "bad-user-id", "bookId": bookId } },
    { label: "bookId has wrong type", body: { "userId": userId, "bookId": "bad-book-id" } },
    { label: "multiple wrong types", body: { "userId": true, "bookId": false } },
    { label: "userId is null", body: { "userId": null, "bookId": bookId } },
    { label: "bookId is null", body: { "userId": userId, "bookId": null } },
    { label: "userId is zero", body: { "userId": 0, "bookId": bookId } },
    { label: "bookId is zero", body: { "userId": userId, "bookId": 0 } },
    { label: "userId is negative", body: { "userId": -userId, "bookId": bookId } },
    { label: "bookId is negative", body: { "userId": userId, "bookId": -bookId } },
    { label: "userId is object", body: { "userId": { "val": userId }, "bookId": bookId } },
    { label: "bookId is object", body: { "userId": userId, "bookId": { "val": bookId } } }
  ];

  variants = variants.concat(invalidCases.map(function(c) {
    return { name: "createLoan (invalid - " + c.label + "): " + userId + "/" + bookId, body: c.body, expectedResponseCodes: [400] };
  }));

  while (true) {
    var response = requestOneOfDirect("post", "/loans", variants);
    if (response.data.model.valid === true) return response;
  }
}

function tryToCreateLoanAndExpectError(userId, bookId, loanNumber, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createLoan(userId, bookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", userId + "/" + bookId, "create", "the operation is not allowed in this state"));
}

// missingUserId/bookId/missingBookId were never created (see generateMissingId()), so they have no
// RTV entry; createLoan is told which argument(s) to send as a plain id instead of resolving one.
function tryToCreateLoanWithNonexistentUserAndExpectError(missingUserId, bookId, loanNumber, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createLoan(missingUserId, bookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", missingUserId + "/" + bookId, "create", "the operation is not allowed in this state"), true, false);
}

function tryToCreateLoanWithNonexistentBookAndExpectError(userId, missingBookId, loanNumber, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createLoan(userId, missingBookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", userId + "/" + missingBookId, "create", "the operation is not allowed in this state"), false, true);
}

function tryToCreateLoanWithNonexistentUserAndBookAndExpectError(missingUserId, missingBookId, loanNumber, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createLoan(missingUserId, missingBookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", missingUserId + "/" + missingBookId, "create", "the operation is not allowed in this state"), true, true);
}

function tryToCreateLoanWithBadParametersAndExpectError(userId, expectedCode) {
  userId = asInteger(userId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/loans";
  var reqDescription = verifyRejectedDescription("Loan", userId, "create", "required parameters are missing or invalid");
  // No "unexpected field" case: the SUT ignores extra fields on this endpoint (only userId/bookId
  // are read/validated - see sut.py's POST /loans), so a request with one succeeds rather than
  // being rejected. See the identical note on createBook.
  var cases = [
    { name: "missing bookId", body: { "userId": userId } },
    { name: "missing userId", body: { "bookId": userId } },
    { name: "missing all required fields", body: {} },
    { name: "userId has wrong type", body: { "userId": "bad-user-id", "bookId": userId } },
    { name: "bookId has wrong type", body: { "userId": userId, "bookId": "bad-book-id" } },
    { name: "multiple wrong types", body: { "userId": true, "bookId": false } },
    { name: "userId and bookId have swapped invalid values", body: { "bookId": userId, "userId": -userId } },
    { name: "userId is null", body: { "userId": null, "bookId": userId } },
    { name: "bookId is null", body: { "userId": userId, "bookId": null } },
    { name: "userId is zero", body: { "userId": 0, "bookId": userId } },
    { name: "bookId is zero", body: { "userId": userId, "bookId": 0 } },
    { name: "userId is negative", body: { "userId": -userId, "bookId": userId } },
    { name: "bookId is negative", body: { "userId": userId, "bookId": -userId } }
  ];
  var variants = cases.map(function (c) {
    return { body: c.body, expectedResponseCodes: [expectedCode], description: reqDescription + " - " + c.name };
  });
  requestOneOfDirect("post", url, variants);
}

// The loans search endpoint validates userId/bookId (malformed/zero/negative -> 400) before
// filtering, so it gets the same dynamic valid/invalid fuzzing loop as the create/delete actions.
function verifyLoanExists(bookId, userId) {
  var bookIdRef = sutBookIdRef(bookId);
  var userIdRef = sutUserIdRef(userId);
  userId = asInteger(userId);

  var invalidCases = [
    { label: "bad userId", parameters: { userId: "bad-user-id", bookId: asString(bookIdRef) } },
    { label: "bad bookId", parameters: { userId: asString(userId), bookId: "bad-book-id" } },
    { label: "zero userId", parameters: { userId: "0", bookId: asString(bookIdRef) } },
    { label: "zero bookId", parameters: { userId: asString(userId), bookId: "0" } },
    { label: "negative userId", parameters: { userId: "-1", bookId: asString(bookIdRef) } },
    { label: "negative bookId", parameters: { userId: asString(userId), bookId: "-1" } }
  ];

  var validParameters = { userId: userIdRef, bookId: bookIdRef, description: verifyExistsDescription("Loan", userId + "/" + bookId, "loans") };
  var variants = [{ name: "readLoans (valid): " + userId + "/" + bookIdRef, parameters: validParameters, expectedResponseCodes: [200], valid: true }];
  variants = variants.concat(invalidCases.map(function (c) {
    var eventName = "Req: readLoans (invalid - " + c.label + "): " + userId + "/" + bookIdRef;
    var parameters = { userId: c.parameters.userId, bookId: c.parameters.bookId, description: eventName };
    return { name: eventName, parameters: parameters, expectedResponseCodes: [400] };
  }));

  while (true) {
    var response = requestOneOfDirect("get", "/loans", variants);
    if (response.data.model.valid === true) return response;
  }
}

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
  var bookIdRef = sutBookIdRef(bookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/loans/" + sutUserIdRef(userId) + "/" + bookIdRef;
  var description = verifyRejectedDescription("Loan", userId + "/" + bookId, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
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

function createUser(id, name) {
  id = asInteger(id);
  name = asString(name);

  var reqDescription = createDescription("User", id);
  var parameters = { description: reqDescription, id: id };
  var callback = rememberCreatedId("USER", id);
  var variants = [
    { name: "createUser (valid-standard): " + id, body: { name: name }, expectedResponseCodes: [201], parameters: parameters, callback: callback, valid: true },
    { name: "createUser (valid-spaced-name): " + id, body: { name: " " + name }, expectedResponseCodes: [201], parameters: parameters, callback: callback, valid: true },
    // Positive counterpart to the "no unexpected-field case" note in
    // tryToCreateUserWithBadParametersAndExpectError below: locks in that an unrecognized field
    // is accepted (silently ignored), not merely untested.
    { name: "createUser (valid-unexpected-field): " + id, body: { name: name, unexpected: "value" }, expectedResponseCodes: [201], parameters: parameters, callback: callback, valid: true }
  ];

  var invalidCases = [
    // Claude: "missing name" and "missing all required fields" are the same request ({}).
    { label: "missing name", body: {} },
    { label: "missing all required fields", body: {} },
    { label: "name has wrong type", body: { "name": 12345 } },
    { label: "name is null", body: { "name": null } },
    { label: "name is empty", body: { "name": "" } }
  ];

  variants = variants.concat(invalidCases.map(function(c) {
    return { name: "createUser (invalid - " + c.label + "): " + id, body: c.body, expectedResponseCodes: [400] };
  }));

  while (true) {
    var response = requestOneOfDirect("post", "/users", variants);
    if (response.data.model.valid === true) return response;
  }
}

function tryToCreateUserWithBadParametersAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/users";
  var reqDescription = verifyRejectedDescription("User", id, "create", "required parameters are missing or invalid");
  // No id-related or "unexpected field" cases: the SUT assigns the user's id itself and
  // silently ignores any other field (only name is read/validated - see sut.py's POST /users),
  // so there is no rejectable invalid id left to fuzz. See the identical notes on createBook.
  var cases = [
    { name: "missing name", body: {} },
    { name: "name has wrong type", body: { "name": 12345 } },
    { name: "name is null", body: { "name": null } },
    { name: "name is empty", body: { "name": "" } }
  ];
  var variants = cases.map(function (c) {
    return { body: c.body, expectedResponseCodes: [expectedCode], description: reqDescription + " - " + c.name };
  });
  requestOneOfDirect("post", url, variants);
}

function deleteUser(id) {
  id = asInteger(id);

  var variants = [
    { name: "deleteUser (valid): " + id, url: "/users/" + sutUserIdRef(id), expectedResponseCodes: [200], parameters: { description: deleteDescription("User", id), id: id }, valid: true },
    { name: "deleteUser (invalid - bad-id): " + id, url: "/users/bad-id", expectedResponseCodes: [400] },
    { name: "deleteUser (invalid - zero): " + id, url: "/users/0", expectedResponseCodes: [400] },
    { name: "deleteUser (invalid - negative): " + id, url: "/users/-1", expectedResponseCodes: [400] }
  ];
  while (true) {
    var response = requestOneOfDirect("delete", null, variants);
    if (response.data.model.valid === true) return response;
  }
}

// verifyUserDeleteFuzz (static per-field fuzz cases) was replaced by the dynamic valid/invalid
// loop inside createUser/deleteUser above. verifyUserReadFuzz was removed and not replaced: the
// /users search endpoint accepts any `q` value and always answers 200, so there is no rejectable
// invalid variant to fuzz for user reads (see the note above verifyMissingEntityReadIsRejected).

function tryToUpdateUserAndExpectError(id, body, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
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
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/users/" + sutUserIdRef(id);
  var description = verifyRejectedDescription("User", id, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
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

function createHold(bookId, id, userId, expectedCode, description, bookIdMissing, userIdMissing) {
  bookId = asInteger(bookId);
  id = asInteger(id);
  userId = asInteger(userId);

  var reqDescription = description || (createDescription("Hold", id) + " for User " + userId + " and Book " + bookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 201 : asInteger(expectedCode);
  var parameters = { description: reqDescription, id: id, userId: userId, bookId: bookId };
  // bookId in each valid body is a late-bound "@{...}" placeholder (see the sutIdRef doc comment
  // above), substituted with the SUT id by Provengo's runtime only once the request actually
  // fires. bookIdMissing/userIdMissing are true when the caller is deliberately exercising a
  // nonexistent foreign key (see tryToCreateHoldWithNonexistent{User,Book,UserAndBook}AndExpectError):
  // that id was never created and has no RTV entry.
  var variants = [
    { name: "createHold (valid-standard): " + id, body: { userId: sutUserIdRef(userId, userIdMissing), bookId: sutBookIdRef(bookId, bookIdMissing) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 ? rememberCreatedId("HOLD", id) : undefined, valid: true },
    { name: "createHold (valid-swapped-order): " + id, body: { bookId: sutBookIdRef(bookId, bookIdMissing), userId: sutUserIdRef(userId, userIdMissing) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 ? rememberCreatedId("HOLD", id) : undefined, valid: true },
    // Positive counterpart to the "no unexpected-field case" note in
    // tryToCreateHoldWithBadParametersAndExpectError below: locks in that an unrecognized field
    // is accepted (silently ignored), not merely untested.
    { name: "createHold (valid-unexpected-field): " + id, body: { userId: sutUserIdRef(userId, userIdMissing), bookId: sutBookIdRef(bookId, bookIdMissing), unexpected: "value" }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 ? rememberCreatedId("HOLD", id) : undefined, valid: true }
  ];

  // No id-related cases: the SUT assigns the hold's id itself (see sut.py's POST /holds,
  // which reads only userId/bookId from the payload) and silently ignores any client-supplied
  // "id" field, so there is no rejectable invalid id left to fuzz - matching createBook above.
  var invalidCases = [
    { name: "missing bookId", body: { "userId": userId } },
    { name: "missing userId", body: { "bookId": bookId } },
    { name: "missing all required fields", body: {} },
    { name: "userId has wrong type", body: { "userId": "bad-user-id", "bookId": bookId } },
    { name: "bookId has wrong type", body: { "userId": userId, "bookId": "bad-book-id" } },
    { name: "multiple wrong types", body: { "userId": false, "bookId": "bad-book-id" } },
    { name: "userId is null", body: { "userId": null, "bookId": bookId } },
    { name: "bookId is null", body: { "userId": userId, "bookId": null } },
    { name: "userId is zero", body: { "userId": 0, "bookId": bookId } },
    { name: "bookId is zero", body: { "userId": userId, "bookId": 0 } },
    { name: "userId is negative", body: { "userId": -userId, "bookId": bookId } },
    { name: "bookId is negative", body: { "userId": userId, "bookId": -bookId } },
    { name: "userId is object", body: { "userId": { "val": userId }, "bookId": bookId } },
    { name: "bookId is object", body: { "userId": userId, "bookId": { "val": bookId } } }
  ];

  variants = variants.concat(invalidCases.map(function(c) {
    return { name: "createHold (invalid - " + c.name + "): " + id, body: c.body, expectedResponseCodes: [400] };
  }));

  while (true) {
    var response = requestOneOfDirect("post", "/holds", variants);
    if (response.data.model.valid === true) return response;
  }
}

// missingBookId/userId/missingUserId were never created (see generateMissingId()), so they have no
// RTV entry; createHold is told which argument(s) to send as a plain id instead of resolving one.
function tryToCreateHoldWithNonexistentUserAndExpectError(bookId, id, missingUserId, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createHold(bookId, id, missingUserId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the operation is not allowed in this state"), false, true);
}

function tryToCreateHoldWithNonexistentBookAndExpectError(missingBookId, id, userId, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createHold(missingBookId, id, userId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the operation is not allowed in this state"), true, false);
}

function tryToCreateHoldWithNonexistentUserAndBookAndExpectError(missingBookId, id, missingUserId, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createHold(missingBookId, id, missingUserId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the operation is not allowed in this state"), true, true);
}

function tryToCreateHoldWithBadParametersAndExpectError(id, userId, expectedCode) {
  id = asInteger(id);
  userId = asInteger(userId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/holds";
  var reqDescription = verifyRejectedDescription("Hold", id, "create", "required parameters are missing or invalid");
  // No id-related cases: the SUT assigns the hold's id itself and silently ignores any
  // client-supplied "id" field (see createHold above), so there is no rejectable invalid id left
  // to fuzz, and no reason to send one on the wire.
  var cases = [
    { name: "missing bookId", body: { "userId": userId } },
    { name: "missing userId", body: { "bookId": userId } },
    { name: "missing all required fields", body: {} },
    { name: "userId has wrong type", body: { "userId": "bad-user-id", "bookId": userId } },
    { name: "bookId has wrong type", body: { "userId": userId, "bookId": "bad-book-id" } },
    { name: "multiple wrong types", body: { "userId": false, "bookId": "bad-book-id" } },
    { name: "userId is null", body: { "userId": null, "bookId": userId } },
    { name: "bookId is null", body: { "userId": userId, "bookId": null } },
    { name: "userId is zero", body: { "userId": 0, "bookId": userId } },
    { name: "bookId is zero", body: { "userId": userId, "bookId": 0 } },
    { name: "userId is negative", body: { "userId": -userId, "bookId": userId } },
    { name: "bookId is negative", body: { "userId": userId, "bookId": -userId } }
    // No "unexpected field" case: the SUT ignores extra fields on this endpoint (only
    // userId/bookId are read/validated - see sut.py's POST /holds), so a request with one
    // succeeds rather than being rejected. See the identical note on createBook.
  ];
  var variants = cases.map(function (c) {
    return { body: c.body, expectedResponseCodes: [expectedCode], description: reqDescription + " - " + c.name };
  });
  requestOneOfDirect("post", url, variants);
}

function deleteHold(id, expectedCode, userId, bookId) {
  id = asInteger(id);
  // Claude: the one caller passes (id, userId, bookId), and this shuffles the arguments to fit an
  // (id, expectedCode, userId, bookId) signature. Just make the signature (id, userId, bookId)?
  if (bookId === undefined && userId !== undefined && userId !== null) {
    bookId = userId;
    userId = expectedCode;
    expectedCode = null;
  }
  userId = userId === undefined || userId === null ? null : asInteger(userId);
  bookId = bookId === undefined || bookId === null ? null : asInteger(bookId);

  var reqDescription = deleteDescription("Hold", id, userId === null || bookId === null ? "" : "for User " + userId + " and Book " + bookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 200 : asInteger(expectedCode);
  var parameters = { description: reqDescription, id: id };
  if (userId !== null) parameters.userId = userId;
  if (bookId !== null) parameters.bookId = bookId;
  var variants = [
    { name: "deleteHold (valid): " + id, url: "/holds/" + sutHoldIdRef(id), expectedResponseCodes: [expectedCode], parameters: parameters, valid: true },
    { name: "deleteHold (invalid - bad-id): " + id, url: "/holds/bad-id", expectedResponseCodes: [400] },
    { name: "deleteHold (invalid - zero): " + id, url: "/holds/0", expectedResponseCodes: [400] },
    { name: "deleteHold (invalid - negative): " + id, url: "/holds/-1", expectedResponseCodes: [400] }
  ];

  while (true) {
    var response = requestOneOfDirect("delete", null, variants);
    if (response.data.model.valid === true) return response;
  }
}

// verifyHoldDeleteFuzz (static per-field fuzz cases) was replaced by the dynamic valid/invalid
// loop inside createHold/deleteHold above. verifyHoldReadFuzz was removed and not replaced: the
// /holds search endpoint accepts any `q` value and always answers 200, so there is no rejectable
// invalid variant to fuzz for hold reads (see the note above verifyMissingEntityReadIsRejected).

// Claude: userId/bookId are normalized and then never used.
function tryToUpdateHoldAndExpectError(id, userId, bookId, body, expectedCode) {
  id = asInteger(id);
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  tryToUpdateAndExpectError("Hold", id, "/holds/" + sutHoldIdRef(id), body, expectedCode);
}

function verifyHoldExists(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutHoldIdRef(id), description: verifyExistsDescription("Hold", id, "holds") });
}

function verifyHoldAbsentFromAllLists(id) {
  id = asInteger(id);
  return readSutList("/holds", { q: sutHoldIdRef(id), description: verifyAbsentDescription("Hold", id, "holds") });
}

function tryToDeleteHoldAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/holds/" + sutHoldIdRef(id);
  var description = verifyRejectedDescription("Hold", id, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
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
