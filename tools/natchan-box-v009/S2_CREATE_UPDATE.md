# S2 — independent create/update comparison (009-dev.4)

S2 is implemented for declared scalar fields, using the same judge for every tool label. No stories, JS, producer
verdicts, known-bug catalogs or product-specific method tables are inputs. The analyzer sends no HTTP requests.
The comparison is not an assertion that every difference between create and update is a product bug.

## Contract candidates

`derive` emits `create_update_bindings`, including diagnostics and exact source pointers:

1. Structural collection POST plus item PUT/PATCH, retaining exact route/trailing-slash spelling.
2. Alternative methods (e.g. PUT creation, POST update) only with explicit public operation role cues and the **same
   resolved request-schema reference**. Cues are fixed create/update/edit prefixes of summary/description, or a
   conservative operation-ID prefix when no text exists. They are not language-model interpretations.
3. Shared scalar input fields must have identical assertion fingerprints after excluding descriptive annotations and
   defaults (the value must be explicitly sent). All other assertions, including ones not validated by S3, participate
   in equality. Required-field lists of the containing create/PATCH objects may legitimately differ.
4. Read-only/write-only, complex, null, schema-ambiguous and differently constrained fields cannot supply a comparison.

Schema names do not select a rule. Shared schema references alone do not establish resource identity or parent scope.
The emitted relationship remains a structural candidate; public role cues do not prove equivalent business intent.

## Runtime prefix and pairing

Require declared complete, exclusive, serial capture plus recorded principal and reset epoch, exactly as for S1/S5.
Separate origin/scheme, actor, epoch, optional case and concrete parent collection. Query semantics are not inferred.
The update target must first have a usable same-scope GET 200 object with at least one declared field present.

For each explicitly sent comparable update field, find retained creation observations with the same scalar value and
contract pair. Numbers compare by exact decimal representation without arbitrary-integer rounding, booleans remain
distinct from numbers, aware date-times compare by instant, and other strings compare exactly.

- No matching creation -> `not_evaluable`.
- Several matching creations -> `not_evaluable`; no latest/most-convenient response is selected.
- A uniquely confirmed same-created-resource match can disambiguate other known resources. It does **not** erase
  intervening mutations or make the comparison controlled again.
- Across nonparallel/nested routes, missing parent/identity linkage causes abstention, not a guessed relationship.

The unit is one update field and contract pair. If a guard prevents pairing from starting, one update-level abstention is emitted instead. Multiple fields and S1/S3/S5/S7 may describe the same event;
their occurrence counts are not distinct-bug counts. A reported field is the value being compared, not a proven cause
of an error. Every S2 verdict explicitly sets `field_causality_proven: false`.

## Response-class comparisons

Classes: synchronous 2xx accepted (excluding 202), 400/422 validation rejected, 5xx server error.
Missing responses, 202, redirects, and 401/403/404/409/429 are not equated with target-field validation rejection.

| Observation with matching input and resource prefix | S2 result |
|---|---|
| Create accepted, update validation-rejected (or reverse) | `policy_observation` |
| One path returns 5xx and the other class differs | `policy_observation`; S7 separately records the server error |
| Both validation-rejected or both server-error class | `consistent` for **response class only**, never proof of healthy behavior |
| Either class unavailable/noncomparable | `not_evaluable` |

Status differences cannot establish that the compared field caused rejection or that unrelated preconditions were
equivalent. This is why they are policy observations rather than automatic product violations.

## Stored-value comparisons

If both writes are accepted, S2 requires actual GET readbacks; write response bodies are not accepted as stored state.
The created item is identified only by:

- a recorded 201 `Location`, resolved against the request URI and checked against the declared item route/origin; or
- an unambiguous public OpenAPI 201 operation link to the item GET, with supported path-parameter expressions.

This uses [RFC 9110, Location semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.2).
There is no guess from `id`, `uuid`, object position or a scenario label. Conflicting links/Location, external server
overrides, malformed URIs and ambiguous operation IDs cannot establish identity.

Both creation and update readbacks must be in the correct scope, without an intervening mutation before their reads.
Readback values must be declared comparable scalars. Missing fields/nulls/bodies are not substituted by defaults.

- Same stored value -> `consistent` on that field.
- Different stored values -> `violation` **candidate** only for the same explicitly identified created item, with no
  mutation between the selected creation and update, the target unchanged in the update preimage, and all sent update
  fields equal to the creation's comparable input fields.
- Different stored values with weaker known controls -> `policy_observation`, with control flags reported.
- Missing comparable creation/update readback -> `not_evaluable`.

Even a controlled difference retains the explicit assumption that the same declared writable scalar has equivalent
write meaning. Intentional server transformations may still require human triage. No root cause or confirmed bug
identity is inferred, and no known-product exception is added to suppress a candidate.

## Limits and missing evidence

Keep at most 512 creation arms and 16,384 internal scalar fingerprints per retained epoch. If a limit is exceeded,
history is marked truncated; subsequent comparisons abstain until a new epoch. Old matches cannot silently reappear
after eviction. Per-write/read state body limit is 64 KiB. Reset boundaries clear history; mutation boundaries clear
pending readbacks. The audit reports truncation, ambiguity and evaluated status/readback counts.

Arrays/nested values, PATCH null actions, aliases without public identity/navigation evidence, general semantic
interpretation of descriptions, relation inference and severity/known-bug matching are outside this S2 subset.
Different declared constraints are explained as excluded fields rather than treated as path inconsistency.

## Required producer retention

Keep request and answer bodies, response status, full URL when available, response headers (especially `Location`),
principal, reset epoch, optional case, and truthful timing/capture provenance. Redact secrets, not identity/navigation
structure. HAR response headers are read directly. JSONL uses `response_headers` as a string map or header list.

The previously reviewed `baselines/v2/har_to_v009.py` did not copy response headers. Add their safe retention on the
producer side before expecting Location-based storage comparisons from its output; original HAR may still have them.
Do not reconstruct lost headers from guessed IDs. An API may legitimately omit Location/links; S2 then reports its
storage comparison as unevaluable while still evaluating eligible response-class differences.

This release changes derived knowledge and engine hashes. Regenerate knowledge/freeze for a new development cycle.
Do not pool post-hoc reruns with a previously frozen held-out evaluation. Operational v008 is unchanged.

## Runnable example

Copy `examples/s2/contract.json`, `request.json` and `traffic.jsonl` to a new experiment directory. Run `derive`,
`freeze` and `analyze` with the same CLI as README. The four synthetic exchanges show a controlled stored-value
difference. Expected S2 output: one `violation` candidate on `title`, source-linked to all four exchanges. S1 also
reports a candidate; these are two property checks, not two confirmed bugs. This is development evidence only.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $engine = Join-Path (Get-Location).Path 'tools\natchan-box-v009\natchan.py'
    $example = Join-Path (Get-Location).Path 'tools\natchan-box-v009\examples\s2'
    $experiment = Join-Path $env:TEMP ('natchan-s2-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $experiment | Out-Null
    foreach ($name in @('contract.json', 'request.json', 'traffic.jsonl')) {
        Copy-Item -LiteralPath (Join-Path $example $name) -Destination $experiment
    }
    python $engine derive --contract (Join-Path $experiment 'contract.json') --output (Join-Path $experiment 'knowledge.json')
    if ($LASTEXITCODE -ne 0) { throw 'Derivation failed.' }
    python $engine freeze --contract (Join-Path $experiment 'contract.json') --knowledge (Join-Path $experiment 'knowledge.json') --output (Join-Path $experiment 'freeze.json')
    if ($LASTEXITCODE -ne 0) { throw 'Freeze failed.' }
    python $engine analyze --request (Join-Path $experiment 'request.json') --output (Join-Path $experiment 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed.' }
    Get-Content -LiteralPath (Join-Path $experiment 'analysis\report.md')
    Write-Host "NATCHAN_S2_OUTPUT $experiment\analysis"
}
```

Acceptance: 144 v009 tests passed, including 41 new S2 tests and four actual loopback HTTP modes.
All 275 operational v008 tests passed. Six exact original contracts derived and froze; S2 pair counts are
Dependency-Track 7, Gitea 24, Kimai 6, Tandoor 74, Vikunja 6 and wger 54. These counts are **not** detected bugs.
See S2_CONTRACT_ACCEPTANCE.json for hashes and scope. No existing system run corpus was reanalyzed for S2 here.
