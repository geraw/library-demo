# Natchan v003 — classification and known-bug catalogs

This release implements offline classification, grouping and evidence-based association. It extends the existing gateway/evaluator pipeline. It does not run a generator, replay HTTP, retry failures or suppress known errors. Python 3.9+ standard library only; no language model is used.

## Run on an existing Library analysis

From the repository root:

```powershell
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\tools\natchan-v003\Invoke-Natchan-Classify-v003.ps1 `
    -InputPath '.\library\ess-experiment\out\natchan-analysis-v002-20261021-155144-080.json'
```

Use the actual path printed by the earlier analysis command. Output: new timestamped JSON and a readable Markdown report. Existing files are never overwritten. Use `-OutputPath`, `-CatalogPath` and `-Python` if needed. PowerShell wrapper was source-reviewed here, not executed on Windows.

```text
python tools/natchan-v003/classifier.py --input analysis.json --output new-classification.json
python -m unittest discover -s tools/natchan-v003/tests -q
```

## Three separate definitions

| Layer | Files | Meaning |
|---|---|---|
| Generic problem patterns | catalogs/generic.json | HTTP server errors, collateral deletion, qualified write/readback differences, partial writes, paired create/update differences and other declared evidence patterns |
| Product configuration/patterns | catalogs/vikunja.json, catalogs/gitea.json; existing product gateways | Product-scoped patterns and interpretations; operation/state mapping stays in the gateway |
| Known bugs | catalogs/library.json; draft records in vikunja.json | A specific product/version and required evidence conditions; signature matching is not discovery of a new root cause |

Catalogs are versioned inputs and their hashes are included in every report. The Library catalog contains all five seeded mutation definitions, scoped to `library / issta-v006`. This version denotes the experimental fixture profile, not a real Library release number.

The Vikunja and Gitea files incorporate the user's specification: server errors, update atomicity, committed-despite-error, silent changes, boundary enforcement, undocumented restrictions, create/update differences, bad test expectations, stale input, cascade, repeated writes, views, links and correlated lock evidence. These are **product-scoped problem types**, not claims that named historical bugs were reproduced.

Vik-F01, VIK-F04 and C1/C2 are draft known-bug records. Exact affected versions, operations/fields and original positive/negative evidence were not present in the supplied specification. Drafts never match. A qualified compound pattern can recognize silent create transformation + update 5xx + partial update without falsely calling it C2.

## Public bug-description format

See [BUG_FORMAT.md](BUG_FORMAT.md), [catalog.schema.json](catalog.schema.json), and the complete editable [examples/bug-template.json](examples/bug-template.json). JSON is data only: no eval, scripts or callable expressions. Supported predicates: eq, in, gte, present; every positive condition is required; any satisfied exclusion vetoes the match. All matching categories survive; there is no first-match suppression.

A new bug can be added without changing the engine **when its required evidence facts are already supplied by a gateway/detector**. A new kind of evidence, relationship or detector still needs an adapter implementation. A JSON predicate cannot infer arbitrary business semantics or prove its own factual input.

## Inputs and gateways

Accepted input envelopes:

- `natchan-analysis/1`: Library traces are re-evaluated through the preserved product evaluator. Stored findings/bug labels are not trusted as classification input. The adapter then derives collateral deletion from recorded before/after readbacks and records the supporting snapshots. Original archive/member/source references and event relationships are retained.
- `natchan-observations/1`: tool/product-normalized observations; see observations.schema.json. Any tool can supply this format. Product, version, run and source are independent of tool. It supports request/response, qualified before/after state, readable/writable fields, explicit schema constraints and paired experiment metadata.

For a new raw JSON/JSONL format, use a declarative mapping:

```text
python tools/natchan-v003/normalize.py --input raw.jsonl --mapping tools/natchan-v003/examples/jsonl-gateway-mapping.json --output normalized.json
python tools/natchan-v003/classifier.py --input normalized.json --output classified.json
```

The example mapping is an editable shape example, not a claim that a specific historical Vikunja log has those field names. Replace field paths/defaults from actual files; JSON arrays support records_path. The normalizer fingerprints its source and preserves record locations. It labels imported oracle facts as imported; they are not silently promoted into verified facts. Raw HTTP responses, qualified state and explicit metadata can still be mechanically evaluated. When the real Vikunja/Gitea artifacts arrive, verify mappings and add any missing product-specific evidence extraction before scoring those runs.

For canonical observations, `fact_basis: recomputed` declares that a trusted producer recomputed supplied facts; it is a provenance assertion, not cryptographic proof. Producers must be audited. Missing/ordinary imported semantic facts are ignored. Library observations are recomputed locally. Human-readable rule titles, native FAIL text and catalog bug names cannot create a match.

## Implemented detectors and limits

| Evidence available | Computed behavior |
|---|---|
| HTTP status | Server-error category; 5xx is not labelled a process crash |
| Transport error with no status | Transport-failure observation; does not assert infrastructure rather than server root cause |
| Request/before/after plus qualified state metadata | Update partial/committed/rollback, field changed/dropped; incomplete or intervened state is not qualified |
| Explicit readable/writable field set | Silent-change check; bool differs from number; numeric 1 equals 1.0; declared date-time fields compare aware timestamps |
| Field constraints and selected request field | Explicit boundary acceptance; unsupported constraint types remain unsupported |
| Qualified paired create/update observations | Status/storage divergence and combined silent-create/update-error/partial-write pattern |
| Exact request ID and run ID shared with server log | Lock evidence for limited explicit message patterns; no time-only causal assertion |
| Rejection with explicit field schema and size-error message | Undocumented restriction candidate, including Gitea organization name; not proof that all OpenAPI-conforming inputs must succeed |
| Recomputed Library case evidence | First clean violation, collateral state loss, same-owner matching and later missing-hold DELETE consequences |

Views, links, cascades, stale-version input and broader harness/policy determinations have declarative rules; they require verified semantic facts from their respective product providers. This release does not reconstruct all of those facts from arbitrary raw logs. It also does not automatically perform retries, replay, cross-version experiments, global request/log alignment or new search planning.

Lists are order-sensitive, object comparison is structural, and only explicitly listed readable/writable top-level fields are checked in generic readback. More complex PATCH/pagination/eventual-consistency semantics require a product profile. HTTP 403 is not treated as proof of deletion. A repeated-write error is not called a concurrency race. Severities remain context-dependent suggestions, and all matches currently request human review.

## Output and grouping

Every assessment retains catalog ID, predicate checks, observed facts, source, categories and any known-bug association. Library observations link primary violations and later consequences. Multiple categories can describe one observation. Group IDs derive deterministically from product/version/catalog entry/entity/operation/field/log fingerprint. Groups retain occurrences, runs, seeds and tools; these counts are not interchangeable with unique bugs.

Normalization retains semantic numbers such as maxLength 250; it removes only UUIDs and explicitly labelled numeric IDs. Signature grouping does not establish shared root cause. Known-bug IDs provide a separate association. Results preserve unresolved observations and missing known-bug conditions. Frequency does not imply determinism because the eligible-trial denominator is not inferred.

The Markdown companion lists groups and source references. The JSON retains complete conditions and observation witnesses. Known matches are never filtered out as noise. No catalog definitions are passed to testing tools.

## Validation

See VALIDATION_20261021.json. Twenty-five v003 unit tests and the existing twenty-six v002 tests pass. Synthetic Vikunja paired evidence exercises the compound classification, not a live product finding. Real work Library evidence yields 22 collateral-deletion observations associated with LIB-ISSTA-BUG-5 and later 404 consequences in exactly cases 80, 257, 260, 266 and 433. No other known Library bug is inferred.

A regression test covers an important historical artifact: a legacy emitted expected-state array can share mutable Ledger storage and contain later appends. The classifier therefore uses time-local recorded readbacks, not that mutable expected list, to establish collateral loss. Historical evaluator rules and original scores were not changed.


## First historical TSE reanalysis: Mealie

`review_mealie.py` reads original historical identity-program receipts from Mealie_Supervisor_Artifact_v003.zip, reuses the preserved compare_owner_readbacks implementation with source hashes, and submits computed observations to the classifier. It never serializes login/credential receipt bodies.

```text
python tools/natchan-v003/review_mealie.py --archive Mealie_Supervisor_Artifact_v003.zip --output NEW_MEALIE_REVIEW.json
```

Selected original data: eight runs, 392 recorded responses, sixteen 5xx observations, four qualified owner-readback state changes after 500. It uses the nearest owner preimage, yielding 2 to 3 items, instead of attributing earlier successful cross-add changes to the failed write. The fixed household-controls protocol declares other_list_add_a targets list_b and vice versa; this explicit routing allows excluding a proven different-list intervening write. Unknown routing remains unresolved, never silently clean. Generic state-change-after-error is reported alongside server error; neither implies complete transaction commitment, authorization-policy violation or root cause. Named Mealie bug identity is not automatically asserted. See reviews/tse-first-pass/MEALIE_20261021.json.


## Verified handoff to the original Gitea/Vikunja agent

Read HANDOFF_PROMPT_HE.md for the complete Hebrew work prompt, including actual PowerShell/Python commands, artifact discovery, catalog completion, gateway requirements and manual-result parity. TAXONOMY.json enumerates all eleven requested families. Eleven additional subtype rules are explicit drafts; they cannot match until evidence extraction and tests are implemented. Active predicates still do not imply complete raw-product adapters.

Run `python tools/natchan-v003/verify_handoff.py --output NEW_PREFLIGHT.json` before editing. It checks files, catalog references, both unit-test suites, CLI help, a synthetic paired-classification command and a raw-JSONL normalization/classification command. If pwsh is installed it also executes the wrapper; otherwise the report explicitly records that target Windows verification remains required. See HANDOFF_VALIDATION_20261021.json. The Library analysis bridge now rejects unsupported/mixed products or incomplete evidence instead of returning a misleading empty classification.
