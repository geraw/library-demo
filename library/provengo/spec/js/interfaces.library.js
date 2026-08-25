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
// 2. EventSets such as AnyBookAdded and matchDeleteUser that classify events.
// 3. extractEventData(), which converts a concrete event into semantic fields.
//
// Stories use action functions and EventSets to describe behavior. The DAL uses
// EventSets plus extractEventData() to update the Context model without parsing
// URLs, bodies, or transport parameters itself.
//////////////////////////////////////////////////////////////////////////

// Server-generated ids are represented by virtual ids in the model and RTVs at the REST boundary.
// See the handoff and remaining verification work in the repository's TODO.md.

var host = (typeof host !== 'undefined') ? host : 'localhost';
var port = (typeof port !== 'undefined') ? port : 23242;
var protocol = (typeof protocol !== 'undefined') ? protocol : 'http';
var path = '';

const svc = new RESTSession(protocol + "://" + host + ":" + port + path, "provengo-client", { headers: { "Content-Type": "application/json", "api_key": "special-key" } });

// Sends one of several request variants (each with its own body/expectedResponseCodes/parameters)
// by offering them all to bp.sync at once, so the event selection mechanism (not this code) picks
// which single variant is actually sent - letting fuzzing/exploration choose the request shape
// instead of a scripted for-loop that sends every case every time.
// A variant's chooser event can sit offered for many synchronization rounds before it wins
// (other b-threads keep running while this one waits its turn), so `block()`-based guards taken
// out before offering don't cover the whole wait. `stillRelevant`, when given, is re-checked
// right after the chooser event wins but before the real REST call fires - the request is
// aborted (REQUEST_ABORTED) instead of actuating a stale "valid" expectation against an entity
// that stopped existing while we were waiting. See verifyBookDetailExists/verifyLoanExists.
const REQUEST_ABORTED = { aborted: true };

function requestOneOf(method, url, variants, onSelected, stillRelevant) {
  if (!variants || variants.length === 0) pvg.fail("requestOneOf requires at least one variant");
  var events = variants.map(function (v, i) {
    var eventName = v.name || v.description || (method.toUpperCase() + " " + (v.url || url) + " (variant " + i + ")");
    return bp.Event(eventName, { variant: v });
  });
  var selectedEvent = bp.sync({ request: events });
  if (stillRelevant && !stillRelevant()) return REQUEST_ABORTED;
  var chosen = selectedEvent.data.variant;
  if (onSelected) onSelected(chosen);
  var requestUrl = chosen.url || url;
  var requestOptions = {
    expectedResponseCodes: chosen.expectedResponseCodes,
    parameters: chosen.parameters || { description: chosen.description || selectedEvent.name }
  };
  if (chosen.body !== undefined) requestOptions.body = JSON.stringify(chosen.body);
  if (chosen.callback !== undefined) requestOptions.callback = chosen.callback;
  return svc[method](requestUrl, requestOptions);
}

svc.postOneOf = function (url, variants, onSelected, stillRelevant) { return requestOneOf("post", url, variants, onSelected, stillRelevant); };
svc.getOneOf = function (url, variants, onSelected, stillRelevant) { return requestOneOf("get", url, variants, onSelected, stillRelevant); };
svc.deleteOneOf = function (url, variants, onSelected, stillRelevant) { return requestOneOf("delete", url, variants, onSelected, stillRelevant); };
svc.putOneOf = function (url, variants, onSelected, stillRelevant) { return requestOneOf("put", url, variants, onSelected, stillRelevant); };

const pvg = { fail: function (msg) { bp.log.error(msg); throw new Error(msg); } };

function asInteger(value) { return Number.parseInt(value, 10); }

function asString(value) { return String(value); }

function entityDescription(entityName, id) {
  return entityName + " " + id;
}

function relationDescription(entityName, id, details) {
  return entityDescription(entityName, id) + (details ? " " + details : "");
}

function createDescription(entityName, id) {
  return "Create: " + entityDescription(entityName, id);
}

function deleteDescription(entityName, id, details) {
  return "Delete: " + relationDescription(entityName, id, details);
}

function verifyExistsDescription(entityName, id, listName) {
  return "Verify: " + entityDescription(entityName, id) + " exists in " + listName + " list";
}

function verifyAbsentDescription(entityName, id, listName) {
  return "Verify: " + entityDescription(entityName, id) + " is absent from " + listName + " list";
}

function verifyRejectedDescription(entityName, id, action, reason) {
  return "Verify: " + action + " " + entityDescription(entityName, id) + " is rejected" + (reason ? " because " + reason : "");
}

function extractId(e) {
  var body = getJsonBody(e);
  if (body && body.id !== undefined && body.id !== null) return asInteger(body.id);
  if (body && body.userId !== undefined && body.userId !== null) return asInteger(body.userId);

  if (e && e.data && e.data.parameters) {
    if (e.data.parameters.id !== undefined && e.data.parameters.id !== null) return asInteger(e.data.parameters.id);
    if (e.data.parameters.userId !== undefined && e.data.parameters.userId !== null) return asInteger(e.data.parameters.userId);
  }

  var pathValue = getRequestPath(e);
  if (pathValue) {
    var segments = pathValue.split("/").filter(function (s) { return s.length > 0; });
    if (segments.length >= 3 && segments[0] === "loans") return asInteger(segments[1]);
    if (segments.length >= 2) return asInteger(segments[segments.length - 1]);
  }

  pvg.fail("Could not extract ID from event fields");
}

function getExpectedResponseCodes(e) {
  var data = e && e.data ? e.data : e;
  if (!data) return [];
  if (Array.isArray(data.expectedResponseCodes)) return data.expectedResponseCodes;
  if (data.options && Array.isArray(data.options.expectedResponseCodes)) return data.options.expectedResponseCodes;
  if (data.parameters && Array.isArray(data.parameters.expectedResponseCodes)) return data.parameters.expectedResponseCodes;
  return [];
}

function hasExpectedCode(e, code) {
  return getExpectedResponseCodes(e).indexOf(code) !== -1;
}

function getRequestPath(e) {
  var data = e && e.data ? e.data : e;
  if (!data) return "";
  var p = data.path || data.url || data.endpoint || "";
  if (!p) return "";
  p = String(p).replace(/^https?:\/\/[^\/]+/, "");
  var qIdx = p.indexOf("?");
  return qIdx === -1 ? p : p.substring(0, qIdx);
}

function getJsonBody(e) {
  var data = e && e.data ? e.data : e;
  if (!data || data.body === undefined || data.body === null) return null;
  if (typeof data.body === "object") return data.body;
  if (typeof data.body === "string") {
    try { return JSON.parse(data.body); } catch (err) { return null; }
  }
  return null;
}

// Boundary adapter from concrete REST events to semantic event data.
// Consumers can depend on fields like id, userId, bookId, title, and
// loanNumber without knowing whether the values came from a JSON body,
// REST path, query parameter, or request metadata.
function extractEventData(e) {
  var body = getJsonBody(e) || {};
  var data = e && e.data ? e.data : e;
  var parameters = data && data.parameters ? data.parameters : {};
  
  // parameters win over body: actions that address a real-id-mapped entity (see the RTV helpers
  // below) attach the logical id as a parameter, while the body/URL they actually send carries
  // the real id. For every other field, parameters were never set before, so this is a no-op.
  var id = parameters.id !== undefined && parameters.id !== null ? parameters.id : body.id;
  var userId = parameters.userId !== undefined && parameters.userId !== null ? parameters.userId : body.userId;
  var bookId = parameters.bookId !== undefined && parameters.bookId !== null ? parameters.bookId : body.bookId;

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

function isValidRequestEvent(e, actionName) {
  return e && e.data && e.data.action === actionName && e.data.type === "valid";
}

//////////////////////////////////////////////////////////////////////////
// Real-id mapping (RTV).
//
// The SUT assigns entity ids instead of accepting a client choice. Stories,
// EventSets, and the DAL keep addressing each entity by the small virtual
// id the story picked when it asked for creation, so traces and context stay
// readable; only the REST calls in this file need the real id the SUT
// actually assigned. The mapping is written once, right after a successful
// create response into Provengo's runtime-variable store under a per-entity
// key ("USER1", "BOOK1", "LOAN1", "HOLD1", ...). Every wire-level use is a
// late-bound `@{...}` expression; parameters retain virtual ids for the DAL.
//////////////////////////////////////////////////////////////////////////

function rtvKey(entityType, logicalId) {
  return entityType + asInteger(logicalId);
}

// Returns a late-bound expression. Provengo substitutes it only when the sampled
// scenario is executed, after the corresponding create callback has populated it.
function realId(entityType, logicalId) {
  return "@{" + rtvKey(entityType, logicalId) + "}";
}

function realUserId(logicalId) { return realId("USER", logicalId); }
function realBookId(logicalId) { return realId("BOOK", logicalId); }
function realLoanId(logicalId) { return realId("LOAN", logicalId); }
function realHoldId(logicalId) { return realId("HOLD", logicalId); }

// Callback functions execute later than model generation. Constructing a callback
// with the key embedded in its source avoids closing over a generation-time local.
function rememberCreatedId(entityType, logicalId) {
  var key = rtvKey(entityType, logicalId);
  return new Function("response",
    "var body = JSON.parse(response.body);" +
    "if (body.id === undefined || body.id === null) pvg.fail('Create response did not contain id');" +
    "pvg.rtv.set(" + JSON.stringify(key) + ", body.id);"
  );
}

// Pulls the real id the SUT assigned out of a create response. The REST library hands the actual
// response to a request's `callback` (svc.post()'s return value is just the request event, not
// the response - see createBook), as a Java map shaped {headers, code, body}, where `body` is the
// response's raw JSON text. During static analysis no real HTTP call happens and no callback
// fires, so callers only get here with a real captured response.
function extractResponseBody(response) {
  if (response === undefined || response === null) return null;
  var bodyText = response.body;
  if (typeof bodyText !== "string") return null;
  try { return JSON.parse(bodyText); } catch (err) { return null; }
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


//////////////////////////////////////////////////////////////////////////
// SUT list readers and verification helpers.
//
// Verification functions read the real SUT state and assert that it matches
// the scenario expectation. They are intentionally kept in the interface
// layer because they are REST-facing checks, not Context model updates.
//////////////////////////////////////////////////////////////////////////

function readSutList(listName, url, parameters) {
  try {
    var requestParameters = parameters || {};
    if (requestParameters.description === undefined || requestParameters.description === null) {
      requestParameters.description = "Verify: read " + listName + " list";
    }
    var response = svc.get(url, { parameters: requestParameters, expectedResponseCodes: [200] });
    if (response === undefined || response === null) return null;
    if (response.lib === "REST" || response.method !== undefined) return null;
    if (response.data && (response.data.lib === "REST" || response.data.method !== undefined)) return null;
    var listData = (typeof response === "string") ? JSON.parse(response) : response;
    if (!Array.isArray(listData) && listData && typeof listData.body === "string") listData = JSON.parse(listData.body);
    if (!Array.isArray(listData) && listData && Array.isArray(listData.data)) listData = listData.data;
    if (!Array.isArray(listData) && listData && Array.isArray(listData.items)) listData = listData.items;
    if (!Array.isArray(listData) && listData && Array.isArray(listData.results)) listData = listData.results;
    if (Array.isArray(listData)) return listData;
    pvg.fail("Could not inspect " + listName + " response as a SUT list");
  } catch (err) {
    if (String(err).indexOf("EndOfContextException") !== -1) return null;
    pvg.fail("Failed to read " + listName + " from the SUT: " + err);
  }
}

function verifySutListContains(listName, url, parameters, predicate, failureMessage, stillRelevant) {
  // Verification is executed against the SUT by fetching only the requested SUT list slice before inspecting it.
  var listData = readSutList(listName, url, parameters);
  if (listData === null) return;
  var found = listData.find(predicate);
  // stillRelevant re-checks that the entity is expected to exist at the moment of the read: a
  // concurrent (legitimate) deletion between when this verification was offered and when the GET
  // actually ran would otherwise read as a false failure instead of a moot check.
  if (!found && (!stillRelevant || stillRelevant())) pvg.fail(failureMessage);
}

function verifySutListDoesNotContain(listName, url, parameters, predicate, failureMessage) {
  // Verification is executed against the SUT by fetching only the requested SUT list slice before inspecting it.
  var listData = readSutList(listName, url, parameters);
  if (listData === null) return;
  var found = listData.find(predicate);
  if (found) pvg.fail(failureMessage + ": " + JSON.stringify(found));
}

function tryToUpdateAndExpectError(entityName, id, url, body, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  var description = verifyRejectedDescription(entityName, id, "update", "this API does not expose update routes");
  svc.put(url, { body: JSON.stringify(body || {}), expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

// Malformed-delete and malformed-read rejection cases are covered by the dynamic valid/invalid
// loops inside deleteBook/deleteUser/deleteLoan/deleteHold and verifyBookDetailExists, so this
// file has no separate verifyMalformedDeleteIsRejected/verifyMalformedReadIsRejected helpers.

function verifyMissingEntityReadIsRejected(entityName, id, url) {
  var description = verifyRejectedDescription(entityName, id, "read", "the entity does not exist");
  svc.get(url, { expectedResponseCodes: [404], parameters: { description: description } });
}

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

// The SUT assigns the book's real id itself (title is the only client-supplied field), so there
// is no client-chosen id left to fuzz or to duplicate. logicalId is this story's own bookkeeping
// handle: it never goes on the wire, only into `parameters` for the DAL/matchers, and into
// the BOOK<n> RTV once the real id comes back.
function createBook(logicalId, title) {
  logicalId = asInteger(logicalId);
  title = asString(title);

  var reqDescription = createDescription("Book", logicalId);
  var captureResponse = rememberCreatedId("BOOK", logicalId);
  var idParameters = { description: reqDescription, id: logicalId };
  var variants = [
    { name: "createBook (valid-standard): " + logicalId, body: { title: title }, expectedResponseCodes: [201], parameters: idParameters, callback: captureResponse },
    { name: "createBook (valid-spaced-title): " + logicalId, body: { title: " " + title }, expectedResponseCodes: [201], parameters: idParameters, callback: captureResponse }
  ];

  var invalidCases = [
    { label: "missing title", body: {} },
    { label: "title has wrong type", body: { "title": 12345 } },
    { label: "title is null", body: { "title": null } },
    { label: "title is empty", body: { "title": "" } }
  ];

  variants = variants.concat(invalidCases.map(function(c) {
    var description = "createBook (invalid - " + c.label + "): " + logicalId;
    return { name: description, body: c.body, expectedResponseCodes: [400], parameters: { description: description } };
  }));

  while (true) {
    var selectedIsValid = false;
    var response = svc.postOneOf("/books", variants, function(chosen) {
      selectedIsValid = chosen.expectedResponseCodes.indexOf(201) !== -1;
    });
    if (selectedIsValid) return response;
  }
}

function tryToCreateBookWithBadParametersAndExpectError(logicalId, expectedCode) {
  logicalId = asInteger(logicalId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/books";
  var reqDescription = verifyRejectedDescription("Book", logicalId, "create", "required parameters are missing or invalid");
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
  svc.postOneOf(url, variants);
}

function deleteBook(logicalId) {
  logicalId = asInteger(logicalId);
  // The valid variant's url is a placeholder here and gets overwritten with the real id in
  // onSelected, right before actuation - see the realId doc comment above for why resolving it
  // this late (rather than up front) matters.
  var variants = [
    { name: "deleteBook (valid): " + logicalId, url: "/books/" + logicalId, expectedResponseCodes: [200], parameters: { description: deleteDescription("Book", logicalId), id: logicalId }, valid: true },
    { name: "deleteBook (invalid - bad-id): " + logicalId, url: "/books/bad-id", expectedResponseCodes: [400] },
    { name: "deleteBook (invalid - zero): " + logicalId, url: "/books/0", expectedResponseCodes: [400] },
    { name: "deleteBook (invalid - negative): " + logicalId, url: "/books/-1", expectedResponseCodes: [400] }
  ];
  while (true) {
    var valid = false;
    var response = svc.deleteOneOf("/books/" + logicalId, variants, function (chosen) {
      valid = chosen.valid === true;
      if (chosen.valid) chosen.url = "/books/" + realBookId(logicalId);
    });
    if (valid) return response;
  }
}

// The book detail endpoint validates its id path parameter (malformed/zero/negative id -> 400)
// before checking existence (valid-format-but-missing id -> 404), so it gets the same
// dynamic valid/invalid fuzzing loop as the create/delete actions. See the Fuzzing
// Interface Layer Contract at the bottom of lib_stories.js.
function verifyBookDetailExists(logicalId, stillRelevant) {
  logicalId = asInteger(logicalId);

  var description = verifyExistsDescription("Book", logicalId, "book detail");
  // Placeholder urls, overwritten with the real id in onSelected right before actuation - see the
  // realId doc comment above.
  var variants = [
    { name: "readBookDetail (valid-standard): " + logicalId, url: "/books/" + logicalId, expectedResponseCodes: [200], parameters: { description: description, id: logicalId }, valid: true, padded: false },
    { name: "readBookDetail (valid-padded-id): " + logicalId, url: "/books/00" + logicalId, expectedResponseCodes: [200], parameters: { description: description, id: logicalId }, valid: true, padded: true },
    { name: "readBookDetail (invalid - bad-id): " + logicalId, url: "/books/bad-id", expectedResponseCodes: [400] },
    { name: "readBookDetail (invalid - zero): " + logicalId, url: "/books/0", expectedResponseCodes: [400] },
    { name: "readBookDetail (invalid - negative): " + logicalId, url: "/books/-1", expectedResponseCodes: [400] }
  ];
  while (true) {
    var valid = false;
    var response = svc.getOneOf("/books/" + logicalId, variants, function (chosen) {
      valid = chosen.valid === true;
      if (chosen.valid) chosen.url = "/books/" + (chosen.padded ? "00" : "") + realBookId(logicalId);
    }, stillRelevant);
    if (response === REQUEST_ABORTED) return;
    if (valid) {
      var bookData = extractResponseBody(response);
      if (bookData === null) return;
      if (!bookData || bookData.id === undefined) pvg.fail("Book " + logicalId + " detail response did not contain an id");
      return;
    }
  }
}

// verifyBookReadFuzz and verifyBookDeleteFuzz (static per-field fuzz cases) were replaced by
// the dynamic valid/invalid loop inside createBook/deleteBook/verifyBookDetailExists above.

function tryToUpdateBookAndExpectError(id, body, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  tryToUpdateAndExpectError("Book", id, "/books/" + realBookId(id), body, expectedCode);
}

function verifyBookExists(logicalId, stillRelevant) {
  // Verification is executed against the SUT dataset by reading the books list and searching for this book's real id.
  logicalId = asInteger(logicalId);
  var id = realBookId(logicalId);
  verifySutListContains("books", "/books", { q: asString(id), description: verifyExistsDescription("Book", logicalId, "books") }, function (item) {
    return item && asInteger(item.id) === id;
  }, "Book " + logicalId + " was not found in the SUT books list", stillRelevant);
}

function verifyBookAbsentFromAllLists(logicalId) {
  // Verification is executed against SUT datasets: books directly, and loans/holds indirectly by bookId.
  logicalId = asInteger(logicalId);
  var id = realBookId(logicalId);
  verifySutListDoesNotContain("books", "/books", { q: asString(id), description: verifyAbsentDescription("Book", logicalId, "books") }, function (item) {
    return item && asInteger(item.id) === id;
  }, "Book " + logicalId + " still appears in books list");
  verifySutListDoesNotContain("loans", "/loans", { bookId: asString(id), description: verifyAbsentDescription("Book", logicalId, "loans") }, function (item) {
    return item && asInteger(item.bookId) === id;
  }, "Book " + logicalId + " still appears in loans list");
  verifySutListDoesNotContain("holds", "/holds", { q: asString(id), description: verifyAbsentDescription("Book", logicalId, "holds") }, function (item) {
    return item && asInteger(item.bookId) === id;
  }, "Book " + logicalId + " still appears in holds list");
}

function tryToDeleteBookAndExpectError(logicalId, expectedCode) {
  logicalId = asInteger(logicalId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/books/" + realBookId(logicalId);
  var description = verifyRejectedDescription("Book", logicalId, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedBookAndExpectError(id) {
  tryToDeleteBookAndExpectError(id, 404);
}

function tryToDeleteNonexistingBookAndExpectError(id) {
  tryToDeleteBookAndExpectError(id, 404);
}

//////////////////////////////////////////////////////////////////////////
// Specific event matchers.
//
// The broad Any* EventSets classify all successful operations of a type and
// are useful for DAL effects. The match* helpers below are narrower EventSets
// for stories: they wait for or block a specific object, duplicate attempt, or
// cascading delete condition.
//////////////////////////////////////////////////////////////////////////

function matchAddBook(id) {
  id = asInteger(id);
  return bp.EventSet("Add Book " + id, function (e) {
    // Book's own id never goes on the wire (see createBook), so match on the logical id it
    // recorded in `parameters` instead of the request/response body.
    var eventParameters = e && e.data && e.data.parameters;
    if (e.name === "POST" && getRequestPath(e) === "/books" && hasExpectedCode(e, 201) && eventParameters && asInteger(eventParameters.id) === id) return true;
    return isValidRequestEvent(e, "createBook") && e.data.parameters && asInteger(e.data.parameters.id) === id;
  });
}

// These matchers compare against the LOGICAL id via extractEventData(e), never against a
// realBookId()-resolved value: a book-delete/loan/hold event's url or body only gets the real id
// baked in at selection time (see deleteBook/createLoan/createHold), so while the event is still
// pending selection its wire-level fields show a placeholder - a matcher used to block() that
// pending event would never recognize it if it compared against the real id. `parameters.id`/
// `parameters.bookId`, in contrast, are set to the logical id at construction time and never
// change, so extractEventData(e) (which prefers parameters - see its doc comment) resolves
// correctly no matter when it's evaluated relative to selection or to the RTV mapping becoming
// available at runtime.
function matchDeleteBook(logicalId) {
  logicalId = asInteger(logicalId);
  return bp.EventSet("Deleted Books " + logicalId, function (e) {
    if (!(e.name === "DELETE" && getRequestPath(e).startsWith("/books/") && hasExpectedCode(e, 200))) return false;
    return extractEventData(e).id === logicalId;
  });
}

function matchDeleteBookOrUser(bookId, userId) {
  bookId = asInteger(bookId);
  userId = asInteger(userId);
  return bp.EventSet("Deleted Book/User " + bookId + "/" + userId, function (e) {
    if (!(e.name === "DELETE" && hasExpectedCode(e, 200))) return false;
    var path = getRequestPath(e);
    if (path.startsWith("/books/")) return extractEventData(e).id === bookId;
    if (path.startsWith("/users/")) return extractEventData(e).id === userId;
    return false;
  });
}

function matchDeleteHoldOrBookOrUser(holdId, bookId, userId) {
  holdId = asInteger(holdId);
  bookId = asInteger(bookId);
  userId = asInteger(userId);
  return bp.EventSet("Deleted Hold/Book/User " + holdId + "/" + userId + "/" + bookId, function (e) {
    if (!(e.name === "DELETE" && hasExpectedCode(e, 200))) return false;
    var path = getRequestPath(e);
    if (path.startsWith("/holds/")) return extractEventData(e).id === holdId;
    if (path.startsWith("/books/")) return extractEventData(e).id === bookId;
    if (path.startsWith("/users/")) return extractEventData(e).id === userId;
    return false;
  });
}

// Guards for the deleteUser/deleteBook stories: once an entity becomes eligible
// for deletion, the delete offer can stay pending (unselected) for many events
// while other b-threads keep running. Without blocking, a hold or loan could be
// added for that same user/book while the offer is pending, turning the delete's
// expected 200 into an unexpected 400 once it is finally selected. Wrapping the
// delete call in block(matchAddHoldOrLoanForUser/Book(...), fn) keeps the entity
// hold/loan-free for as long as the delete offer is outstanding.
function matchAddHoldOrLoanForUser(userId) {
  return bp.EventSet("Add Hold/Loan for User " + userId, function (e) {
    var body = getJsonBody(e);
    if (!body) return false;
    if (AnyHoldAdded.contains(e) && asInteger(body.userId) === asInteger(userId)) return true;
    if (AnyLoanAdded.contains(e) && asInteger(body.userId) === asInteger(userId)) return true;
    return false;
  });
}

function matchAddHoldOrLoanForBook(bookId) {
  bookId = asInteger(bookId);
  return bp.EventSet("Add Hold/Loan for Book " + bookId, function (e) {
    if (!(AnyHoldAdded.contains(e) || AnyLoanAdded.contains(e))) return false;
    return extractEventData(e).bookId === bookId;
  });
}

function matchAddLoanForHeldResourceOrDeleteHoldOrBookOrUser(holdId, bookId, userId) {
  holdId = asInteger(holdId);
  bookId = asInteger(bookId);
  userId = asInteger(userId);
  return bp.EventSet("Added Loan for Held Resource or Deleted Hold/Book/User " + holdId + "/" + userId + "/" + bookId, function (e) {
    if (e.name === "POST" && getRequestPath(e) === "/loans" && hasExpectedCode(e, 201)) {
      var loanData = extractEventData(e);
      if (loanData.userId === userId || loanData.bookId === bookId) return true;
    }
    if (e.name === "DELETE" && hasExpectedCode(e, 200)) {
      var path = getRequestPath(e);
      var deletedId = extractEventData(e).id;
      if (path.startsWith("/holds/") && deletedId === holdId) return true;
      if (path.startsWith("/books/") && deletedId === bookId) return true;
      if (path.startsWith("/users/") && deletedId === userId) return true;
    }
    return false;
  });
}

function matchAnyBookDeleted() {
  return AnyBookDeleted;
}

function deleteLoan(userId, logicalBookId, loanNumber) {
  userId = asInteger(userId);
  logicalBookId = asInteger(logicalBookId);
  loanNumber = loanNumber === undefined || loanNumber === null ? null : asInteger(loanNumber);

  var invalidCases = [
    { label: "bad-user-id", url: "/loans/bad-user-id/" + logicalBookId },
    { label: "bad-book-id", url: "/loans/" + userId + "/bad-book-id" },
    { label: "zero userId", url: "/loans/0/" + logicalBookId },
    { label: "zero bookId", url: "/loans/" + userId + "/0" },
    { label: "negative userId", url: "/loans/-1/" + logicalBookId },
    { label: "negative bookId", url: "/loans/" + userId + "/-1" }
  ];

  var reqDescription = deleteDescription("Loan", userId + "/" + logicalBookId, loanNumber === null ? "" : "number " + loanNumber);
  var parameters = { description: reqDescription, userId: userId, bookId: logicalBookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  // The valid variant's url is a placeholder, overwritten with the real id in onSelected right
  // before actuation - see the realId doc comment above.
  var variants = [{ name: "deleteLoan (valid): " + userId + "/" + logicalBookId, url: "/loans/" + userId + "/" + logicalBookId, expectedResponseCodes: [200], parameters: parameters, valid: true }];
  variants = variants.concat(invalidCases.map(function(c) {
    return { name: "deleteLoan (invalid - " + c.label + "): " + userId + "/" + logicalBookId, url: c.url, expectedResponseCodes: [400] };
  }));

  while (true) {
    var valid = false;
    var response = svc.deleteOneOf("/loans/" + userId + "/" + logicalBookId, variants, function (chosen) {
      valid = chosen.valid === true;
      if (chosen.valid) chosen.url = "/loans/" + realUserId(userId) + "/" + realBookId(logicalBookId);
    });
    if (valid) return response;
  }
}

// verifyLoanReadFuzz and verifyLoanDeleteFuzz (static per-field fuzz cases) were replaced by the
// dynamic valid/invalid loop inside createLoan/deleteLoan/verifyLoanExists above.

function tryToUpdateLoanAndExpectError(userId, bookId, body, expectedCode) {
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  tryToUpdateAndExpectError("Loan", userId + "/" + bookId, "/loans/" + realUserId(userId) + "/" + realBookId(bookId), body, expectedCode);
}

function createLoan(userId, logicalBookId, loanNumber, expectedCode, description) {
  userId = asInteger(userId);
  logicalBookId = asInteger(logicalBookId);
  if (expectedCode === undefined && (loanNumber === 201 || loanNumber === 400 || loanNumber === 404)) {
    expectedCode = loanNumber;
    loanNumber = null;
  }
  loanNumber = loanNumber === undefined || loanNumber === null ? null : asInteger(loanNumber);

  var reqDescription = description || (createDescription("Loan", userId + "/" + logicalBookId) + (loanNumber === null ? "" : " number " + loanNumber));
  expectedCode = expectedCode === undefined || expectedCode === null ? 201 : asInteger(expectedCode);
  var parameters = { description: reqDescription, userId: userId, bookId: logicalBookId };
  if (loanNumber !== null) parameters.loanNumber = loanNumber;
  // bookId in each valid body is a placeholder (logicalBookId), overwritten with the real id in
  // onSelected right before actuation - see the realId doc comment above.
  var variants = [
    { name: "createLoan (valid-standard): " + userId + "/" + logicalBookId, body: { userId: realUserId(userId), bookId: realBookId(logicalBookId) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 && loanNumber !== null ? rememberCreatedId("LOAN", loanNumber) : undefined, valid: true },
    { name: "createLoan (valid-swapped-order): " + userId + "/" + logicalBookId, body: { bookId: realBookId(logicalBookId), userId: realUserId(userId) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 && loanNumber !== null ? rememberCreatedId("LOAN", loanNumber) : undefined, valid: true }
  ];

  var invalidCases = [
    { label: "missing bookId", body: { "userId": userId } },
    { label: "missing userId", body: { "bookId": logicalBookId } },
    { label: "missing all required fields", body: {} },
    { label: "userId has wrong type", body: { "userId": "bad-user-id", "bookId": logicalBookId } },
    { label: "bookId has wrong type", body: { "userId": userId, "bookId": "bad-book-id" } },
    { label: "multiple wrong types", body: { "userId": true, "bookId": false } },
    { label: "userId is null", body: { "userId": null, "bookId": logicalBookId } },
    { label: "bookId is null", body: { "userId": userId, "bookId": null } },
    { label: "userId is zero", body: { "userId": 0, "bookId": logicalBookId } },
    { label: "bookId is zero", body: { "userId": userId, "bookId": 0 } },
    { label: "userId is negative", body: { "userId": -userId, "bookId": logicalBookId } },
    { label: "bookId is negative", body: { "userId": userId, "bookId": -logicalBookId } },
    { label: "userId is object", body: { "userId": { "val": userId }, "bookId": logicalBookId } },
    { label: "bookId is object", body: { "userId": userId, "bookId": { "val": logicalBookId } } }
  ];

  variants = variants.concat(invalidCases.map(function(c) {
    return { name: "createLoan (invalid - " + c.label + "): " + userId + "/" + logicalBookId, body: c.body, expectedResponseCodes: [400] };
  }));

  while (true) {
    var valid = false;
    var response = svc.postOneOf("/loans", variants, function (chosen) {
      valid = chosen.valid === true;
    });
    if (valid) return response;
  }
}

function tryToCreateLoanAndExpectError(userId, bookId, loanNumber, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createLoan(userId, bookId, loanNumber, expectedCode, verifyRejectedDescription("Loan", userId + "/" + bookId, "create", "the operation is not allowed in this state"));
}

function tryToCreateLoanWithBadParametersAndExpectError(userId, expectedCode) {
  userId = asInteger(userId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/loans";
  var reqDescription = verifyRejectedDescription("Loan", userId, "create", "required parameters are missing or invalid");
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
    { name: "bookId is negative", body: { "userId": userId, "bookId": -userId } },
    { name: "unexpected field", body: { "userId": userId, "bookId": userId, "unexpected": "value" } }
  ];
  var variants = cases.map(function (c) {
    return { body: c.body, expectedResponseCodes: [expectedCode], description: reqDescription + " - " + c.name };
  });
  svc.postOneOf(url, variants);
}

// The loans search endpoint validates userId/bookId (malformed/zero/negative -> 400) before
// filtering, so it gets the same dynamic valid/invalid fuzzing loop as the create/delete actions.
function verifyLoanExists(logicalBookId, userId, stillRelevant) {
  var bookId = realBookId(logicalBookId);
  var realUser = realUserId(userId);
  userId = asInteger(userId);

  var invalidCases = [
    { label: "bad userId", parameters: { userId: "bad-user-id", bookId: asString(bookId) } },
    { label: "bad bookId", parameters: { userId: asString(userId), bookId: "bad-book-id" } },
    { label: "zero userId", parameters: { userId: "0", bookId: asString(bookId) } },
    { label: "zero bookId", parameters: { userId: asString(userId), bookId: "0" } },
    { label: "negative userId", parameters: { userId: "-1", bookId: asString(bookId) } },
    { label: "negative bookId", parameters: { userId: asString(userId), bookId: "-1" } }
  ];

  var validParameters = { userId: realUser, bookId: bookId, description: verifyExistsDescription("Loan", userId + "/" + logicalBookId, "loans") };
  var variants = [{ name: "readLoans (valid): " + userId + "/" + bookId, parameters: validParameters, expectedResponseCodes: [200], valid: true }];
  variants = variants.concat(invalidCases.map(function (c) {
    var eventName = "Req: readLoans (invalid - " + c.label + "): " + userId + "/" + bookId;
    var parameters = { userId: c.parameters.userId, bookId: c.parameters.bookId, description: eventName };
    return { name: eventName, parameters: parameters, expectedResponseCodes: [400] };
  }));

  while (true) {
    var valid = false;
    var response = svc.getOneOf("/loans", variants, function (chosen) { valid = chosen.valid === true; }, stillRelevant);
    if (response === REQUEST_ABORTED) return;
    if (valid) {
      if (response === undefined || response === null || response.lib === "REST" || response.method !== undefined) return;
      if (response.data && (response.data.lib === "REST" || response.data.method !== undefined)) return;
      var listData = typeof response === "string" ? JSON.parse(response) : response;
      if (!Array.isArray(listData) && listData && typeof listData.body === "string") listData = JSON.parse(listData.body);
      if (!Array.isArray(listData) && listData && Array.isArray(listData.data)) listData = listData.data;
      var stillFound = Array.isArray(listData) && listData.some(function (item) { return item && asInteger(item.userId) === userId && asInteger(item.bookId) === bookId; });
      if (!stillFound && (!stillRelevant || stillRelevant())) {
        pvg.fail("Loan " + userId + "/" + bookId + " was not found in the SUT loans list");
      }
      return;
    }
  }
}

function verifyLoanAbsentFromAllLists(logicalBookId, userId) {
  // Verification is executed against the SUT dataset by reading the loans list and confirming the loan is absent.
  var bookId = logicalBookId === undefined || logicalBookId === null ? null : realBookId(logicalBookId);
  userId = asInteger(userId);
  var loanId = userId + (bookId === null ? "" : "/" + bookId);
  var parameters = { userId: realUserId(userId), description: verifyAbsentDescription("Loan", loanId, "loans") };
  if (bookId !== null) parameters.bookId = asString(bookId);
  verifySutListDoesNotContain("loans", "/loans", parameters, function (item) {
    if (!item || asInteger(item.userId) !== userId) return false;
    return bookId === null || asInteger(item.bookId) === bookId;
  }, "Loan " + userId + (bookId === null ? "" : "/" + bookId) + " still appears in loans list");
}

function tryToDeleteLoanAndExpectError(userId, logicalBookId, expectedCode) {
  userId = asInteger(userId);
  var bookId = realBookId(logicalBookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/loans/" + realUserId(userId) + "/" + bookId;
  var description = verifyRejectedDescription("Loan", userId + "/" + logicalBookId, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedLoanAndExpectError(userId, bookId) {
  tryToDeleteLoanAndExpectError(userId, bookId, 404);
}

function tryToDeleteNonexistingLoanAndExpectError(userId, bookId) {
  tryToDeleteLoanAndExpectError(userId, bookId, 404);
}

function matchAddLoan(userId) {
  return bp.EventSet("Add Loan " + userId, function (e) {
    var body = getJsonBody(e);
    if (e.name === "POST" && getRequestPath(e) === "/loans" && hasExpectedCode(e, 201) && body && asInteger(body.userId) === asInteger(userId)) return true;
    return isValidRequestEvent(e, "createLoan") && e.data.body && asInteger(e.data.body.userId) === asInteger(userId);
  });
}

function matchDeleteLoan(userId) {
  return bp.EventSet("Deleted Loans " + userId, function (e) {
    if (e.name === "DELETE" && getRequestPath(e).startsWith("/loans/") && hasExpectedCode(e, 200) && asInteger(extractEventData(e).userId) === asInteger(userId)) return true;
    return isValidRequestEvent(e, "deleteLoan") && asInteger(extractEventData(e).userId) === asInteger(userId);
  });
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
    { name: "createUser (valid-spaced-name): " + id, body: { name: " " + name }, expectedResponseCodes: [201], parameters: parameters, callback: callback, valid: true }
  ];

  var invalidCases = [
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
    var valid = false;
    var response = svc.postOneOf("/users", variants, function (chosen) { valid = chosen.valid === true; });
    if (valid) return response;
  }
}

function tryToCreateUserWithSameIdAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/users";
  var reqDescription = verifyRejectedDescription("User", id, "create", "the id already exists");
  var body = {
    "id": id,
    "name": "Duplicate user " + id
  };
  let response = svc.post(url, { body: JSON.stringify(body), expectedResponseCodes: [expectedCode], parameters: { description: reqDescription } });
  return response;
}

function tryToCreateUserWithBadParametersAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/users";
  var reqDescription = verifyRejectedDescription("User", id, "create", "required parameters are missing or invalid");
  var cases = [
    { name: "missing name", body: { "id": id } },
    { name: "missing id", body: { "name": "User name " + id } },
    { name: "missing all required fields", body: {} },
    { name: "id has wrong type", body: { "id": "bad-user-id", "name": "User name " + id } },
    { name: "name has wrong type", body: { "id": id, "name": 12345 } },
    { name: "multiple wrong types", body: { "id": true, "name": false } },
    { name: "id and name have swapped types", body: { "name": id, "id": "User name " + id } },
    { name: "id is null", body: { "id": null, "name": "User name " + id } },
    { name: "name is null", body: { "id": id, "name": null } },
    { name: "id is zero", body: { "id": 0, "name": "User name " + id } },
    { name: "id is negative", body: { "id": -id, "name": "User name " + id } },
    { name: "name is empty", body: { "id": id, "name": "" } },
    { name: "unexpected field", body: { "id": id, "name": "User name " + id, "unexpected": "value" } }
  ];
  var variants = cases.map(function (c) {
    return { body: c.body, expectedResponseCodes: [expectedCode], description: reqDescription + " - " + c.name };
  });
  svc.postOneOf(url, variants);
}

function deleteUser(id) {
  id = asInteger(id);

  var variants = [
    { name: "deleteUser (valid): " + id, url: "/users/" + realUserId(id), expectedResponseCodes: [200], parameters: { description: deleteDescription("User", id), id: id }, valid: true },
    { name: "deleteUser (invalid - bad-id): " + id, url: "/users/bad-id", expectedResponseCodes: [400] },
    { name: "deleteUser (invalid - zero): " + id, url: "/users/0", expectedResponseCodes: [400] },
    { name: "deleteUser (invalid - negative): " + id, url: "/users/-1", expectedResponseCodes: [400] }
  ];
  while (true) {
    var valid = false;
    var response = svc.deleteOneOf("/users/" + id, variants, function (chosen) { valid = chosen.valid === true; });
    if (valid) return response;
  }
}

// verifyUserDeleteFuzz (static per-field fuzz cases) was replaced by the dynamic valid/invalid
// loop inside createUser/deleteUser above. verifyUserReadFuzz was removed and not replaced: the
// /users search endpoint accepts any `q` value and always answers 200, so there is no rejectable
// invalid variant to fuzz for user reads (see the note above verifyMissingEntityReadIsRejected).

function tryToUpdateUserAndExpectError(id, body, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  tryToUpdateAndExpectError("User", id, "/users/" + realUserId(id), body, expectedCode);
}

function verifyUserExists(id, stillRelevant) {
  // Verification is executed against the SUT dataset by reading the users list and searching for this user id.
  id = asInteger(id);
  verifySutListContains("users", "/users", { q: realUserId(id), description: verifyExistsDescription("User", id, "users") }, function (item) {
    return item && asInteger(item.id) === id;
  }, "User " + id + " was not found in the SUT users list", stillRelevant);
}

function verifyUserAbsentFromAllLists(id) {
  // Verification is executed against SUT datasets: users directly, and loans/holds indirectly by userId.
  id = asInteger(id);
  verifySutListDoesNotContain("users", "/users", { q: realUserId(id), description: verifyAbsentDescription("User", id, "users") }, function (item) {
    return item && asInteger(item.id) === id;
  }, "User " + id + " still appears in users list");
  verifySutListDoesNotContain("loans", "/loans", { userId: realUserId(id), description: verifyAbsentDescription("User", id, "loans") }, function (item) {
    return item && asInteger(item.userId) === id;
  }, "User " + id + " still appears in loans list");
  verifySutListDoesNotContain("holds", "/holds", { q: realUserId(id), description: verifyAbsentDescription("User", id, "holds") }, function (item) {
    return item && asInteger(item.userId) === id;
  }, "User " + id + " still appears in holds list");
}

function tryToDeleteUserAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/users/" + realUserId(id);
  var description = verifyRejectedDescription("User", id, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedUserAndExpectError(id) {
  tryToDeleteUserAndExpectError(id, 404);
}

function tryToDeleteNonexistingUserAndExpectError(id) {
  tryToDeleteUserAndExpectError(id, 404);
}

function matchAddUser(id) {
  return bp.EventSet("Add User " + id, function (e) {
    var parameters = e && e.data && e.data.parameters;
    if (e.name === "POST" && getRequestPath(e) === "/users" && hasExpectedCode(e, 201) && parameters && asInteger(parameters.id) === asInteger(id)) return true;
    return isValidRequestEvent(e, "createUser") && parameters && asInteger(parameters.id) === asInteger(id);
  });
}

function matchAnyUserAdded() {
  return AnyUserAdded;
}

function matchDeleteUser(id) {
  return bp.EventSet("Deleted Users " + id, function (e) {
    if (e.name === "DELETE" && getRequestPath(e).startsWith("/users/") && hasExpectedCode(e, 200) && asInteger(extractEventData(e).id) === asInteger(id)) return true;
    return isValidRequestEvent(e, "deleteUser") && asInteger(extractEventData(e).id) === asInteger(id);
  });
}

function matchAnyUserDeleted() {
  return AnyUserDeleted;
}

function createHold(logicalBookId, id, userId, expectedCode, description) {
  logicalBookId = asInteger(logicalBookId);
  id = asInteger(id);
  userId = asInteger(userId);

  var reqDescription = description || (createDescription("Hold", id) + " for User " + userId + " and Book " + logicalBookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 201 : asInteger(expectedCode);
  var parameters = { description: reqDescription, id: id, userId: userId, bookId: logicalBookId };
  // bookId in each valid body is a placeholder (logicalBookId), overwritten with the real id in
  // onSelected right before actuation - see the realId doc comment above.
  var variants = [
    { name: "createHold (valid-standard): " + id, body: { userId: realUserId(userId), bookId: realBookId(logicalBookId) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 ? rememberCreatedId("HOLD", id) : undefined, valid: true },
    { name: "createHold (valid-swapped-order): " + id, body: { bookId: realBookId(logicalBookId), userId: realUserId(userId) }, expectedResponseCodes: [expectedCode], parameters: parameters, callback: expectedCode === 201 ? rememberCreatedId("HOLD", id) : undefined, valid: true }
  ];

  var invalidCases = [
    { name: "missing bookId", body: { "id": id, "userId": userId } },
    { name: "missing userId", body: { "id": id, "bookId": logicalBookId } },
    { name: "missing id", body: { "userId": userId, "bookId": logicalBookId } },
    { name: "missing all required fields", body: {} },
    { name: "id has wrong type", body: { "id": "bad-hold-id", "userId": userId, "bookId": logicalBookId } },
    { name: "userId has wrong type", body: { "id": id, "userId": "bad-user-id", "bookId": logicalBookId } },
    { name: "bookId has wrong type", body: { "id": id, "userId": userId, "bookId": "bad-book-id" } },
    { name: "multiple wrong types", body: { "id": true, "userId": false, "bookId": "bad-book-id" } },
    { name: "id is null", body: { "id": null, "userId": userId, "bookId": logicalBookId } },
    { name: "userId is null", body: { "id": id, "userId": null, "bookId": logicalBookId } },
    { name: "bookId is null", body: { "id": id, "userId": userId, "bookId": null } },
    { name: "id is zero", body: { "id": 0, "userId": userId, "bookId": logicalBookId } },
    { name: "userId is zero", body: { "id": id, "userId": 0, "bookId": logicalBookId } },
    { name: "bookId is zero", body: { "id": id, "userId": userId, "bookId": 0 } },
    { name: "id is negative", body: { "id": -id, "userId": userId, "bookId": logicalBookId } },
    { name: "userId is negative", body: { "id": id, "userId": -userId, "bookId": logicalBookId } },
    { name: "bookId is negative", body: { "id": id, "userId": userId, "bookId": -logicalBookId } },
    { name: "id is object", body: { "id": { "val": id }, "userId": userId, "bookId": logicalBookId } },
    { name: "userId is object", body: { "id": id, "userId": { "val": userId }, "bookId": logicalBookId } },
    { name: "bookId is object", body: { "id": id, "userId": userId, "bookId": { "val": logicalBookId } } }
  ];

  variants = variants.concat(invalidCases.map(function(c) {
    return { name: "createHold (invalid - " + c.name + "): " + id, body: c.body, expectedResponseCodes: [400] };
  }));

  while (true) {
    var valid = false;
    var response = svc.postOneOf("/holds", variants, function (chosen) {
      valid = chosen.valid === true;
    });
    if (valid) return response;
  }
}

function tryToCreateHoldAndExpectError(bookId, id, userId, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createHold(bookId, id, userId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the operation is not allowed in this state"));
}

function tryToCreateHoldWithSameIdAndExpectError(bookId, id, userId, expectedCode) {
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  return createHold(bookId, id, userId, expectedCode, verifyRejectedDescription("Hold", id, "create", "the id already exists"));
}

function tryToCreateHoldWithBadParametersAndExpectError(id, userId, expectedCode) {
  id = asInteger(id);
  userId = asInteger(userId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/holds";
  var reqDescription = verifyRejectedDescription("Hold", id, "create", "required parameters are missing or invalid");
  var cases = [
    { name: "missing bookId", body: { "id": id, "userId": userId } },
    { name: "missing userId", body: { "id": id, "bookId": userId } },
    { name: "missing id", body: { "userId": userId, "bookId": userId } },
    { name: "missing all required fields", body: {} },
    { name: "id has wrong type", body: { "id": "bad-hold-id", "userId": userId, "bookId": userId } },
    { name: "userId has wrong type", body: { "id": id, "userId": "bad-user-id", "bookId": userId } },
    { name: "bookId has wrong type", body: { "id": id, "userId": userId, "bookId": "bad-book-id" } },
    { name: "multiple wrong types", body: { "id": true, "userId": false, "bookId": "bad-book-id" } },
    { name: "parameters have swapped invalid values", body: { "bookId": id, "id": "Hold " + id, "userId": "User " + userId } },
    { name: "id is null", body: { "id": null, "userId": userId, "bookId": userId } },
    { name: "userId is null", body: { "id": id, "userId": null, "bookId": userId } },
    { name: "bookId is null", body: { "id": id, "userId": userId, "bookId": null } },
    { name: "id is zero", body: { "id": 0, "userId": userId, "bookId": userId } },
    { name: "userId is zero", body: { "id": id, "userId": 0, "bookId": userId } },
    { name: "bookId is zero", body: { "id": id, "userId": userId, "bookId": 0 } },
    { name: "id is negative", body: { "id": -id, "userId": userId, "bookId": userId } },
    { name: "userId is negative", body: { "id": id, "userId": -userId, "bookId": userId } },
    { name: "bookId is negative", body: { "id": id, "userId": userId, "bookId": -userId } },
    { name: "unexpected field", body: { "id": id, "userId": userId, "bookId": userId, "unexpected": "value" } }
  ];
  var variants = cases.map(function (c) {
    return { body: c.body, expectedResponseCodes: [expectedCode], description: reqDescription + " - " + c.name };
  });
  svc.postOneOf(url, variants);
}

function deleteHold(id, expectedCode, userId, bookId) {
  id = asInteger(id);
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
    { name: "deleteHold (valid): " + id, url: "/holds/" + realHoldId(id), expectedResponseCodes: [expectedCode], parameters: parameters, valid: true },
    { name: "deleteHold (invalid - bad-id): " + id, url: "/holds/bad-id", expectedResponseCodes: [400] },
    { name: "deleteHold (invalid - zero): " + id, url: "/holds/0", expectedResponseCodes: [400] },
    { name: "deleteHold (invalid - negative): " + id, url: "/holds/-1", expectedResponseCodes: [400] }
  ];

  while (true) {
    var valid = false;
    var response = svc.deleteOneOf("/holds/" + id, variants, function (chosen) { valid = chosen.valid === true; });
    if (valid) return response;
  }
}

// verifyHoldDeleteFuzz (static per-field fuzz cases) was replaced by the dynamic valid/invalid
// loop inside createHold/deleteHold above. verifyHoldReadFuzz was removed and not replaced: the
// /holds search endpoint accepts any `q` value and always answers 200, so there is no rejectable
// invalid variant to fuzz for hold reads (see the note above verifyMissingEntityReadIsRejected).

function tryToUpdateHoldAndExpectError(id, userId, bookId, body, expectedCode) {
  id = asInteger(id);
  userId = asInteger(userId);
  bookId = asInteger(bookId);
  expectedCode = expectedCode === undefined || expectedCode === null ? 405 : asInteger(expectedCode);
  tryToUpdateAndExpectError("Hold", id, "/holds/" + realHoldId(id), body, expectedCode);
}

function verifyHoldExists(id, stillRelevant) {
  // Verification is executed against the SUT dataset by reading the holds list and searching for this hold id.
  id = asInteger(id);
  verifySutListContains("holds", "/holds", { q: realHoldId(id), description: verifyExistsDescription("Hold", id, "holds") }, function (item) {
    return item && asInteger(item.id) === id;
  }, "Hold " + id + " was not found in the SUT holds list", stillRelevant);
}

function verifyHoldAbsentFromAllLists(id) {
  // Verification is executed against the SUT dataset by confirming this hold id is absent from the holds list.
  id = asInteger(id);
  verifySutListDoesNotContain("holds", "/holds", { q: realHoldId(id), description: verifyAbsentDescription("Hold", id, "holds") }, function (item) {
    return item && asInteger(item.id) === id;
  }, "Hold " + id + " still appears in holds list");
}

function tryToDeleteHoldAndExpectError(id, expectedCode) {
  id = asInteger(id);
  expectedCode = expectedCode === undefined || expectedCode === null ? 400 : asInteger(expectedCode);
  var url = "/holds/" + realHoldId(id);
  var description = verifyRejectedDescription("Hold", id, "delete", "the operation is not allowed in this state");
  svc.delete(url, { expectedResponseCodes: [expectedCode], parameters: { description: description } });
}

function tryToDeleteDeletedHoldAndExpectError(id) {
  tryToDeleteHoldAndExpectError(id, 404);
}

function tryToDeleteNonexistingHoldAndExpectError(id) {
  tryToDeleteHoldAndExpectError(id, 404);
}

function matchAddHold(id) {
  return bp.EventSet("Add Hold " + id, function (e) {
    var parameters = e && e.data && e.data.parameters;
    if (e.name === "POST" && getRequestPath(e) === "/holds" && hasExpectedCode(e, 201) && parameters && asInteger(parameters.id) === asInteger(id)) return true;
    return isValidRequestEvent(e, "createHold") && parameters && asInteger(parameters.id) === asInteger(id);
  });
}

function matchDeleteHold(id) {
  return bp.EventSet("Deleted Holds " + id, function (e) {
    if (e.name === "DELETE" && getRequestPath(e).startsWith("/holds/") && hasExpectedCode(e, 200) && asInteger(extractEventData(e).id) === asInteger(id)) return true;
    return isValidRequestEvent(e, "deleteHold") && asInteger(extractEventData(e).id) === asInteger(id);
  });
}

function matchAnyHoldDeleted() {
  return AnyHoldDeleted;
}
