# EvoMaster v3 campaign evidence (2026-11-20)

This directory documents the 18-cell EvoMaster campaign and accompanies the RESTler v3 archive in this repository branch.

## Campaign results

| Set | Cells | HTTP requests | Server errors |
| --- | ---: | ---: | ---: |
| `literature-v003` | baseline, B1-B6 (7) | 102,981 | 0 |
| `netbox-gitea` | baseline, F1-F6 (7) | 208,967 | 0 |
| `featurefuzz` | baseline, C1-C3 (4) | 120,370 | 0 |
| **Total** | **18** | **432,318** | **0** |

All 18 cells are marked `COMPLETED` in the source summaries. Completion and HTTP status counts alone do not establish that seeded defects were detected.

## Full evidence archive

The complete source archive has been uploaded to this branch as six parts under `evidence/`, together with `parts-manifest.json`. The manifest records each part's byte size and SHA-256, as well as the original archive's size and SHA-256.

The original ZIP passed integrity validation before upload. It contains 426 files, including all 18 per-cell `http.jsonl` traces, generated test reports, native and server logs, run commands, effective configuration, OpenAPI files, and campaign summaries. The original archive is 529,710,328 bytes (about 506 MiB) and has SHA-256:

`4e29fde3f73e62f81b8859ca11693d436a68dec424f2f6e1e11ec17797b0f1c2`

It is split because GitHub limits the size of an individual repository file. The six parts are all below GitHub's 100 MB per-file limit. GitHub emitted its standard warning for files above the recommended 50 MB; the push completed successfully.

## Restore and verify the archive

Clone this branch (it includes the RESTler archive as well):

```powershell
git clone --branch codex/restler-evomaster-archive-2026-11-21 --single-branch https://github.com/geraw/library-demo.git C:\work\temp\library-demo-evidence
```

Reassemble the ZIP and verify every part and the final archive hash:

```powershell
.\research\evomaster-v3-archive-2026-11-21\Join-EvoMaster-Evidence.ps1 -RepositoryPath 'C:\work\temp\library-demo-evidence' -DestinationPath 'C:\work\temp\EvoMaster-all-evidence-20261120-restored.zip'
```

The script stops if a part is missing or its checksum differs. On success, it verifies the reconstructed archive's byte size and SHA-256 against the manifest.

## Evidence interpretation

The campaign summary records execution status, HTTP request counts, and server-error counts. Review the raw traces and EvoMaster reports before making mutation-attribution or bug-detection claims.

The C-arm rows match the uploaded `summary(6).csv`. B- and F-arm rows match the PowerShell summary output shared on 2026-11-21.

## Related RESTler archive

This branch is based on `codex/restler-v3-archive-2026-11-19` and contains the RESTler v3 source kit and campaign/validation archives alongside the EvoMaster records:

- `research/restler-v3-archive-2026-11-19/README.md`
- `research/restler-v3-archive-2026-11-19/SHA256SUMS.json`


## Trace audit and recovered source references

The 36-cell offline HTTP-trace audit and its limits are documented in [`analysis/TRACE_AUDIT.md`](analysis/TRACE_AUDIT.md). Six distinct B/F/C mutant arms show mismatches under an independent consistency oracle; this is not a claim that RESTler or EvoMaster natively reported six detections. The F/C code under `source-reference/` is hash-mismatched reference material, not byte-identical campaign source; see `source-reference/PROVENANCE.md`.
