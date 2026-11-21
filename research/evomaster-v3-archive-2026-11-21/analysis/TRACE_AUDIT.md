# Offline trace audit: 36 Library campaigns

Date: 2026-11-21

## Scope and evidence

This audit reads the retained RESTler and EvoMaster HTTP traces for the 18-cell campaign of each tool. The inputs are the two archives already stored in this branch:

- EvoMaster archive SHA-256: `4e29fde3f73e62f81b8859ca11693d436a68dec424f2f6e1e11ec17797b0f1c2`
- RESTler archive SHA-256: `ece61a0ad1af789c74c197d09be7f8beea3944f2837cfbba89083894c17f99cd` (`restler-validated-20261119-154213-146b9f-analysis.zip`, stored under `research/restler-v3-archive-2026-11-19/`)

The campaign summaries report 36/36 completed cells, 517,066 total HTTP requests, and zero HTTP 5xx responses. Completion and lack of server errors are not evidence that no semantic fault was triggered.

The script `audit_mutant_traces.py` performs an offline, input-projected CRUD replay. It reconstructs rows from successful POST request bodies and returned IDs, applies successful DELETE requests, then compares that projected state with unfiltered collection GETs and GET-by-ID responses. It also flags successful POST responses that echo a different input field. It does not infer whether a 4xx response should have been accepted, assess filtered-query semantics, or classify a mismatch against a specific mutation without the mutation definition. Therefore its event counts are consistency-oracle observations, not native tool detections and not counts of distinct bugs.

## Trace-level observations

The following six distinct mutation arms produced at least one mismatch under that offline oracle in one or both tools:

| Mutation arm | EvoMaster trace evidence | RESTler trace evidence | Interpretation from the mutation catalog |
| --- | --- | --- | --- |
| F2 | 816 POST echo mismatches; 849 collection mismatches | No mismatch under this oracle | Hold stored against the wrong book after the relational trigger |
| F3 | No mismatch under this oracle | 300 collection mismatches | Successful hold cancellation leaves the targeted hold present |
| F5 | 2,346 POST echo mismatches; collection state matched | No mismatch under this oracle | Creation response reports the wrong user while stored hold data is correct |
| C1 | 221 collection mismatches | No mismatch under this oracle | Filtered loan read corrupts the shared collection used by later reads |
| C2 | 328 collection mismatches | 314 collection mismatches | Cancelling one hold removes another hold for the same user/book pair |
| C3 | 512 collection mismatches and 119 by-ID mismatches | 21 by-ID mismatches | Reused book ID creates an identity collision; a read by ID can return the older row |

The counts are mismatching observations in traces, not independent reproductions. Each campaign has one baseline and isolated mutant arms. All three retained baselines for each tool had no mismatch under this oracle. The remaining nine arms (B1-B6, F1, F4, F6) were not positively classified by this generic consistency check. This does not prove those faults were absent or impossible to trigger: B1/F1 require a semantic oracle for a valid request rejected with 4xx; B4/F4 require filtered-query semantics; and F6's defining signal is a 5xx response. They need class-specific evaluation before assigning a final 0/1 result.

## What the tools themselves reported

Do not write that “RESTler and EvoMaster found six bugs.” The archived run summaries keep `mutation_attribution=REVIEW_REQUIRED` and `native_report_review=PENDING` for mutant cells. The six-arm union above comes from the independent offline trace oracle after the runs.

RESTler produced ten `ResourceHierarchyChecker_20x` replay reports in the retained campaign. All ten replay logs contain a book creation and a hold creation but omit the required `POST /users` setup. For each report, the referenced user was created earlier in that arm's full HTTP trace, so the saved minimized replay cannot reproduce its recorded successful hold as written. Treat these as incomplete replay candidates, not confirmed seeded-bug detections. Example: the baseline replay uses user `448964` without creating it; the full trace creates that user at order 4580 before the hold at order 4582. This is a replay/setup defect in the report evidence, not proof of a Library mutation.

## The paper's denominator is different

The paper's primary semantic comparison has 11 fault classes across Library, Garage, Pharmacy, and NetBox. Its Table 4 reports SBT 11/11, RESTler 2/11, and EvoMaster 2/11; both black-box tools' two confirmations are NetBox classes B and C. Table 5 reports separate Library prefix controls and excludes them from the primary total.

The 15 labels B1-B6, F1-F6, and C1-C3 in this archive are a separate set of synthetic Library mutation arms. They are not the paper's 11-class ledger, and the letters B/C are overloaded across the two experiments. The campaign trace audit must not be merged into the paper's Table 4 detection counts without a separate protocol and class-specific oracle.

## Source provenance and remaining reproducibility gap

The archived campaign inputs record these source hashes:

- F source used by the run: `faf5260a806009bbd11245418cc1cbaf5a83343597661953f83ea7b9393d875a`
- C source used by the run: `c1fe3e6fe5d0583230dd66eb878d3f6a8af20f857ca6eae5a447e19423631bb1`

The source snapshots included alongside this report were recovered from the public branch `codex/library-feature-mutants-v001`, commit `791816c91f39e26a10292f742269cd29ea87d9e7`. Their hashes are `133ff2f4a4e836c3e76e79fec9eedb6b206edb946e3c3442df63c3ca54908847` (F) and `26a6a5fd5e71db9a06a885fe2450b523ca5356d46e258ace80af6566e90e79cd` (C). Neither matches the hash recorded for its run.

The recovered snapshots and mutation descriptions are useful for interpreting the trace witnesses, and are included with this archive for inspection. They are explicitly reference snapshots, not the byte-identical run sources. Exact source-level rerun reproducibility remains incomplete until the two files matching the campaign hashes are recovered. Do not silently substitute the reference snapshots when claiming a byte-identical rerun.

## Re-run the offline audit

From the repository root, first restore the split EvoMaster ZIP, then run the audit:

```powershell
$evo = Join-Path $env:TEMP 'EvoMaster-all-evidence-20261120-restored.zip'
.\research\evomaster-v3-archive-2026-11-21\Join-EvoMaster-Evidence.ps1 `
  -RepositoryPath (Get-Location).Path -DestinationPath $evo
python .\research\evomaster-v3-archive-2026-11-21\analysis\audit_mutant_traces.py `
  $evo `
  .\research\restler-v3-archive-2026-11-19\restler-validated-20261119-154213-146b9f-analysis.zip `
  --output .\trace-audit.json
```

The JSON output is retained as `trace-audit.json`. The command verifies the offline audit process only; it does not rerun either test-generation tool.
