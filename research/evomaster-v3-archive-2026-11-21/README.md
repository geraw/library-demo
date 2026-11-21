# EvoMaster v3 campaign summary (2026-11-20)

This directory records the 18-cell EvoMaster campaign that accompanies the RESTler v3 archive in this repository branch.

## Campaigns

| Set | Cells | HTTP requests | Server errors |
| --- | ---: | ---: | ---: |
| `literature-v003` | baseline, B1-B6 (7) | 102,981 | 0 |
| `netbox-gitea` | baseline, F1-F6 (7) | 208,967 | 0 |
| `featurefuzz` | baseline, C1-C3 (4) | 120,370 | 0 |
| **Total** | **18** | **432,318** | **0** |

Every cell is marked `COMPLETED` in the source summaries. The campaign summary records execution status, HTTP request counts, and server-error counts only.

## Evidence scope

This is a summary-only record. Raw per-cell `http.jsonl` traces, EvoMaster generated tests, native logs/reports, and the full campaign output directories were not available in the uploaded files used to prepare this commit. Therefore this directory makes no claim that any seeded defect was detected. Review the traces and native reports before reporting mutation attribution or bug-detection results.

The C-arm rows match the uploaded `summary(6).csv`. B- and F-arm rows were transcribed from the PowerShell output shared on 2026-11-21.

## Related RESTler archive

The parent branch contains the RESTler v3 source kit and its campaign/validation archives:

- `research/restler-v3-archive-2026-11-19/README.md`
- `research/restler-v3-archive-2026-11-19/SHA256SUMS.json`

This branch is based on `codex/restler-v3-archive-2026-11-19`, preserving those files alongside this EvoMaster summary.
