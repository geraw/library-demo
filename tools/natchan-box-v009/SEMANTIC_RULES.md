# Bounded independent semantic rules — 009-dev.3

This is a development subset of the supplied requirements, not full semantic coverage.
Same procedures for all tool names. No producer verdicts, scenario names, JS, system source or known-bug catalogs
are consumed by the judge. Tests may implement a synthetic SUT; its implementation is not a judge input.

## Resource identity and capture assumptions

- Derive item write/read candidates from a shared concrete URI route, matching GET 200 JSON-object and PUT/PATCH
  request schemas. A guessed `id` field or a schema reference is not a resource key.
- Scope observations by URI, captured origin, principal, reset epoch and optional opaque sequence ID.
- Require a declared complete, exclusive, serial capture for cross-exchange checks. These are unverified capture
  assertions, not inferred product facts; missing assertions cause abstention. Recorded interval overlap/order
  conflicts disable state checks for the entire capture before any state verdicts are emitted.
- Any mutation invalidates earlier cached preimages and pending comparisons globally. A failed/missing-answer mutation
  may still have changed state. A read failure discards an older preimage. Epoch changes discard state even if an old
  epoch label is reused later. Wrong-origin/actor/sequence reads never close a pending comparison.
- Only GET 200 object bodies without query parameters supply snapshots. No pagination/filtered-view assumptions.
- Bounded retention: 128 snapshots, 64 KiB state body per snapshot/write/read and one pending mutation.
  Eviction loses evidence and causes abstention rather than guessing. No request/answer body is emitted in a verdict.

## S1 — read-back consistency subset

Opportunity: a matched item PUT/PATCH. Deferred evaluation needs successful synchronous response, comparable sent
fields and a later same-scope read without an intervening mutation. HTTP 202/redirects are not interpreted.
Missing actor, reset, body, binding or read produces a reasoned `not_evaluable` verdict.

Comparable fields must be declared scalar fields with matching types/formats in request/read schemas. Read-only,
write-only, composed, complex and schema-mismatched fields are excluded. Compare numeric values mathematically
(boolean is not integer); timezone-aware date-time strings by instant; other scalar values exactly.

- Every evaluated field matches: `consistent` for those fields only.
- Changed field or omitted required read field: `violation`, explicitly a persistence-assumption candidate.
- Only optional read fields omitted: `policy_observation`.
- Unsupported value comparison: `not_evaluable`.

The generic persistence assumption is explicit in the verdict. Same-named fields do not prove business intent, so
triage may find intentional normalization. Only formal read/write flags and numeric/date-time equivalence are handled
automatically; natural-language descriptions are not interpreted. S1 consistency does not prove response-schema validity.
Creation/read bindings and nested fields/arrays are not implemented.

## S3 — scalar constraint subset

Opportunity: POST/PUT/PATCH with matched contract operation. Supported fields: scalar type, enum/const, min/max string
length, numeric inclusive/exclusive bounds and required fields declared in properties. Unsupported schemas/values,
formats, regex patterns, nesting, arrays and additional-properties rules are not certified by this subset.

- No violation among evaluated constraints: `consistent`, named `INPUT_WITHIN_EVALUATED_CONSTRAINT_SUBSET`.
  This says nothing about other preconditions, business behavior or why a valid-input request was rejected.
- Invalid input rejected with 4xx: `consistent` for the rejection check.
- Invalid input accepted: `policy_observation` while storage is unverified; a returned error body is not read-back state.
- Invalid input followed by eligible same-resource GET 200 retaining an invalid field: `violation` with exact schema pointers.
- Missing definitive rejection/storage: `not_evaluable`.

S3 static request checks do not require actor/order assertions. Storage confirmation uses all S1 identity/capture guards.
Normalized valid storage is an observation, not a false stored-constraint violation. No full JSON Schema validator is claimed.

## S5 — observed state after an error

Opportunity: matched item PUT/PATCH answered with 4xx/5xx (missing answer abstains). Require eligible preimage and
postimage; compare only sent scalar fields that request an observable change. Missing fields or unchanged request
values cannot establish a rollback test.

- All compared fields kept: `consistent`, `unchanged` on this projection only.
- All applied: `policy_observation`, `committed_despite_error`.
- Some applied and some kept: `policy_observation`, `partial`.
- Other values observed: `policy_observation`, `other_state_change`.

Every verdict states that a contract-level atomicity guarantee was not established and that full-resource atomicity
was not proven. These observations expose behavior for triage; they are not automatically proven contract bugs.
Create/delete atomicity and collateral/server-managed changes are not certified by this subset.

## S7 and remaining classes

S7 remains status-only: matched 5xx or undeclared status -> candidate; declared non-5xx -> consistent for status only;
missing answer/operation -> abstention. Server signatures require unique request-ID joins and do not prove root cause.
S2 path consistency, S4 reference integrity and S6 placement/views remain unimplemented with null counts.

## Counting and interpretation

One S7 judgement per exchange, plus applicable S1/S3/S5 checks. One exchange can participate in multiple properties;
do not add their occurrences as distinct bugs. A policy observation is separate from a violation.
An opportunity denominator is per defined check, not seven automatic checks per HTTP exchange.
Zero opportunities (e.g. no PUT/PATCH in Library) is not evidence of business correctness.
Unknown-route mutations are separately counted and invalidate state; they do not certify zero semantic defects.
The analyzer never initiates an HTTP request. End-to-end test harnesses and retrospective archive readers are separate.

Dev.3 bounds nested expansion beyond depth 2, diagnoses unavailable bindings, and separates S7 5xx/undeclared-status groups.
Start-only/completion-observation timing does not independently verify a serial history. See REVIEW_RESPONSE_20261101.md.
