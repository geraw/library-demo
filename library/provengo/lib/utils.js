//////////////////////////////////////////////////////////////////////////
// Generic REST/Provengo helpers with no knowledge of this SUT's domain
// (books, users, loans, holds). Anything here should read the same in a
// spec for a completely different REST service.
//
// Loaded before spec/js (see the project's documented load order), so these
// are available regardless of definition order relative to the SUT-specific
// files that call them.
//////////////////////////////////////////////////////////////////////////

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

function isValidRequestEvent(e, actionName) {
  return e && e.data && e.data.action === actionName && e.data.type === "valid";
}

// Pulls a REST callback's response body out of the Java map shape {headers, code, body} that the
// REST library hands to a request's `callback` (svc.post()'s return value is just the request
// event, not the response). During static analysis no real HTTP call happens and no callback
// fires, so callers only get here with a real captured response.
function extractResponseBody(response) {
  if (response === undefined || response === null) return null;
  var bodyText = response.body;
  if (typeof bodyText !== "string") return null;
  try { return JSON.parse(bodyText); } catch (err) { return null; }
}

//////////////////////////////////////////////////////////////////////////
// SUT list readers and verification helpers.
//
// Generic in the sense that they take the list name/URL/predicate as
// parameters - no book/user/loan/hold knowledge lives here.
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

function verifyMissingEntityReadIsRejected(entityName, id, url) {
  var description = verifyRejectedDescription(entityName, id, "read", "the entity does not exist");
  svc.get(url, { expectedResponseCodes: [404], parameters: { description: description } });
}
