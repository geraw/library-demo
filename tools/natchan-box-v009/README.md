# Natchan Box v009 — independent contract context (development milestone 1)

**Version: `009-dev.1`, not a production replacement for v008.** Python 3.10+, standard library only.
Based on repository commit `6310af7baecc25fc46692d1127c80dbc1da4247d`.
The operational v008 directory, branch, request interface, product catalogs and existing integrations are unchanged.
Keep using v008 in established pipelines until v009 passes the later acceptance gates.

This is the first implementation of the supplied [research requirements](RESEARCH_REQUIREMENTS.md),
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
4. Implements the **S7 status-only subset**: exact operation attribution, 5xx candidates, undeclared-status
   candidates, explicit abstention, symptom grouping and unique request-ID log correlation.
   Declared 5xx remain error candidates. Other declared statuses are consistent **only for this status check**.
   An error candidate does not prove a product defect, root cause, severity or business-rule violation.
5. Emits deterministic evidence-linked outputs and numeric exit codes. No SUT requests are sent.

The independent route imports **no v008 runtime module or product catalog**. The earlier work remains available
in the same checkout, but producer-derived profiles and known-bug catalogs are not loaded in this route.

## Explicit capability limits

| Class | Milestone 1 |
|---|---|
| S1 read-back consistency | Not implemented; counts/opportunities null |
| S2 path consistency | Not implemented; counts/opportunities null |
| S3 constraint conformance | Constraints retained in knowledge; judgement not implemented |
| S4 reference integrity | Ambiguities retained; judgement not implemented |
| S5 failure atomicity | Not implemented; counts/opportunities null |
| S6 placement/view consistency | Not implemented; counts/opportunities null |
| S7 error answers in context | Status checks, operation matching, symptom groups; coarse request-body shape only |

S7 does not infer invalid references, field-level input classes, multipart causes, side effects or business meaning.
Without a unique join it does not infer a server error's cause. Same-looking symptoms need not share a root cause.
All successful analyses currently have status **PARTIAL**, including clean controls.

This milestone inventories entity candidates from GET response schemas, but does not yet prove their identities
or derive an executable entity graph. Operation names/descriptions are not interpreted as business rules.
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
S1–S6 counts are null. Output status PARTIAL. Synthetic examples are not confirmed product bugs.
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

Formats: `http-jsonl`, `journal-jsonl`, `har`, `none`. `none` must omit `traffic`.
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
| verdicts.jsonl | One independently computed S7 verdict per captured exchange; exact evidence references |
| findings.json | Symptom groups, occurrence counts and representative verdict IDs; distinct bug count null |
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
