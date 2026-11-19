# Library REST tool experiment: reproducibility kit and evidence (2026-11-19)

This directory preserves the RESTler v3 runner kit and the completed campaign evidence for the Library study. It is intended for independent review and repeat runs.

## Contents

- `Library-RESTler-Stateful-v3.zip` — source kit: PowerShell entry points, Python campaign runner and support modules, configuration/validation files, and regression evidence.
- `restler-validated-20261119-154213-146b9f-analysis.zip` — full campaign package with batch summaries, inputs, per-cell RESTler output, native analyzer reports, and HTTP traces.
- `evidence-curated.zip` — compact navigation/evidence subset, excluding large raw HTTP traces; use the full campaign package for complete trace-level review.
- `Library-RESTler-V3-Validation-20261119-153739-481.zip` — standalone validation campaign archive.
- `Library-RESTler-Baseline300-20261119-151900-288.zip` — additional 300-second literature-v003 baseline evidence.
- `SHA256SUMS.json` — SHA-256 checksums for each archived input.

## What was run

The full campaign archive records three SUT sets and 18 RESTler cells:

| Set | Baseline and mutants | Cells |
|---|---|---:|
| `literature-v003` | baseline, B1–B6 | 7 |
| `netbox-gitea` | baseline, F1–F6 | 7 |
| `featurefuzz` | baseline, C1–C3 | 4 |

Each cell records its command, configuration, timings, HTTP request counts, server status counts, native RESTler outputs and analyzer status. The separate smoke gates and validation archive are also retained. Check the per-cell summaries and native reports before treating a run as a confirmed bug discovery; a completed cell or successful HTTP request alone is not a discovery.

## Reproduce

1. Download and extract `Library-RESTler-Stateful-v3.zip` outside the repository checkout.
2. Read the included `README.md` and `VALIDATION.json`. The work-machine launcher expects the isolated RESTler installation and trial environment described there.
3. On that configured Windows work machine, run a validation baseline first:

   ```powershell
   .\Run-Work-RESTler-V3.ps1 -Mode Validate -Seconds 60
   ```

4. After reviewing the validation ZIP, run the complete sequence:

   ```powershell
   .\Run-Work-RESTler-V3.ps1 -Mode Full -Seconds 60
   ```

The launcher writes results outside the source checkout. The campaign is sequential and starts a fresh SUT for each cell. See the kit README for individual entry-point parameters and commands, including `-Tools restler,evomaster`.

## Tool scope and evidence limits

The scripts retain EvoMaster as an explicit/manual tool option, but this v3 work did **not** calibrate or validate EvoMaster. The archived smoke and 18-cell campaign results are RESTler-only; no EvoMaster campaign results are claimed here. Do not compare or combine these results with the earlier v2 full-checker/BFS configuration: v3 uses a distinct random-walk/stateful-checker profile, and its disabled checkers can change detection behavior. The full source kit documents remaining environment assumptions and limitations.

## Provenance

The included source kit also carries its original `SHA256.json` and `VALIDATION.json`. The outer `SHA256SUMS.json` verifies the exact archives uploaded here. The campaign inputs preserve the source/SUT snapshots and effective configurations used by the recorded runs.
