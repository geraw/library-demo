# Natchan Box v009 — independent contract context (development milestone 2)

**Version: `009-dev.2`, not a production replacement for v008.** Python 3.10+, standard library only.
Based on repository commit `6310af7baecc25fc46692d1127c80dbc1da4247d`.
The operational v008 directory, branch, request interface, product catalogs and existing integrations are unchanged.
Keep using v008 in established pipelines until v009 passes the later acceptance gates.

This extends the first implementation of the supplied [research requirements](RESEARCH_REQUIREMENTS.md),
not a claim that all seven semantic classes have been implemented.

## What this milestone does

1. Derives a provenance-addressed knowledge document from public OpenAPI 3.0/3.1 or Swagger 2 **JSON**.
   It retains operation schemas, constraints, declared responses, authentication schemes and explicit operation links.
   Resource identities, operation roles and relationships remain **candidates/unknown** when not proven.
   A schema `$ref`, a field named `owner_id`, a nested URL, or an HTTP method does not prove a business relationship.
2. Produces and verifies a deterministic contract/knowledge/code freeze, without inspecting result evidence.
   Supplied knowledge is recomputed from the contract and must match; handwritten overrides are not accepted.
3. Reads raw HTTP JSONL, `research` exchanges in a journal, or bounded HAR 1.2.
   Tool labels select no rules. Producer actions, logical IDs, bug IDs, oracle categories and verdicts are not judges' inputs.
4. Implements bounded **S1/S3/S5** state checks (see below) and the **S7 status-only subset**: exact operation attribution, 5xx candidates, undeclared-status
   candidates, explicit abstention, symptom grouping and unique request-ID log correlation.
   Declared 5xx remain error candidates. Other declared statuses are consistent **only for this status check**.
   An error candidate does not prove a product defect, root cause, severity or business-rule violation.
5. Emits deterministic evidence-linked outputs and numeric exit codes. No SUT requests are sent.

The independent route imports **no v008 runtime module or product catalog**. The earlier work remains available
in the same checkout, but producer-derived profiles and known-bug catalogs are not loaded in this route.

## Explicit capability limits

| Class | Milestone 1 |
|---|---|
| S1 read-back consistency | Same concrete item URI, scalar fields, synchronous PUT/PATCH, controlled capture |
| S2 path consistency | Not implemented; counts/opportunities null |
| S3 constraint conformance | Scalar types, enum/const, lengths, numeric bounds and required declared fields; accepted invalid input needs read-back for storage credit |
| S4 reference integrity | Ambiguities retained; judgement not implemented |
| S5 failure atomicity | Before/after requested scalar fields; observed partial/full commit is policy observation without a contract guarantee |
| S6 placement/view consistency | Not implemented; counts/opportunities null |
| S7 error answers in context | Status checks, operation matching, symptom groups; coarse request-body shape only |

S7 does not infer invalid references, field-level input classes, multipart causes, side effects or business meaning.
Without a unique join it does not infer a server error's cause. Same-looking symptoms need not share a root cause.
All successful analyses currently have status **PARTIAL**, including clean controls.

This milestone inventories entity candidates from GET response schemas, but does not yet prove their identities
or derive a general executable entity graph. Same-route item write/read bindings are retained separately as structural candidates. Operation names/descriptions are not interpreted as business rules.
Composed schemas, reference siblings and external references are left ambiguous/unknown, not silently flattened.
The context document is a conservative partial interpretation, not a complete OpenAPI validator.

## Install separately; do not change the operational checkout

Repository: [geraw/library-demo](https://github.com/geraw/library-demo), branch `natchan-box-v009`.

```powershell
git clone --single-branch --branch natchan-box-v009 https://github.com/geraw/library-demo.git library-demo-natchan-v009
if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
Set-Location .\library-demo-natchan-v009
git rev-parse HEAD
python -m unittest discover -s .\tools\natchan-box-v009\tests -q
if ($LASTEXITCODE -ne 0) { throw 'v009 development tests failed.' }
```

Keep the recorded commit with the experiment. Existing integrations still call `tools/natchan-box-v008/natchan.py`.

## Run the synthetic demonstration

The example is development evidence, not a held-out study. Run from the repository root:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $engine = Join-Path (Get-Location).Path 'tools\natchan-box-v009\natchan.py'
    $example = Join-Path (Get-Location).Path 'tools\natchan-box-v009\examples'
    $experiment = Join-Path $env:TEMP ('natchan-v009-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $experiment | Out-Null
    Copy-Item -LiteralPath (Join-Path $example 'contract.json') -Destination $experiment
    Copy-Item -LiteralPath (Join-Path $example 'request.json') -Destination $experiment

    python $engine derive --contract (Join-Path $experiment 'contract.json') --output (Join-Path $experiment 'knowledge.json')
    if ($LASTEXITCODE -ne 0) { throw 'Contract derivation failed.' }
    python $engine freeze --contract (Join-Path $experiment 'contract.json') --knowledge (Join-Path $experiment 'knowledge.json') --output (Join-Path $experiment 'freeze.json')
    if ($LASTEXITCODE -ne 0) { throw 'Freeze failed.' }

    Copy-Item -LiteralPath (Join-Path $example 'traffic.jsonl') -Destination $experiment
    python $engine analyze --request (Join-Path $experiment 'request.json') --output (Join-Path $experiment 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed.' }
    Get-Content -LiteralPath (Join-Path $experiment 'analysis\result.json')
    Write-Host "NATCHAN_V009_OUTPUT $experiment\analysis"
}
```

Expected: 4 exchanges; S7: 1 consistent, 2 violations, 1 not evaluable; 1 symptom group with 2 occurrences.
S2/S4/S6 counts are null. S1/S3/S5 have zero opportunities in this GET-only example. Output status PARTIAL. Synthetic examples are not confirmed product bugs.
`python -I` is supported as well.

## Pipeline interface

Three separate commands:

```text
python tools/natchan-box-v009/natchan.py derive --contract contract.json --output knowledge.json
python tools/natchan-box-v009/natchan.py freeze --contract contract.json --knowledge knowledge.json --output freeze.json
python tools/natchan-box-v009/natchan.py analyze --request request.json --output new-analysis-directory
```

Input schema is intentionally distinct: `natchan-semantic-request/1`.
Legacy `natchan-request/1` requests remain supported by v008, not by this new independent track.
Paths are relative to the request file, never the shell working directory.
Outputs must be new; existing output directories are refused. Contract and knowledge are read only.

The request requires `run.id`, `run.product`, `run.tool`, `run.start_state`, contract, knowledge, freeze and evidence.
`start_state` is `fresh_snapshot`, `accumulated` or `unknown`; it is retained as declared metadata, not inferred.
Optional `run.product_version` is **caller-declared**, not a confirmed observed server version.
Metadata provenance makes this distinction explicit. No version-specific known-bug credit is awarded.
The copied contract must be the registered tool contract. This milestone hashes its exact bytes;
it does not yet validate a normalization chain back to the original server contract.

Formats: `http-jsonl`, `journal-jsonl`, `observer-tool-jsonl`, `har`, `none`. `none` must omit `traffic`.
For evidence with no HTTP capture, use `none`: every semantic count is null, including S7.
It is not equivalent to an empty but valid captured stream.
The `server_log` field is optional and names a structured JSONL server log.
There is no configuration field for producer profiles, JS, stories, known-bug catalogs or per-tool semantic rules.

## Raw traffic and server log

HTTP JSONL records use `method`, `path` or `url`, `status`, optionally `input`, `response`,
`request_headers`, `response_headers` and `request_id`. Bodies may be JSON values.
Journal JSONL uses the same fields with `category: research`; other categories are counted as ignored.
Raw non-HTTP oracle rows, including RT/ATOM/REF/DIV verdicts and STORY_CHECK, never provide a judgement.
This phase does not extract independent evidence from their auxiliary reads.

HAR requires `log.version: "1.2"` and `log.entries`. Source locators use the original entry index.
JSONL locators use original 1-based physical line numbers. Every locator contains the exact traffic SHA256.
Secrets should be redacted before delivery. This judge does not emit raw URLs, headers, bodies or log messages.

Server log JSONL records: `request_id`, `message` or `error`, optionally `method`, `path`, `status`.
Only an ID unique in both HTTP and structured log records can join; supplied method/path/status must agree.
No timestamp or adjacent-line join is attempted. Signature hashes normalize numeric tokens/UUIDs mechanically.
No semantic interpretation of the message, product-specific signature or causal attribution is claimed.
Unjoined 5xx counts are reported. Plain-text logs currently remain unjoined, not proof that no server errors occurred.

## Outputs

| File | Meaning |
|---|---|
| knowledge.json (derive command) | Contract-bound partial context; JSON pointers, constraints, candidates and ambiguities |
| freeze.json (freeze command) | Engine source hashes, contract hash and exact knowledge hash |
| verdicts.jsonl | S7 per exchange, plus applicable S1/S3/S5 checks; exact evidence references and comparison outcomes |
| findings.json | Separate violation/policy-observation symptom groups, occurrences and representative verdict IDs; distinct bug count null |
| coverage.json | Supported/unsupported classes, counts, abstentions, ingestion and unjoined-error counts |
| provenance.json | Input and engine hashes; declared run metadata; no producer verdicts used |
| diagnostics.json | Exit/reason; no raw exceptions or source paths |
| report.md | Scope and interpretation of this partial development milestone |
| result.json | Final completion marker, status, exit and output SHA256 hashes |

Canonical report bytes contain no wall time or absolute local paths. The same inputs yield identical report bytes
across different output directories. Changing producer annotations changes the raw source hash, but never the
semantic decision; exact evidence IDs appropriately change with those source bytes.
Run ID is hashed. Product/tool/version metadata must be public-safe labels; inspect contracts and raw evidence separately
before sharing. This is not a general redaction guarantee for arbitrary caller-provided metadata.

## Limits and exits

| Exit | Meaning |
|---|---|
| 0 | Processed; currently always PARTIAL, never proof of no defects |
| 2 | Invalid inputs, missing files, changed inputs or freeze drift |
| 3 | Unsupported interface, format or documented resource limit |
| 4 | Unexpected internal defect |

JSONL: up to 512 MiB, 16 MiB per physical line, 100,000 HTTP exchanges. Streaming judgement does not retain the traffic.
HAR: up to **64 MiB**, at most 100,000 entries; larger HAR is explicitly refused with exit 3,
`HAR_DOCUMENT_LIMIT_64_MIB_USE_JSONL`. Convert outside this milestone to documented JSONL if needed.
Contracts, knowledge, request and server log each have a 32 MiB cap. JSON nesting beyond 128 is invalid.
Derivation caps: 100,000 schema-node visits, 10,000 operations and 32 MiB of derived knowledge;
exceeding a cap returns exit 3. Recursive schema edges are recorded as unknown rather than expanded repeatedly.
YAML contracts, archive/nested ZIP input and native RESTler text logs are not yet supported in this route (exit 3).
Use the existing v008 interfaces for those supported legacy workflows. No silent fallback to v008 occurs.

After analysis starts, a failure removes partial verdicts/findings and leaves only diagnostics and a FAILED result.
Invalid request envelopes and existing output targets are rejected before output creation; the CLI writes a reason to stderr.

## Research protocol and next gates

Register the exact engine commit, original/tool contracts, normalization record, derived knowledge and freeze **before**
prospective evidence exists. Hash checking cannot prove chronology or that a system was unseen.
Any reanalysis of old evidence is explicitly post hoc. No new held-out evaluation is claimed here.

The requirements document remains unchanged. Proposed clarifications and the remaining implementation are in
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md). The snapshot is the supplied requirements, not evidence of implemented coverage.


## New in 009-dev.2: controlled state checks

See [SEMANTIC_RULES.md](SEMANTIC_RULES.md) for exact rules and limits.
To enable cross-exchange S1/S5 checks, the capture must explicitly declare:

```json
"capture": {"complete": true, "exclusive": true, "ordering": "serial"}
```

This object is inside `evidence`. These are capture facts, not tool-specific rule settings. Do not set them true merely
because a tool ran in isolation from this analyzer. The producer must establish complete capture, no outside writers
and serial requests. An overlapping/out-of-order recorded interval overrides a false serial declaration.
The analyzer cannot independently prove completeness or isolation from captured traffic alone.

Every state-bearing record must have a stable `actor` (or an unredacted recorded authorization credential from which
an opaque scope is computed) and a captured reset `epoch`. Optional `case_id` separates retained sequences.
Never put scenario meanings into these fields: they are opaque scopes, not rule selectors.
Missing metadata yields abstention. `started_utc` and `ended_utc` are optional timezone-aware intervals;
HAR uses `startedDateTime` and `time`. Without intervals, serialization remains a declared capture assumption.

Cross-exchange rules currently bind only PUT/PATCH to a GET 200 object at the same item route, with common declared
scalar fields. Different actors, origins, IDs, reset epochs or sequences cannot supply each other's snapshots.
Any intervening mutation invalidates pending comparisons and cached preimages, including mutations of another resource.
Read-only/write-only, ambiguous, mismatched and complex fields are excluded. Numeric/date-time equivalence is handled;
no language model interprets descriptions or transformations.

S1 mismatches are candidates conditional on the generic persistence assumption printed in the verdict. Optional missing
read fields are policy observations; required missing read fields are candidates. S5 reports unchanged, partial,
committed_despite_error or other_state_change, but never invents an atomicity promise. S3 uses only its documented scalar
subset, not full schema or business validation. See coverage for checked/unsupported fields and preconditions.

State retention is bounded to 128 snapshots, 64 KiB per state body and one pending mutation. Evictions and budget
abstentions are explicit. Raw bodies/principal names are never copied into semantic verdicts.
Old dev.1 freezes/knowledge must be regenerated for dev.2; the original dev.1 commit remains reproducible.

## Retrospective Library transport acceptance

The exact old baseline archive `mutants-neutral-v008-20261020-131134-37312-review.zip`
(SHA256 `41d2e1b8369d1d552a0e1e5b55181b9f1a3c38dd0ebd2d5bd4a719cf57c90b86`) was reprocessed.
This is development/post-hoc evidence, not a new run or held-out evaluation.

`observer-tool-jsonl` accepts the legacy recorder's `role: tool` request/answer rows, maps `request` to `input`,
and ignores all other rows. In particular, observer GETs and producer `verdict` rows are **not** tool traffic.
Their labels, seeded-bug switches and outcomes cannot supply the judge's answer. Exact original line numbers remain.

| Capture | Tool exchanges | S7 5xx candidates | S3 consistent subset checks | S3 not evaluable |
|---|---:|---:|---:|---:|
| RESTler | 7,634 | 7 | 2,366 | 603 |
| EvoMaster | 74,168 | 0 | 42,120 | 0 |

RESTler's seven 5xx are one symptom group on `GET /loans`, not seven distinct bugs. Eight RESTler exchanges have
no server answer and receive S7 abstentions. S3 found no stored-bound violations in these captures; valid-input subset
counts do not mean the whole operation or business behavior was correct.

The Library contract has no PUT/PATCH item updates, so S1/S5 have no applicable opportunities in this milestone.
S2/S4/S6 and seeded Library business invariants are not covered by this new route. This does not replace v008's
existing Library domain provider or its separate 44-observation compatibility check. No new native tool bug-detection
credit or new seeded-bug detection is claimed.

Reproduce in a fresh output directory:

```powershell
python .\tools\natchan-box-v009\validate_library_archive.py --archive "$env:USERPROFILE\Downloads\mutants-neutral-v008-20261020-131134-37312-review.zip" --output C:\experiment\library-v009-posthoc
if ($LASTEXITCODE -ne 0) { throw 'Retrospective acceptance failed; inspect its results.' }
```

The utility stores raw extracted inputs locally; do not share them without the study redaction procedure.
The committed `LIBRARY_RETROSPECTIVE.json` contains only safe aggregates, exact source hashes and symptom groups.

## Validation of this checkpoint

90 development tests pass, including six real loopback HTTP modes and the 90,000-exchange stress case.
All 275 operational v008 tests pass unchanged. See `VALIDATION.json` and `LIBRARY_RETROSPECTIVE.json`.
No Windows PowerShell or new Gitea/Vikunja live run or held-out evaluation is claimed.
The legacy ingestion counter `ignored_non_http` means records outside the selected tool/research stream;
it includes raw observer HTTP readbacks as well as producer verdict/metadata rows, not only non-HTTP records.
