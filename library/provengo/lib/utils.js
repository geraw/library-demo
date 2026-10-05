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

//////////////////////////////////////////////////////////////////////////
// SUT list reads.
//////////////////////////////////////////////////////////////////////////

// Reads a SUT list, expecting 200, and returns the event sync() selected - svc.get never hands
// back the HTTP response, so the list's contents can't be inspected here (that would need a REST
// callback). Within a waitFor(...) scope, the returned event may be the waited-for one instead.
function readSutList(url, parameters) {
  return svc.get(url, { parameters: parameters, expectedResponseCodes: [200] });
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
