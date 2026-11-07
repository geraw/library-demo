# Natchan v009: capabilities, changes, validation and operation

**Version:** 009-dev.9. **Date:** 2 November 2026.  
**Engine provenance:** see `tools/natchan-box-v009/VALIDATION_DEV9.json` for exact code hashes.  
**Scope:** independent offline analysis of retained REST traffic and its API contract.

## 1. Purpose and current conclusion

Natchan is an offline test oracle: it examines recorded requests and responses, relates them to the API contract, and reports errors, semantic contradictions, conditional observations and reasons why a check could not be evaluated. It does not generate test scenarios or send requests to the system under test (SUT). The same independent analysis path accepts traffic produced by Provengo, EvoMaster and RESTler; a tool name does not choose the semantic rules.

Version 009-dev.9 is a bounded research implementation, not a universal business oracle or a drop-in replacement for every v008 integration. It can support a common evaluation layer for the four Library configurations, but equal analysis rules do not imply equal test coverage. Comparisons must separately report server calls, evaluable opportunities and findings.

**Latest acceptance result:** all B1 (10), B2 (8) and B4 (19) detection request IDs match the dedicated Library oracle on the unchanged original traffic, with no extra target findings. The baseline remains clean. B1/B2 are conditional observations; B4 is a filter violation. Synthetic repaired-response controls remove all 37 detections. See [dev.9 validation](../../tools/natchan-box-v009/LIFECYCLE_HISTORY_DEV9.md) for scope, controls and remaining real-system parity gaps.

## 2. Inputs and processing

1. **Contract derivation.** `contract_context.py` derives operations, schemas, scalar constraints, declared responses and bounded semantic policies from OpenAPI/Swagger JSON. Provenance points to contract locations. Narrow affirmative descriptions can support selected policies; arbitrary natural-language business requirements are not understood.
2. **Freeze.** `natchan.py` records contract, derived knowledge and analyzer code hashes. Analysis verifies the freeze and recomputes knowledge from the contract. Handwritten product profiles are not silently treated as contract facts.
3. **Evidence normalization.** `traffic.py` reads supported JSONL, observer journals or HAR. It retains evidence locations and request ordering/scope metadata. Infrastructure errors and timeouts are not server responses; authentication records are not product request counts in the story adapter.
4. **Independent judgment.** The checkers compare responses and eligible state sequences. Mutation labels, scenario descriptions, known bug IDs and producer verdicts are not used to decide the result.
5. **Reporting.** Findings, per-check verdicts, coverage, abstention reasons and provenance are written into a new output directory. Original traffic, baseline results and samples remain unchanged.

Sequence checks require sufficient identity, ordering and isolation evidence. Capture declarations are inputs supplied by the recorder, not facts independently proved by the analyzer. Story and attempt identifiers serve only as opaque boundaries; they do not encode expected outcomes.

## 3. What is checked

| Family | Implemented subset | Interpretation and main limit |
|---|---|---|
| S1: read-back consistency | Eligible scalar write/read comparisons; structural create/delete/read lifecycle | Query uncertainty and missing policy can reduce a contradiction to an observation. Intervening writes can invalidate the comparison. |
| S2: path consistency | Bounded create/update input-class and identity-linked readback comparisons | Different statuses are not automatically proof of a business defect. |
| S3: constraint conformance | Scalar types, enums, bounds, lengths and supported required fields | Accepted invalid input without verified storage is an observation. This is not full JSON Schema validation. |
| S4: reference integrity | Observed references to absent resources; bounded copy-reference correspondence | Name/shape correspondence is a hypothesis. A 404 may reflect permissions. Enum fields are excluded from inferred foreign keys. |
| S5: effects after failure | Eligible before/after scalar state; bounded rejected-create evidence | Partial effects do not prove atomicity violation without a relevant guarantee. Missing preimages cause abstention. |
| S6: views and collections | Explicit conjunctive filters; bounded collateral deletion, nested membership, aggregate and scaling observations | Returned items can violate a filter without proving collection completeness. Aggregate/scaling meanings may remain hypotheses. |
| S7: response errors | Server 5xx and undeclared statuses, operation attribution and symptom grouping | A 500 occurrence is not a distinct root cause. No automatic causal or severity claim. |

Supported families contain restricted checks, not complete coverage of those semantic categories. Bounds on retained state, body size and join windows deliberately trade coverage for bounded resource use and more explicit uncertainty.

## 4. Reading the results

| Result | Meaning |
|---|---|
| `violation` | Contradiction under the check's stated evidence and assumptions. Inspect its contract provenance and semantic status before claiming a confirmed product bug. |
| `policy_observation` | Suspicious behavior whose business guarantee or visibility semantics are not established. Requires triage. |
| `consistent` | This particular evaluated property held on this evidence. It does not certify the SUT. |
| `not_evaluable` | An opportunity lacked evidence or exceeded supported semantics. It is not a pass or an undetected-bug count. |

`findings.json` groups symptoms; `verdicts.jsonl` preserves individual judgments; `coverage.json` provides denominators, ingestion counts and abstention reasons. `provenance.json` and the freeze identify the analyzed inputs and engine. `result.json` records processing outcome. Successful v009 analyses currently report `PARTIAL`; this is a capability limitation, not necessarily execution failure.

Do not add occurrences across properties and call the sum “distinct bugs.” A single request can participate in several checks, and repeated findings can share a cause. Do not equate Provengo test failures with analyzer findings: a test can fail before collecting the state evidence a semantic oracle needs.

## 5. What actually changed from v008

The comparison is based on the checked-in v008 README, CHANGES and implementation structure. It is not a head-to-head accuracy experiment on the new upload.

| Aspect | v008 already provided | v009 independent route |
|---|---|---|
| Shared HTTP analysis | A tool-neutral judge and multiple raw/native adapters | Retains tool-neutral analysis with a separate contract-first request interface |
| Semantic analysis | Deleted/stale references, projections, configured aggregates, scaling and copy checks | Bounded independently derived checks and explicit contract-vs-hypothesis distinctions; semantic analysis itself is not new |
| Context source | Product-specific metadata/profiles, recorded bindings and legacy providers | Derived contract knowledge, provenance and freeze; no v008 product catalog imported by the independent judge |
| Isolation and provenance | Actor/reset/case controls, source hashes, freeze and evidence controls | Explicit capture requirements plus current story/attempt boundaries and transport-gap handling |
| Server logs | Configured signatures and conservative ID/optional time joins | Unique structured request-ID joins; narrower scope, no root-cause proof |
| Interface | `natchan-request/1`, legacy pipeline/ZIP/native adapters | `natchan-semantic-request/1`, derive/freeze/analyze; dedicated Library replay and story-package readers |
| Coverage | Broader legacy adapter and configured-product support | Greater independence from producer semantics in this route, but incomplete functional parity |

The v008 release documented 275 tests, including inherited tests. The current v009 suite has 204 analyzer tests plus 13 benchmark tests. These totals cover different code and scopes; their size is not evidence that one release is better.

### Specific dev.8 repairs

- Additional query parameters no longer suppress an explicitly declared, comparable filter predicate. Duplicate known predicates and unsupported values still cause abstention.
- Undeclared query parameters can permit conditional lifecycle tracking on eligible operations. They do not establish query semantics or justify a proven lifecycle violation.
- Different story attempts cannot provide each other's pre/post state. Infrastructure failures break continuity.
- Story `pass:null` values remain observations, and checks from incomplete/setup-failed stories are not promoted to successful product tests.
- Explicit enums are not inferred as foreign keys. Empty internal-reference sets do not demonstrate a broken copy.

## 6. Validation: what was actually exercised

| Validation layer | Result | What it does not establish |
|---|---|---|
| Analyzer regression suite | 204 tests passed | General correctness on arbitrary APIs |
| Library benchmark suite | 13 tests passed | Successful completion of all four native campaigns |
| Focused Library query acceptance | B1/B2 conditional observations, B4 violation; matching baselines clean | Recovery in long interleaved traces |
| Retained real-system witnesses | 14 observations reproduced: Mealie 9, wger 3, Vikunja 2; 14 repaired controls suppress the corresponding findings | 14 distinct confirmed bugs; controls are synthetic repaired evidence |
| Gitea G014 regression | Six 500 state-effect witnesses, four 4xx observations and ten rollback controls retained | A universal atomicity guarantee |
| Cycle 5 direct reproductions | Eight 500 occurrences from Homebox/Paperless; eight controls without 500 | Eight independent root causes or semantic discoveries |
| Cycle 5 Label Studio journals | Two journals, each 38 product HTTP records; 67 infrastructure-error records separated; no semantic/policy/500 findings | Successful business exploration: many stories failed setup; one journal is an extra run, not a protocol replicate |

Cycle 5's recorded triage identifies six root causes across the direct reproductions. It also identifies tool false positives: Paperless DELREF treated enum values as references, and Homebox COPY compared empty reference sets. These cannot serve as positive bug-detection targets. Full Homebox/Paperless story ZIP replay is not claimed from the direct reproduction files.

### Latest original Provengo replay

Input: `provengo-raw-20261102-193151-793.zip`. Every file hash listed in its evidence manifest was verified before analysis. The original contract and recorder declarations were used. No SUT requests or resampling occurred.

| Cell | Retained HTTP exchanges | Prior dedicated Oracle occurrences | dev.9 semantic occurrences | dev.9 policy observations |
|---|---:|---:|---:|---:|
| Baseline | 16,324 | — | 0 | 0 |
| B1 | 3,358 | 10 | 0 | 10 |
| B2 | 14,619 | 8 | 0 | 8 |
| B4 | 16,324 | 19 | 19 | 0 |

B4 has 168 evaluated filter checks: 19 contradictions and 149 consistent results. The baseline has 168 consistent filter checks. All 37 detection request IDs match the independently recomputed reference oracle, not just the numerical totals. All four cells have zero 5xx findings. Ten non-HTTP records per cell are excluded from HTTP counts.

The baseline comes from run `benchmark-v001-20261101-233425-14e824`; the mutants come from `benchmark-v001-20261102-040359-d5a33d`. These different runs are explicitly retained rather than described as one newly executed campaign.

Actual query names include `description`, `id`, `q`, `userId`, `bookId` and `loanNumber`. The presence of such names does not prove they are semantically irrelevant.

### How B1/B2 were recovered

The checker now retains per-resource lifecycle hypotheses. Contract-declared integer identifiers are canonicalized, including leading zeros; string IDs are not. Unrelated reads do not erase history. Rejected and other-resource writes retain the hypothesis but force conditional classification because their side effects are not proven absent. Successful same-target changes, ambiguous creation, unknown successful actions, 500s, 202s, missing responses and scope changes remain barriers. The analyzer never consumes Oracle labels; the acceptance harness compares outputs afterward.

The original B1/B2 detection gap is closed on this evidence. Generic parity with all producer checks remains incomplete: wger's percent-preview rounding and Mealie's standalone inverse-action roundtrip are explicit gaps, not successful checks. This distinction is essential when reporting the research result.

## 7. Running from the existing checkout

Use PowerShell from the root of the existing `library-demo` checkout. No clone is needed. The analyzer requires Python 3.10+; the independent engine uses the standard library. Benchmark tests additionally need the benchmark's installed dependencies. These instructions do not require a running SUT, Java, RESTler or EvoMaster for offline replay.

### Update

```powershell
git fetch origin refs/heads/master:refs/remotes/origin/master
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
git merge --ff-only refs/remotes/origin/master
if ($LASTEXITCODE -ne 0) { throw 'Update failed; inspect local Git state.' }
git rev-parse HEAD
```

### Reanalyze existing Library runs from all four configurations

```powershell
& .\library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe `
  .\tools\natchan-box-v009\replay_library.py `
  --runs-root .\library\benchmark-v001\runs `
  --contract .\library\benchmark-v001\openapi.json
if ($LASTEXITCODE -ne 0) { throw 'Replay failed; inspect the printed diagnostics.' }
```

The script discovers retained `http.jsonl` files, creates a new `analyzer-replay-*` directory, derives and freezes knowledge, and reuses capture declarations only from the matching cell's `natchan-request.json`. It writes `replay-summary.json`. A missing configuration remains missing; compact reports cannot reconstruct discarded traffic.

To reproduce the four-cell analysis above, extract the supplied ZIP into a new directory and pass that directory as `--runs-root`, and its `openapi.json` as `--contract`. Use a new `--output` directory if supplying one explicitly.

### Analyze a real-system story package

```powershell
python .\tools\natchan-box-v009\review_stories.py `
  --evidence 'D:\evidence\system-stories.zip' `
  --contract 'D:\evidence\matching-openapi.json' `
  --output 'D:\evidence\analysis-dev8-new'
if ($LASTEXITCODE -ne 0) { throw 'Story analysis failed.' }
```

Replace the example paths. The contract must match the package's recorded hash. `story-review.json` separates the producer's final-attempt checks from independent raw-journal analysis. It does not turn story labels into oracle rules.

### Generic integration

Create a request file with schema `natchan-semantic-request/1`, run metadata, paths to contract/knowledge/freeze, evidence format and traffic path. Use `tools/natchan-box-v009/examples/request.json` as the starting point; it is a synthetic example, not a claim of capture completeness. Paths inside a request are relative to that request file.

```powershell
python .\tools\natchan-box-v009\natchan.py derive --contract contract.json --output knowledge.json
if ($LASTEXITCODE -ne 0) { throw 'Derivation failed.' }
python .\tools\natchan-box-v009\natchan.py freeze --contract contract.json --knowledge knowledge.json --output freeze.json
if ($LASTEXITCODE -ne 0) { throw 'Freeze failed.' }
python .\tools\natchan-box-v009\natchan.py analyze --request request.json --output analysis-new
if ($LASTEXITCODE -ne 0) { throw 'Analysis failed.' }
```

Only declare complete, exclusive, serial capture when the recorder actually established it. Supported evidence formats include `http-jsonl`, `journal-jsonl`, `observer-tool-jsonl` and `har`; there is no automatic legacy-v008 request conversion.

### Regression tests

```powershell
python -m unittest discover -s .\tools\natchan-box-v009\tests -q
if ($LASTEXITCODE -ne 0) { throw 'Analyzer tests failed.' }
& .\library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe `
  -m unittest discover -s .\library\benchmark-v001\tests -q
if ($LASTEXITCODE -ne 0) { throw 'Benchmark tests failed.' }
```

For reproducibility, retain the Git commit, engine hashes, exact contract, original HTTP and recorder metadata, input hashes, knowledge/freeze, result files and exit status. Report HTTP exchanges separately from sampling steps and native tool counters. Report evaluated opportunities separately from all recorded requests.

## 8. Source map and remaining acceptance gate

Primary implementation and evidence sources in this repository:

- `tools/natchan-box-v008/README.md` and `CHANGES.md`: prior capabilities and documented validation.
- `tools/natchan-box-v009/natchan.py`, `contract_context.py`, `traffic.py`: interface, derivation, normalization and provenance.
- `lifecycle.py`, `collection_semantics.py`, `relational_observations.py`, `state_semantics.py`, `create_update.py`, `rejected_create.py`: bounded semantic rules.
- `STEP2_ACCEPTANCE.md`, `STEP34_ACCEPTANCE.md`, `QUERY_AND_STORY_EVIDENCE_DEV8.md`, `VALIDATION_DEV8.json`: milestone validation; older statements about missing original Provengo traffic are superseded by section 6 of this guide.
- `EVIDENCE_FORMATS_STORIES.md`: supplied evidence-format specification, retained verbatim.
- `docs/analyzer/PROVENGO_DEV8_REPLAY.json`: machine-readable results and input hashes for the latest uploaded evidence.

The next acceptance gates are full retained mutant replay for the other Library configurations and explicit handling of the remaining real-system producer semantics. The current repair closes B1/B2 on the supplied traces and preserves the established real-evidence regressions; it does not justify a claim of a complete generic business oracle.
