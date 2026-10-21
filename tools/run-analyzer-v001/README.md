# Run analyzer v001: tool adapters × product profiles

This is the results analyzer, not the JS generator and not a generator validator. It reads retained outputs from Provengo, RESTler and EvoMaster, reports their native alerts and HTTP anomalies, and optionally asks the separate shared semantic checker to evaluate product-specific rules. It never runs generators, sends HTTP requests or changes a SUT.

## Two independent extension axes

- `native_adapters.py`: tool-specific artifact readers. Adding a tool does not require modifying product rules. An unregistered tool still retains its run identity and can use external semantic checking; its native metric stays unknown until an adapter is added.
- `../semantic-checker-v001/checker.py`: product/version-specific semantic profiles. Adding a product profile does not require modifying Provengo/RESTler/EvoMaster artifact readers.
- `analyze_runs.py`: tool/product-independent run inventory, HTTP anomaly summary, execution evidence, input hashes and JSON/CSV reporting. Every run is preserved; seeds/runs are not silently collapsed into the latest one.

The earlier semantic-checker package is a component of this analyzer. Its initial integration alone was not the full historical three-tool results analyzer.

## Historical code actually found

`openapi_to_sbt_provengo_four_systems_v38.zip` includes:

- `experiments/netbox_a2a/collect_a2a_results.py`: collects all three tools' run metadata and separates native faults, sequence-local semantic confirmation, campaign reachability and hidden-trigger diagnostics. A frozen original is retained under `history/`.
- `experiments/netbox_a2a/evaluate_netbox_a2a_trace.py::parse_native`: extracts EvoMaster potential-fault counts, RESTler bucket-file counts and Provengo FAIL log mentions.
- Per-product semantic evaluators and sequence-trace preparation scripts.

The historical collector was tied to NetBox A2A, selected latest tool/input-mode runs, and asserted input parity without rechecking files. It also defaulted missing scores in some fields. The new analyzer reuses the native metric meanings and semantic profiles but does not carry those assumptions forward: missing is unknown, every run survives, and optional input hashes are measured. This is an initial generalization, not a claim that a complete universal analyzer was already present as one file.

## Run now on the existing work-machine Library archive

```powershell
& .\tools\run-analyzer-v001\Invoke-Run-Analyzer-v001.ps1 `
  -LibraryArchivePath '.\library\ess-experiment\runs\java-fixed-split-v011-20261021-094721-5216-review.zip'
```

The analyzer reads all three arms, retains failed tests separately from external candidates, and identifies native failed cases that passed the healthy control. Such correlation does not automatically turn a candidate into a unique confirmed business bug. Output paths are printed as `RUN_ANALYSIS_JSON` and `RUN_ANALYSIS_CSV`. Existing files are never overwritten.

Python alternative:

```text
python tools/run-analyzer-v001/analyze_runs.py --library-archive PATH --output NEW_REPORT.json
```

## Analyze mixed tools and products

Create a JSON manifest using `example_manifest.json` as a shape example, replacing its illustrative paths with actual retained artifacts. All paths resolve relative to the manifest file. Then:

```powershell
& .\tools\run-analyzer-v001\Invoke-Run-Analyzer-v001.ps1 -ManifestPath 'C:\PATH\study-runs.json'
```

Each run requires unique `id`, `tool`, `system`. Optional `variant` and `profile` identify the benchmark/configuration explicitly. `artifacts` may specify:

| Key | Meaning |
|---|---|
| native_jsonl | Provengo fixed Java native per-case JSONL |
| log | Native EvoMaster log, or fallback Provengo log |
| bug_buckets | Exact RESTler run's bug_buckets directory |
| native_json | Previously collected native JSON with integer count and explicit metric; retained as declared evidence |
| trace | Recorded HTTP evidence for anomaly and optional semantic analysis |
| execution_json | Exit code, watchdog flag and wall_seconds recorded by a runner |

Optional `inputs` maps labels such as `sut` or `openapi` to actual files to hash. No same-SUT/contract/version assertion is made merely because labels match. Match fingerprints, configurations, budgets and evidence scopes before making a comparative research claim.

## What the report does and does not count

| Layer | Examples | Interpretation |
|---|---|---|
| Execution | Nonzero exit, timeout, partial result | Harness/run state; not itself a business bug |
| Native findings | Failed fixed Java tests; EvoMaster potential faults; RESTler bucket files | Tool-specific metrics, preserved separately; do not sum or equate them |
| HTTP anomalies | 4xx/5xx counts in tool traffic | Observed responses, not automatic bug confirmation |
| External evaluation | Confirmed historical rule classes or current Library candidates | Product/profile-specific evidence; independent of native alerts |
| Evidence gaps | Missing artifacts, unknown test scope, missing readbacks | Unknown/incomplete, never silently zero |

RESTler's historical native metric counts artifact files, potentially including auxiliary files. It is not a deduplicated bug count. EvoMaster's potential-fault summary is not semantic confirmation. Provengo fallback FAIL mentions are diagnostic only; fixed-test JSONL has the more precise failed-test metric. No regex matching can make these metrics interchangeable.

Semantic profiles and boundary/readback requirements are documented in `../semantic-checker-v001/README.md`. No boundary reconstruction from RESTler network logs or generated EvoMaster tests has been added here. A flat fuzzing campaign cannot be declared a single official test simply to get a score. If no profile/trace is supplied, native analysis still works, while semantic status stays `not_evaluated`. Historical Pharmacy response markers and Todoist runtime-only limitations remain explicit.

## Validation / current scope

Run `python -m pytest tools/run-analyzer-v001/tests tools/semantic-checker-v001/tests -q`. The new tests cover all three native adapters, independent products, unknown versus explicit zero, preserving repeated runs, incomplete reports, separate HTTP anomalies, input fingerprints and non-overwriting reports. The shared checker retains its 29 tests. See `VALIDATION_20261021.json` for the real Library archive check.

This first analyzer supports a declared mixed-run inventory and the v011 archive convenience reader. It is not yet an automatic importer for every historical directory layout, every tool version or every product's finding format. Future work: additional native formats, case replay/boundary adapters, richer anomaly categories, product declarations and readable consolidated bug witnesses.
