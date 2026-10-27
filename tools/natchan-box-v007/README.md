# Natchan Box v007 — generic projection, move and operation analysis

Offline Python 3.10+, standard library only; a full `geraw/library-demo` checkout is required. Base release: v006 at `5974f32122a990cd5b77a7006f32e7576a9e8575`. This is a new directory/release. v006, older analyzers, producer code, frozen toolkit tags and experiments are unchanged. No SUT requests or new tests against a live server are launched by this analyzer.

## Generic engine and product metadata

The engine implements reusable rules over retained HTTP exchanges. Product bindings live in JSON:

| Component | Responsibility |
|---|---|
| `story_semantic_rules.py` | Source/actor/identity binding; projection update/delete/move comparisons; enum operation evaluation; failed-precondition analysis |
| `semantics/*.json` | Contract-bound routes, entities, references, projection places, operator meanings and explicit rounding assumptions |
| `story_catalog.json` | Generic pattern predicates; no product names, expected event counts or particular test identifiers |
| `story_profiles.json` | Product aliases and retrospective candidate bug-ID links, separate from rule detection |
| `derive_story_semantics.py` | Deterministic metadata extraction from OpenAPI plus a producer story IR; no SUT access |

A new product using a supported pattern needs metadata, not product-specific engine code. A genuinely new semantic family may need a new generic rule. Generated relations and metamorphic hypotheses do not themselves establish intended product behavior. Numeric ID collisions are scoped to the declared entity/place; actor, successful mutation, exact resource path, positive preimage and response acknowledgement are checked. Unknown semantics remain explicit gaps.

## Run an existing immutable ZIP

Create `analysis-request.json` beside the ZIP:

```json
{
  "schema_version": "natchan-request/1",
  "run": {"id": "wger-stories-run", "tool": "provengo", "product": "wger", "product_version": "unknown"},
  "evidence": {"adapter": "toolkit-v1", "archive": "stories.zip"}
}
```

Use `unknown` only when observed version evidence is missing, as in the retained stories packages. The login package `v1-vikunja-login-20261025-125344.zip` records `v2.6.0` in ENV; its request must specify `v2.6.0`. Request metadata never supplies a missing observed version. The producer target alias `mealie-pg` maps to canonical product `mealie`, without proving database identity from that label.

```powershell
python -m unittest discover -s .\tools\natchan-box-v007\tests -q
python .\tools\natchan-box-v007\natchan.py --request 'C:\experiment\analysis-request.json' --output 'C:\experiment\analysis-v007-001'
$analysisExit = $LASTEXITCODE
```

Output must be a fresh directory. Standard invocation and `python -I ...` are supported; the latter explicitly binds this release's own module path. The optional `Invoke-Natchan-Box-v007.ps1` wrapper throws for nonzero exits. Pipelines requiring the numeric exit code should invoke Python and retain `$LASTEXITCODE` immediately.

## Evidence interface and outputs

The existing `natchan-request/1` and adapter name `toolkit-v1` are retained. v1 model/campaign/login/baseline inputs remain supported. Stories input is detected via `result_stories.json`, recorded `gateway-journal.jsonl` and optional native logs. A run ZIP, one folder prefix, or nested `review_stories.zip` is supported. If both outer and inner result copies exist, they must agree. Full original ZIPs may contain more evidence than Git-retained subsets.

The step parser is corrected: `..._42 move N1_0 ...` belongs to step 42 of its story, not step 0 of an invented story name. Clean restarts at step 1 can be evaluated as separate attempts by the new semantic rules; unresolved duplicate/non-monotonic steps remain unqualified. No evidence is paired across attempts. Older supported rules remain conservative where their attempt association is unresolved.

Outputs: `result.json` (final marker), `findings.json`, `coverage.json`, `provenance.json`, `diagnostics.json`, `report.md`, successful `analysis.json`. Findings include `semantic_checks` with recomputed expected/observed values, source witnesses and a `classification_role`. A failed stale-reference precondition is `test_precondition_failure`, not a confirmed product bug. Behavior signatures remain candidates. Coverage records missing native/server logs, versions, manifests, semantic hypotheses, rounding uncertainty and unresolved bindings. Input/configuration hashes are retained.

| Exit | Meaning |
|---|---|
| 0 | Analysis completed; COMPLETE or PARTIAL does not imply absence of findings |
| 2 | Invalid request or explicitly contradictory/invalid supported evidence/configuration |
| 3 | Explicit unsupported interface, format or semantic-policy vocabulary |
| 4 | Unexpected engine defect |

## New semantic rules

- **PROJ-NEST / UPDATE:** a successful acknowledged field update differs from a later projection that was positively qualified before the update.
- **PROJ-NEST / DELETE:** a child remains in the qualified projection after an accepted DELETE. This does not establish the internal persistence or cache cause.
- **PROJ-NEST / MOVE:** the first read of each qualified old/new view after an accepted, acknowledged relation change contradicts the configured parent membership hypothesis. Nested places, grouped root arrays, full-body POST updates and alternate array shapes are handled. Both the old child's placement and destination parent's preimage are required. Later writes end the comparison window.
- **OP-ENUM:** operator meanings are mapped from declared descriptions, not enum position. Accepted operand configurations are applied in iteration order with Decimal arithmetic. Absolute and percent steps, replacement controls, hold iterations and explicit per-operation rounding are supported. Tolerated display quantization is explicit metadata, not a hidden product exception. Unknown operators, ambiguous iteration/output bindings and missing controls are not promoted to arithmetic findings.
- **STALE / 5xx context:** scalar and array/object references use declared metadata, with pre-read, successful deletion, target absence and write witnesses. Other changed fields are exposed; causality is never inferred from sequence alone.
- **STALE / failed precondition:** when the snapshot and write do not contain the deleted reference, the report explicitly rejects that reference-based explanation of the 5xx. The server error remains visible separately.

Existing DELREF, STALE, AGG, native contribution/copy measurements, toolkit/v1 and login rules are preserved. Raw HTTP and weaker retained producer measurements remain distinct. Producer `pass`, `failed_checks`, NOTE text and reported known bug IDs are not accepted as the analyzer's answer.

## Configure another product

See `SEMANTIC_CONFIG.md` and `schemas/story-semantics.schema.json`. Supply `story-semantics.json` inside the run ZIP, or an external file through `configuration.story_semantics`. Bundled profiles are a convenience for three known contract hashes; they are never silently applied to another contract revision. A hash mismatch disables that profile and produces a gap. No server version is inferred from a contract hash.

## Validation and research scope

`VALIDATION.json`, `REANALYSIS.json` and `STORIES_REANALYSIS.md` record tests and reanalysis of 29 exact Git-retained evidence subsets at producer commit `62ff20a9da589e3b4ac18189e6f8f7f46f4ccde8`. Source member paths, Git blob IDs, SHA256 values, counts and semantic comparisons are recorded without local filesystem paths. This is retrospective development/regression validation, **not a held-out bug-discovery experiment**. Candidate links W-F3/W-F4/V-F1/W-F5 were added after these behaviors were known. Frozen rules must be evaluated on future held-out evidence before claiming generalization.

Notable G-F1 result: the retained snapshot and request both have empty labels; `assignee` is the other changed field. v007 reports a failed reference precondition and keeps the 5xx. It neither confirms a label-deletion cause nor proves a different root cause. The known GIT-C1 behavior is a possible explanation requiring separate evidence.

The original 34 uploaded story ZIPs and original login ZIP were not available for full byte-for-byte acceptance here; the producer's v006 acceptance report is not relabeled as a v007 run. The 18 original model archive rechecks are likewise producer-reported v006 acceptance. Windows PowerShell and producer orchestration were not executed. RESTler ingestion is outside this release; existing baseline adapters are preserved.

## Reproduce the repository-subset analysis

With a full producer Git clone containing the pinned commit:

```powershell
python .\tools\natchan-box-v007\validate_repository_stories.py --producer-repo C:\work\temp\vikunja_study --output C:\experiment\stories-v007-recheck
```

The destination must not exist. The script reads pinned Git object bytes, excludes NOTE summaries, creates deterministic subset ZIPs, runs the analyzer and writes a machine-readable summary. The detailed producer integration handoff is `HANDOFF_PROMPT_HE.md`. Local outputs may contain paths/input data; apply the research pipeline's redaction before sharing them.
