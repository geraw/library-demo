# Lifecycle history repair and cross-system verification — 009-dev.9

## Outcome

On the unchanged uploaded Provengo traffic, the independent analyzer now matches
all **37 detection request IDs** reported by the Library oracle: B1 **10**, B2
**8**, B4 **19**. There are no extra target detections and the original baseline
has zero semantic/policy findings. Synthetic controls correcting the flagged
responses remove all target findings. No SUT was called and no samples changed.

B1/B2 are **conditional lifecycle observations**; B4 is a contract-filter
violation. Matching an oracle's detection locations does not establish that its
business assumptions follow from every API contract.

## What the oracle taught us

The Library oracle keeps per-entity lifecycle state until a relevant lifecycle
transition/reset. It parses numeric IDs, including leading zeros, and does not
forget every entity on unrelated writes or field-fuzzing rejection. The previous
analyzer cleared its history on every write and even unrelated filtered reads.

The engine repair is generic:

- Normalize path identities numerically only when both the response identity and
  the path parameter are declared integers. String IDs remain distinct.
- Preserve hypotheses across other-entity writes and rejected writes. Count the
  intervening mutations and retain up to four source locators. Such histories
  produce observations, never proved violations: unexpected side effects have
  not been excluded.
- Successful writes to the same identity invalidate the earlier hypothesis;
  successful create/delete transitions establish the new lifecycle state.
- An unbound successful creation clears that collection's earlier hypotheses.
  Unknown successful actions, server errors, asynchronous writes and missing
  responses are hard barriers. Actor/origin/epoch/case and capture guards remain.
- An unrelated query read no longer erases lifecycle history. Declared item-view
  query semantics remain unsupported; unknown query semantics remain explicit.

No product name, B-number, scenario description or producer verdict selects a
runtime rule. `acceptance_library_oracle.py` loads the reference oracle solely
in the acceptance harness, after independent judgments have been computed.

## Verification

- 204 analyzer tests and 13 benchmark tests pass. Twelve new controls exercise
  integer/string identity, neutral resource names, read-query continuity,
  declared item views, rejected-write uncertainty, same-target updates,
  recreation, ambiguous creation, unknown-success/500/202/missing-answer
  barriers, scope changes and repaired readbacks.
- Exact request-ID agreement with the reference oracle on four original cells;
  not merely equal totals. Four full-cell synthetic corrected-response controls.
- Retained real evidence: 14 relational observations and 14 synthetic repaired
  controls still pass (Mealie 9, wger 3, Vikunja 2).
- Gitea G014: six 500 state-effect witnesses, four 4xx observations and ten
  rollback controls pass.
- Cycle 5: eight Homebox/Paperless 500 reproduction occurrences with eight
  non-500 controls pass; these are not eight distinct root causes.
- The actual story-package adapter replays eight journals from the original
  seven systems and two Label Studio journals, with exact recorded contract
  hashes. Transport-added trailing newlines are removed only in a separate
  temporary contract copy when that restores the exact recorded hash.

| System / evidence | HTTP | Semantic violations | Conditional observations | 5xx occurrences |
|---|---:|---:|---:|---:|
| Mealie journal | 299 | 0 | 9 | 4 |
| wger recent journal | 945 | 0 | 3 | 0 |
| wger older journal | 190 | 0 | 0 | 0 |
| Vikunja journal | 165 | 0 | 2 | 0 |
| Gitea story journal | 132 | 0 | 0 | 0 |
| Tandoor journal | 141 | 0 | 34 | 0 |
| Kimai journal | 46 | 0 | 0 | 0 |
| Dependency-Track journal | 37 | 0 | 0 | 0 |
| Label Studio, each of two journals | 38 | 0 | 0 | 0 |
| Homebox direct reproduction tests | 6 test responses | — | — | 6 |
| Paperless direct reproduction tests | 2 test responses | — | — | 2 |

The table excludes separate undeclared-status findings. Gitea's G014 acceptance
is a separate capture, not the Gitea story journal in the table. Ten distinct
real systems were examined. Setup failures in Kimai/Dependency-Track and Label
Studio limit exploration; zero findings there does not establish correctness.

## Remaining oracle parity limits

The **Library B1/B2 recovery gap is closed for these retained traces**. Full
parity with every specialized real-system producer check is not established.
The real-system producer checks and independent findings use different units.
For example, repeated reference/copy checks can describe the same underlying
symptom; a one-to-one numeric comparison would be misleading.

The old wger percentage check expected 9.9 and observed 9; its configuration's
`value` schema is integer. The contract's enum labels alone do not specify the
rounding semantics of the computed preview. The analyzer does not automatically
promote that producer assertion into a bug. Mealie's zero-net add/remove check
(13 -> 14) is not independently implemented as a separate roundtrip rule;
its related nonlinear scaling observation is detected. These remain explicit
coverage/semantic-model gaps, not passed checks.

Full raw mutant captures for the other three Library configurations were not
included in the uploaded four-cell package. Existing local traces can be
reanalyzed with `replay_library.py`; no claim of their full replay is made here.

## Reproduce

From the existing repository checkout, after updating Git:

```powershell
& .\library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe `
  .\tools\natchan-box-v009\replay_library.py `
  --runs-root .\library\benchmark-v001\runs `
  --contract .\library\benchmark-v001\openapi.json
```

For exact acceptance, extract the uploaded raw ZIP to a new directory, replacing
the example path below. The oracle is a comparison tool, not an engine input.

```powershell
python .\tools\natchan-box-v009\acceptance_library_oracle.py `
  --runs-root 'D:\evidence\provengo-raw' `
  --contract 'D:\evidence\provengo-raw\openapi.json' `
  --oracle .\library\benchmark-v001\oracle_v001.py `
  --output 'D:\evidence\oracle-parity-dev9-new'
```

`review_study.py --study-root <existing-study-evidence> --cycle5-root
<existing-cycle5-evidence> --output <new-directory>` replays the retained study
layout used here. `review_stories.py` remains the individual-package entry point.
All commands preserve the original evidence. The machine-readable release
record is `VALIDATION_DEV9.json`; `docs/analyzer/NATCHAN_V009_GUIDE.md` is the
maintainer/user guide.
