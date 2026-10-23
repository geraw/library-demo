# Natchan Box v001 — pipeline input/output contract

Python 3.10+; standard library only. This is a wrapper of the preserved analyzers, not a new classifier. The supported raw adapters are versioned and finite. No network, SUT calls, replay, account preparation or language model is used.

## One pipeline entry point

From the `geraw/library-demo` repository root:

```powershell
python .\tools\natchan-box-v001\natchan.py --request 'D:\experiment\analysis-request.json' --output 'D:\experiment\analysis-001'
$analysisExit = $LASTEXITCODE
if ($analysisExit -ne 0) { throw "Natchan failed: $analysisExit" }
$result = Get-Content 'D:\experiment\analysis-001\result.json' -Raw | ConvertFrom-Json
if ($result.status -eq 'PARTIAL') { Write-Host 'Inspect coverage.json before using research counts.' }
```

Or use `Invoke-Natchan-Box-v001.ps1 -RequestPath ... -OutputPath ... -Python python`.
The Python CLI is the canonical process interface; the PowerShell wrapper throws on nonzero and is source-reviewed, not executed on Windows here.

The producer should finish writing its immutable, preferably sanitized evidence package, write `analysis-request.json` next to it, invoke this command, then archive the output directory alongside its original evidence. `result.json` is written **last**, references all companion artifact hashes, and is the completion marker. Do not consume an output while the producer process is still running. The output must be fresh and outside an input directory. Existing output is never overwritten. No tokens or server credentials are required.

## Input: analysis-request.json

```json
{
  "schema_version": "natchan-request/1",
  "run": {
    "id": "g026-seed1",
    "tool": "provengo",
    "product": "gitea",
    "product_version": "28.1.0"
  },
  "evidence": {
    "adapter": "provengo-native-lifecycle",
    "archive": "g026-results.zip"
  },
  "configuration": {
    "product_profile": "gitea-lifecycle",
    "catalog_set": "research-catalogs-v014"
  }
}
```

All relative paths resolve from the request file's parent, independently of the caller's working directory. `run.id` names the pipeline job; original underlying run IDs remain unchanged. The other run fields are **assertions**, compared with observed non-null product/version/tool metadata. `mixed` explicitly allows multiple values for corpus or multiple-tool evidence, never for the single-product native-lifecycle adapter. Absent underlying metadata remains unknown; declared values do not overwrite it. Seed stays in original evidence; the v001 request does not accept an unverified seed declaration.

Exactly one evidence location is allowed. Unknown keys/adapter IDs/profile IDs/catalog-set IDs are rejected. Optional `evidence.sha256` pins the location file's raw SHA256 (64 lowercase hexadecimal characters); it is not accepted for directory inputs. Configuration contains descriptions, not expected findings or verdicts. The CLI validates its contract without requiring a JSON Schema package; the schemas document structural shape and the CLI also enforces adapter-specific compatibility and path semantics.

## Supported adapters

| Adapter ID | Evidence location | Actual existing engine | Scope |
|---|---|---|---|
| `provengo-native-lifecycle` | `archive` | v016 | Gitea/Provengo native `SHARED_EVIDENCE` receipts, e.g. g026 |
| `gitea-native-tools` | `directory` or `archive` | v015 | Gitea EvoMaster/Schemathesis runs, e.g. g018 |
| `historical-corpus` | `manifest` plus `root` | v014 | Explicit dataset/gateway corpus for historical evidence |
| `normalized-observations` | `observations` | v003 classifier, v014 catalogs | Nonempty `natchan-observations/1` supplied by an audited adapter |

An arbitrary RESTler log, unknown product or new format does not become supported merely by naming it in JSON. Supply an audited normalization adapter; the existing `natchan-v003/observations.schema.json` describes normalized records. Imported semantic facts retain the classifier's existing trust policy; this box does not independently validate arbitrary `fact_basis: recomputed` assertions. No cached human findings are ingested as raw evidence.

### Native lifecycle archive

Required at ZIP root: `native.log`, with actual version and request/response receipts. `sut.log` supplies error correlation. Absence of the server log yields PARTIAL, not zero known bugs. A present `EXPORT_gNNN.json` is checked by v016. Producer `observations.json` verdicts and cached known-bug results are ignored. Native source byte/line references and existing catalog predicates are preserved.

### Native tools directory/archive

Immediate children must be run directories, each containing `run-meta.json` and `sut.log`. Original reports, exchanges and `tool-console.log` are used according to the existing tool adapter. An enclosing extra folder is not guessed. Windows ZIP separators are normalized; traversal, symlinks, case-collisions and oversized archives are rejected. No saved test files are executed. Archive-mode sources originally refer to a temporary extracted path; `provenance.source_locations` maps this prefix back to the original ZIP and slash-normalized member paths. Original bytes and hashes remain identifiable after extraction is removed.

Native tool reports, retained HTTP exchanges, and server-log signatures remain separate evidence tiers. A log signature never becomes an exact known bug just because it resembles a known issue. Unknown native fault counts or incomplete tool execution cause PARTIAL. A metadata count disagreement fails the wrapper.

### Historical corpus

Use `examples/corpus.request.json`; `evidence.manifest` points to a `natchan-corpus/1` document and `evidence.root` is its evidence base. Dataset paths **inside that manifest** resolve against `evidence.root`. The wrapper does not relocate missing historical artifacts. v014's `worker.execute` defines the supported dataset adapters; `corpus-v014.json` is the historical template, not evidence included with a checkout. Pin original bytes with its `locked_sources`. The original engine's audit records actual read inputs. The existing v014 catalog and metadata exclusion policy are used unchanged.

## Configuration and version control

| File/setting | Role |
|---|---|
| `analysis-request.json` | Job identity, adapter, evidence locations and optional pin |
| `schemas/request.schema.json` | Public structural input schema |
| `schemas/{result,findings,coverage,provenance,diagnostics}.schema.json` | Public output schemas |
| `configuration.product_profile` | `gitea-lifecycle` for native lifecycle; `adapter-default` for others |
| `configuration.catalog_set` | Only `research-catalogs-v014` is registered in v001 |
| `configuration.profile` | Optional profile JSON path, native lifecycle only |
| `configuration.catalogs` | Optional catalog directory, native lifecycle/normalized only |
| `../natchan-v016/profiles/gitea-lifecycle.json` | Native route/method/error-log bindings |
| `../natchan-v014/catalogs/*.json` | Existing generic/product/known-bug predicates and version qualifications |
| `../natchan-v014/profiles.json` | Historical readback metadata exclusions |
| `../natchan-v015/log-signatures.json` | Baseline log signatures |
| `SHA256.json` | Box release-file hashes, generated after tests |

This box requires the full repository's preserved dependencies; copying only natchan.py is insufficient. Explicit overrides are not silently accepted by adapters that cannot apply them. Runtime provenance records actual code/config/catalog/input hashes. Existing analyzers are unchanged.

## Fixed outputs

| File | Contract |
|---|---|
| `result.json` | Processing status, exit code, requested job metadata, counts and relative artifact paths/hashes; written last |
| `findings.json` | One entry per source occurrence, with multiple tags/known IDs, predicate checks and witnesses; severity suggestions remain context-qualified |
| `coverage.json` | Adapter scope, explicit evidence gaps, original rule coverage and limitations |
| `provenance.json` | Request, input/code/catalog fingerprints, Python version and underlying engine inventory |
| `diagnostics.json` | Invalid/unsupported input or engine failure details |
| `report.md` | Generated solely from unified machine outputs |
| `analysis.json` | Original analyzer JSON, copied without changing facts or classifications; present after successful processing |
| `engine-report.*` | Original readable reports when provided by the engine |

Successful processing always writes all fixed outputs. A handled failure writes the six common files, with no success counts; an unusable/existing output path cannot receive diagnostics and fails to stderr. `analysis.json` is not guaranteed on failure. Input raw data and producer findings are never overwritten.

### Status and process exits

| Status | Exit | Meaning |
|---|---:|---|
| COMPLETE | 0 | Processing finished within the selected adapter scope, no explicit gaps detected |
| PARTIAL | 0 | Processing finished; missing evidence/underlying tool gaps are enumerated |
| FAILED | 2 | Invalid request/evidence, metadata conflict, hash mismatch or invalid output |
| FAILED | 3 | Unsupported adapter/schema/profile/configuration combination |
| FAILED | 4 | Underlying analyzer failed or unexpected engine exception |

A finding is **not** a processing failure. PARTIAL is intentionally a successful invocation; callers must inspect status and coverage before scoring. COMPLETE is **not** proof of complete product/known-bug coverage or product correctness. No zero-finding claim is made on FAILED. Counts are occurrences, not independent bugs. Native and log-signature counts are not additive evidence of more HTTP failures. Matched known bugs remain human-review candidates, not proof of identical root cause.

## Verification

```powershell
python -m unittest discover -s .\tools\natchan-box-v001\tests -v
```

The test suite exercises the real classifier, wrong metadata, corrupt/missing/changed input, unsupported interfaces, no overwrite, error artifacts, imported-verdict independence and ZIP path/collision controls. See VALIDATION.json for real-data parity with the underlying native analyzers. It does not claim a rerun of Provengo/Gitea or complete historical-corpus evidence coverage.
