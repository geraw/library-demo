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

function verifyExistsDescription(entityName, id, how) {
  return "Verify: " + entityDescription(entityName, id) + " exists" + (how ? " (" + how + ")" : "");
}

// List reads only check that the SUT answers 200 (see readSutList), so they are described as
// reads, not as verifications of the list's contents.
function readListAfterCreateDescription(entityName, id, listName) {
  return "Read: " + listName + " list for " + entityDescription(entityName, id) + " after create";
}

function readListAfterDeleteDescription(entityName, id, listName) {
  return "Read: " + listName + " list for " + entityDescription(entityName, id) + " after delete";
}

function verifyRejectedDescription(entityName, id, action, reason) {
  return "Verify: " + action + " " + entityDescription(entityName, id) + " is rejected" + (reason ? " because " + reason : "");
}

// The three accessors below read the event shape RESTSession produces (svc.get/post/delete):
// data.url, data.expectedResponseCodes, and a JSON string in data.body.

function getExpectedResponseCodes(e) {
  var data = e && e.data ? e.data : e;
  return data && Array.isArray(data.expectedResponseCodes) ? data.expectedResponseCodes : [];
}

function hasExpectedCode(e, code) {
  return getExpectedResponseCodes(e).indexOf(code) !== -1;
}

function getRequestPath(e) {
  var data = e && e.data ? e.data : e;
  if (!data || !data.url) return "";
  var p = String(data.url).replace(/^https?:\/\/[^\/]+/, "");
  var qIdx = p.indexOf("?");
  return qIdx === -1 ? p : p.substring(0, qIdx);
}

function getJsonBody(e) {
  var data = e && e.data ? e.data : e;
  if (!data || typeof data.body !== "string") return null;
  try { return JSON.parse(data.body); } catch (err) { return null; }
}

//////////////////////////////////////////////////////////////////////////
// SUT reads.
//////////////////////////////////////////////////////////////////////////

// Reads a SUT list, expecting 200. svc.get never hands back the HTTP response, so the list's
// contents cannot be inspected here (that would need a REST callback).
function readSutList(url, parameters) {
  return svc.get(url, { parameters: parameters, expectedResponseCodes: [200] });
}

// Reads the detail of an entity that was deleted, expecting 404.
function verifyMissingEntityReadIsRejected(entityName, id, url) {
  var description = verifyRejectedDescription(entityName, id, "read", "the " + entityName.toLowerCase() + " no longer exists");
  svc.get(url, { expectedResponseCodes: [404], parameters: { description: description, id: asInteger(id) } });
}
