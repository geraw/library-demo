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

The full archive was received on 2026-11-21 and passed ZIP integrity validation. It contains 426 files, including all 18 per-cell `http.jsonl` traces, generated test reports, native and server logs, run commands, effective configuration, OpenAPI files, and campaign summaries. Its compressed size is about 506 MB.

GitHub rejects individual repository files above 100 MB. The archive therefore must be split into sub-100-MB parts before it can be committed. The checked-in uploader handles this and records SHA-256 hashes for the original archive and every part.

1. Fetch and switch to this branch in the local clone:

   ```powershell
   git fetch origin codex/restler-evomaster-archive-2026-11-21
   git switch --track -c codex/restler-evomaster-archive-2026-11-21 origin/codex/restler-evomaster-archive-2026-11-21
   ```

   If the local branch already exists, use `git switch codex/restler-evomaster-archive-2026-11-21`.

2. Run the uploader from the repository root:

   ```powershell
   .\research\evomaster-v3-archive-2026-11-21\Upload-EvoMaster-Evidence.ps1 `
     -ArchivePath 'C:\work\temp\EvoMaster-all-evidence-20261120.zip' `
     -RepositoryPath 'C:\work\temp\library-demo'
   ```

   It creates 90-MiB parts, a `parts-manifest.json`, commits them, and pushes this branch. It stops if the working tree is dirty or free disk space is insufficient. The upload is about 506 MB, so the Git push may take some time.

3. To reconstruct and verify the original ZIP after cloning the repository:

   ```powershell
   .\research\evomaster-v3-archive-2026-11-21\Join-EvoMaster-Evidence.ps1 `
     -RepositoryPath 'C:\work\temp\library-demo' `
     -DestinationPath 'C:\work\temp\EvoMaster-all-evidence-20261120-restored.zip'
   ```

The archive upload is not complete until the numbered parts and `parts-manifest.json` appear under `research/evomaster-v3-archive-2026-11-21/evidence/` on this branch.

## Evidence interpretation

The campaign summary records execution status, HTTP request counts, and server-error counts. The raw traces and EvoMaster reports should be reviewed before making mutation-attribution or bug-detection claims.

The C-arm rows match the uploaded `summary(6).csv`. B- and F-arm rows match the PowerShell summary output shared on 2026-11-21.

## Related RESTler archive

This branch is based on `codex/restler-v3-archive-2026-11-19` and contains the RESTler v3 source kit and campaign/validation archives alongside the EvoMaster records:

- `research/restler-v3-archive-2026-11-19/README.md`
- `research/restler-v3-archive-2026-11-19/SHA256SUMS.json`
