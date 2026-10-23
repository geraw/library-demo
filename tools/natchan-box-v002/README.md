# Natchan Box v002 — toolkit/v1 E1–E5 evidence

Adds `toolkit-v1` to the existing Box request/result interface. v001 remains frozen. Uses the existing v003 classifier, v014 catalogs/engine, Gitea raw-sequence rules and v015 native-tool parsers. The old four adapters remain available unchanged. Python 3.10+ standard library, offline; no SUT calls, saved-test execution or online Git resolution.

## Run

From the full analyzer repository checkout:

```powershell
python .\tools\natchan-box-v002\natchan.py --request 'D:\experiment\analysis-request.json' --output 'D:\experiment\analysis-002'
if ($LASTEXITCODE -ne 0) { throw 'Analysis failed; inspect diagnostics.json.' }
```

Use a fresh output directory outside any input directory. The pipeline must inspect both process exit and `result.json.status`. Existing outputs are not overwritten. The PowerShell convenience entry point is `Invoke-Natchan-Box-v002.ps1`; Python is the tested process interface.

## Request

```json
{
  "schema_version": "natchan-request/1",
  "run": {
    "id": "toolkit-v1-model",
    "tool": "provengo",
    "product": "gitea",
    "product_version": "28.1.0"
  },
  "evidence": {
    "adapter": "toolkit-v1",
    "archive": "v1-gitea-model.zip"
  },
  "configuration": {
    "toolkit_repo": "../vikunja_study"
  }
}
```

`archive` accepts the original E1/E3 outer package, E2/E4 individual review ZIP, or E5 baseline package. No manual extraction/renaming. The run format is detected from retained files, not a product-specific filename. Product comes from `result_v1.json.sut` or package `ENV.sut`. Version comes from `result_v1.json.sut_version` or generic native `run-meta.json.sut_version`, never an invented native-log version event. Metadata conflicts are errors. Request metadata remains assertions, not substitutes for missing facts. For mixed baseline tools set `run.tool` to `mixed`.

Paths in the request resolve from the request file. Optional `evidence.sha256` pins original archive bytes. Other Box adapters and fixed output schemas are described in [v001](../natchan-box-v001/README.md).

## Resolving sut.json without changing toolkit v1

Three supported ways:

1. Include a non-secret `sut.json` snapshot in the package root (or `configs/<sut>/sut.json`). This is recommended for future packages; the analyzer also supports snapshots at individual run roots. If present in an outer package it is inherited by its runs.
2. Set `configuration.toolkit_repo` to a **local Git repository** containing the producer commit named by `ENV.git_head`. The adapter executes read-only `git show <recorded-commit>:toolkit/v1/configs/<sut>/sut.json`. It does not use the current working-tree version or fetch from the network. Missing local history is an error. Git is needed only for this option.
3. Set `configuration.sut_config` to an external snapshot and optionally `configuration.sut_config_sha256` to its exact raw hash. If the ENV names a producer commit and there is no Git verification, the configuration binding is marked unverified and processing is PARTIAL. A hash pins bytes; it does not prove their relationship to that commit.

If both snapshots and a local Git binding are supplied they must agree byte-for-byte. Config `name` must match actual product. The resolved hash/source/commit and binding quality are recorded in provenance. Without a configuration, raw HTTP and applicable existing product parsers still operate, but product log-pattern counts are explicitly not evaluable.

Do not change/recreate a frozen toolkit-v1 tag merely to add this analyzer adapter. Existing packages can use the local Git or external-snapshot options. Include snapshots through a versioned producer change when desired.

## E1/E3 outer packages

Read ENV status/kind/product/version/seeds/git_head; discover `review_v1_s<seed>.zip`. Preserve source archive hash and nested-member chain. Check outer/inner result copies, product/version consistency and seed identity. Missing expected seeds, prepare-only packages and STOPPED packages are coverage gaps. A STOPPED package with no actual run has PARTIAL processing and **null finding counts**, not a clean zero. If a stopped package contains an actual prefix, retain and analyze that prefix while keeping the package status gap.

## E2/E4 run ZIPs

Read the original journal, IR, result, logs and campaign plan. Validate `manifest_v1.json` / `input_hashes.json` when present. Only `research` records count as physical requests. `g014-sequence` records are associated with matching physical receipts and plan steps, never added as extra HTTP. Duplicate/malformed step identities and result/request-count conflicts fail; incomplete associations are coverage gaps.

The existing Gitea parser and raw-sequence detector are reused only when actual product is Gitea. Generic products retain their own identity and receive raw status classification/IR route context plus applicable producer measurements. They do not inherit Gitea known-bug claims or arbitrary Gitea log semantics. Product-specific known-bug/state extraction beyond that remains an explicit gap for other products.

Result statuses are retained independently of analysis processing. STOPPED_AT_FIRST_FAILURE/TIME_LIMIT/incomplete runs can yield useful findings on the recorded prefix, but do not imply full planned coverage. Model/campaign summaries, probe prose, NOTE files and producer `reference_findings` are not classification facts.

### Oracle measurements

All six documented categories are retained. Labels like `partial`, `crash`, `silently_dropped` and `class_diverge` are **not accepted as proof**. The adapter reuses measurement comparisons and raw sequence rules; `analysis.json.producer_measurements` records the reported label alongside a recomputed measurement and its source. Atomic field states remain producer field measurements when complete snapshots are missing, not an independently verified transaction. Unknown categories are retained as coverage gaps. Reference/association policy and missing/deleted/foreign validity are not proved by status alone.

Raw campaign create/update comparisons still require the existing positive-control and same-value conditions for qualified rules. The producer's count of eight divergences is not an expected count forced into the analyzer.

## E5 baseline packages

Read actual product from ENV, generic `sut_version` and `sut_log_reach` from each run's metadata. Compare legacy aliases if present; conflicting aliases fail. Log patterns (`error_pattern`, `http500_pattern`, `request_pattern`) use the producer's literal substring semantics; `reach_regex` is a regex. Configured raw counters are compared with metadata.

For Gitea, reuse v015 using aliases synthesized only in a disposable copy. Original archives remain immutable. Native reports, log signatures and retained HTTP evidence stay separate. Rebind temporary source paths back to original archive/member locations before publishing analysis. Missing EvoMaster reports and SECURITY-stage failures remain partial evidence, not native success.

For another product, generic counters and JUnit testcase/failure counts are readable. Product-specific native findings/exchanges and detailed log interpretation remain NOT EVALUABLE until an audited parser is connected. Such a package returns PARTIAL, not a false claim of full cross-product coverage.

## Outputs and process policy

The same six common outputs plus the original `analysis.json` are produced: `result.json`, `findings.json`, `coverage.json`, `provenance.json`, `diagnostics.json`, `report.md`. `result.json` is written last. Codes: 0 COMPLETE/PARTIAL, 2 wrapper input error, 3 unsupported interface, 4 underlying adapter/engine error (including toolkit-level hash/format contradictions). Findings are not process errors.

Added original-analysis fields:

- `toolkit_packages`: ENV metadata and source locations.
- `toolkit_run_summaries`: actual per-run status, seed, raw request counts, campaign steps and categories.
- `toolkit_configurations`: resolved SUT config bindings/hashes.
- `producer_measurements`: retained measurements and recomputed comparisons, not promoted verdicts.
- `toolkit_coverage_gaps`: incomplete runs, missing snapshots/configuration/seeds and unsupported scopes.
- `toolkit_log_findings`: separate baseline log-signature evidence.

Runtime provenance includes configuration bindings and full original input hashes/member chains. The adapter performs no redaction/repacking of old originals; use the producer's corrected export if an old export contains private paths. No raw run archives are included in this release.

## Validation and limits

```powershell
python -m unittest discover -s .\tools\natchan-box-v002\tests -v
```

Tests include all E1–E5 shapes, nested seeds, no native version receipt, duplicate sequence avoidance, STOPPED/no evidence, generic names without Gitea aliases, wrong-product negatives, malicious verdict labels, manifest changes and recorded-commit configuration retrieval despite a different working tree. Existing g026 and g018 regressions remain unchanged.

The uploaded `EVIDENCE_FORMATS_v1.md` and producer source at 0f24f1bed4e7f740989aedc0dc9665444c371375 were inspected. Original toolkit-v1 home smoke ZIPs were **not provided here**. Tests using constructed protocol fixtures and a translated copy of original g018 are format/regression validation, not reanalysis of the reported 480-request/433-step smoke runs. Actual smoke parity remains to be measured on those original corrected packages.
