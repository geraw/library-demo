# Natchan v015: native lifecycle and Gitea log-signature analysis

This additive version reuses v014's native artifact parser and common rule engine,
plus the existing v003/v005 classifier dependencies. It does not replace the
generic corpus entry point or the Library/Vikunja gateways. Signature-level
evidence is a separate result layer, not an exact known-bug confirmation.

## Run

Extract an original native Gitea campaign ZIP into a directory with
`evomaster_rep1`, etc. On Linux normalize ZIP member backslashes to `/`.
Use a new output directory each time. Python standard library only:

```powershell
python .\tools\natchan-v015\native_analysis.py --input C:\path\to\extracted-g018 --output C:\path\to\new-analysis
python -m unittest discover -s .\tools\natchan-v015\tests -v
python -m unittest discover -s .\tools\natchan-v014\tests -p test_g015_gateway.py -v
```

Outputs: `analysis.json`, containing the existing common analysis, explicit
log-signature findings with hashes/line numbers, native process lifecycle and
caller-filtered reach; `report.md`, generated from those outputs. Saved tests
are not executed. There are no network calls or SUT modifications.

## Interpretation

- `log-signatures.json` is the editable, versioned signature catalog. It adds
  missing-issue comments, C1-compatible issue-edit user lookup, and absent
  release-object diagnostics, while retaining earlier baseline families.
- Signature hits may describe an error cause, not prove it. Adjacent compatible
  HTTP responses are labeled candidates, with `causal_join=false`; payloads,
  request IDs and readbacks remain required for stronger claims.
- C1 signature matches do not establish partial persistence or native reporting.
- Failed console exits or explicit fatal errors override a COMPLETE wrapper
  message, even if a native report happens to exist. Missing native reports
  yield unknown fault counts, never zero.
- Owner-team log messages alone do not confirm B-OWNERS.
- Error lines and HTTP failures are different counts. Generic rule labels can
  overlap. Neither sum is a count of independent bugs.
- Host gateway `.1` exclusion follows g018's network policy, not authenticated
  identity attribution. This does not implement multi-user authorization checks.
- Existing native reports are parsed when present; Schemathesis exchanges use
  the prior adapter. EvoMaster lifecycle is not applied to Schemathesis.

## Executed g018 regression, 22 October 2026

Original archive: `g018-gitea-baselines-20261022-142813.zip`.
The integration re-read raw logs and consoles, not the prior review narrative:

| Observation | Count |
|---|---:|
| HTTP 5xx | 190 |
| Tool-caller successful nested repository responses | 1600 |
| Missing-issue comment signatures | 133 |
| C1-compatible signatures | 1 |
| Missing release-object signatures | 1 |
| Initialization-template signatures | 28 |
| License-template signatures | 13 |
| team_unit uniqueness signatures | 14 |
| Owner-team log-only signatures | 85 |
| EvoMaster failed processes | 3 |

Six new evidence-separation tests and nine prior gateway tests pass. Every
request/500/reach metadata comparison passed. All missing native fault counts
remained null. No exact known-bug or persistence claim was promoted by signatures.
The runner source that prints G018_COMPLETE was not changed by this update.

See [Gitea identity research plan](GITEA_IDENTITY_PLAN.md) for the next proposed
campaign. That document is a plan, not evidence of executed tests.
