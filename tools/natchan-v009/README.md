# Automatic classification pipeline v009

The normalized event pipeline now assembles measurements, verifies trace context, runs all 14 registered families and uses one shared catalog classifier. REF-1/LINK-2 have executable providers; DIV-1 reuses EDGE-U rather than duplicating its logic. Historical journal adapters now also feed the shared classifier, with limited evidence tiers preserved. No LLM, server requests, generated tests or manual per-finding classification is involved in these entry points.

## Scope of the completion

Supported families: RESPONSE, EDGE-1, RT-1, ATOM-1-2, EDGE-U, KNOWN, CASCADE-1, ADJ, IDEM, VIEW, LINK, REF-1, LINK-2, DIV-1.

`analyzer.py` accepts `natchan-events/1` or trusted gateway `natchan-measurements/1`. The new event interface computes context from actual event IDs, order, run/case, actors, resources, resets and intervening writes. It does not accept supplied `context: true` flags on the event path. The older measurement interface remains for existing trusted adapters; its context assertions remain the adapter's responsibility.

A producing-tool gateway must emit probe ID/family/role tags and normalized requests/responses. The product profile supplies version, schema fields, relationship policies, identity aliases, reference semantics and trigger definitions. `families` provides defaults; optional `probe.policy` selects a family-qualified entry in `profile.policies` for different operations/fields. This metadata is configured once per supported integration, not completed manually for every finding. Schema alone does not prove business intent.

This is not an automatic parser for every arbitrary future tool log or an automatic discovery engine for unknown business requirements. A new product/tool still needs its gateways. Missing evidence yields a structured `not_evaluable` result with reasons; no recorded probes yield `no_measurements`, not a zero-bug result. Incomplete capture declarations or duplicate event IDs reject the input globally rather than producing a misleading negative report.

## Running

```powershell
git pull --ff-only origin master
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\tools\natchan-v009\Invoke-Natchan-v009.ps1 `
    -InputPath '.\tools\natchan-v009\synthetic-all-families.json'
```

The supplied example is explicitly SYNTHETIC, contains all 14 families and is not research evidence. For a real normalized producer export, replace InputPath. The wrapper uses repository `.venv` when present, otherwise `python`; requires Python 3.10+, standard library only for analysis. The PowerShell wrapper was source-reviewed on Linux, not executed on Windows.

For original retained archives (repeat `--input` for multiple archives):

```powershell
python .\tools\natchan-v009\historical.py `
    --input 'C:\evidence\review_g005_s6.zip' `
    --input 'C:\evidence\v164-triggers-20261018-153232-redacted.zip' `
    --output '.\historical-report-new.json'
```

Existing outputs are rejected. The historical gateway reuses the bounded nested ZIP reader from v008. No extraction occurs; journals stay independently scoped; exact journal duplicates are removed. Full reports include source references, not an instruction to replay evidence against a server. Redact sensitive input data before sharing reports.

See `EVIDENCE_CONTRACT.json` for required roles and witness requirements. Native results supplied in `native_results` are retained separately and never inferred from external patterns. Existing Library/v002 analysis envelopes retain their existing entry points; this event CLI does not silently reinterpret them.

## How acceptance was tested

1. **Positive end-to-end examples:** one frozen synthetic case per family passes through event assembly, provider and catalog. Assert the expected pattern ID, not just success exit status.
2. **Healthy controls:** one corrected case per family must be evaluated without its defect pattern. Unknown is not accepted as a passing healthy control.
3. **Evidence mutations:** remove readbacks, change actors or parents, insert intervening writes/resets, duplicate roles/IDs, move timestamps outside windows, corrupt body types and supply forged verdicts. Assert missing context or absence of the inappropriate classification.
4. **Known-bug controls:** GIT-C7 can match only the supported version and source-backed email validation context. A different version or unrelated validation message must not match.
5. **Original evidence:** re-read 18 retained journals with input SHA256 checks. Freeze descriptive baseline counts independently of the running classifier: 174 ID-projection differences (48 REF + 126 LINK), 28 response-class differences, 23 error observations (17 KNOWN attempts + six ADJ probes). These are overlapping symptom occurrences, not unique product defects. No unqualified historic observation is allowed to become a named known bug.
6. **Regression:** execute historical and current suites in separate processes to avoid their historical module-name collisions. 83 tests in v009 and 134 retained tests passed: 217 total. Test results and original-evidence parity are separate artifacts under `reviews/`.

```powershell
python -m pytest .\tools\natchan-v009\tests -q
python .\tools\natchan-v009\validate_historical.py --root .
```

The historical validation needs the exact private evidence cache named in `reviews/historical-summary.json`; public Git contains code, hashes and compact summaries, not private raw journals. Failure to locate inputs is an error, not a successful validation.

## Classification rules and safeguards

- CASCADE requires a declared relationship, recorded child-parent binding, successful child-before read, successful parent deletion, matching identity and no intervening writes. A child read denied with 403 remains unknown. Parent path names alone are insufficient.
- ADJ verifies trigger operation, successful trigger, timestamps/window and intervening triggers. Its result is temporal association, never a causal claim.
- EDGE-U/DIV require the actual same field/value, parent scope, an update preimage and a profile statement that create/update preconditions are comparable. If both succeed, stored-value comparison needs both readbacks. GIT-C7 matching additionally checks the accepted email body and email-related rejection.
- REF/LINK compare ID sets only after a successful write/readback, with explicit `observe` or `exact_set` semantics. A descriptive projection difference is separate from a policy violation. Producer-only ID projections in old logs remain a lower tier.
- Atomicity requires full snapshots or scoped matching-item counts. Definite applied+kept fields establish partiality even if other fields are unknown. This fixes a conservative omission in the retained v005 implementation; historical source is unchanged.
- KNOWN is a non-suppressing signature match. Missing response body cannot satisfy a broad regex. A retry summary alone does not prove a database-lock cause.
- IDEM verifies identical writes, resource, identity and order; either response can expose the server error. It does not infer that every endpoint promises idempotency.
- Malformed readback objects do not become dropped-field findings. Unknown fields, unknown product policies and missing measurements remain visible.

## Actual readiness boundary

All registered families execute automatically on complete, correctly normalized evidence, or return explicit missing requirements. This validates the shared mechanism; it does not prove every historical raw gateway already emits all required facts. The old 18-journal cohort still lacks full atomicity/readback bodies and some relationship/trigger context. The new historical route classifies justified symptoms and reports missing semantics without manual interpretation. It cannot reconstruct observations that were never recorded.

Before the next real product campaign, its collector must satisfy `EVIDENCE_CONTRACT.json` and pass the positive, healthy and missing-evidence acceptance cases for its gateway/profile. Do not claim a real-system family supported merely because its synthetic core test passed. Remaining historical archives listed in v008 were not newly fetched by this release.
