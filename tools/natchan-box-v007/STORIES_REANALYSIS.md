# Natchan v007 — retrospective results

The tables below are generated from analyzer outputs in REANALYSIS.json. Source: `weissye/vikunja_study@62ff20a9da589e3b4ac18189e6f8f7f46f4ccde8`. The inputs are 29 deterministic ZIPs containing exact Git-retained result/journal/native-log files, excluding NOTE prose and producer summaries as analytical answers. These are not the original complete user-uploaded ZIPs. No SUT was run.

**Scope:** this is retrospective rule development/regression validation, not a held-out discovery experiment. Generic HTTP facts are recomputed; product intent, a cache root cause and causal dependence on a prior deletion are not independently established. Candidate IDs were known when their signature mappings were added.

| Retained case | Research / 5xx | Finding occurrences | Behavior candidates | Exit / status |
|---|---|---|---|---|
| gitea-stories-20261026-214605 | 134 / 0 | 0 | none observed | 0 / PARTIAL |
| gitea-stories-20261026-214948 | 155 / 1 | 1 | none observed | 0 / PARTIAL |
| gitea-v2reg-20261026-232345 | 155 / 1 | 1 | none observed | 0 / PARTIAL |
| mealie-pg-stories-20261026-180615 | 226 / 5 | 5 | M-C1: 4, M-D2: 1 | 0 / PARTIAL |
| mealie-stories-20261026-152627 | not retained | 3 | MEAL-F01: 1, MEAL-COPY-INTRA-REF: 2 | 0 / PARTIAL |
| mealie-stories-20261026-155056 | not retained | not evaluable | none observed | 0 / PARTIAL |
| mealie-stories-20261026-155119 | not retained | not evaluable | none observed | 0 / PARTIAL |
| mealie-stories-20261026-160113 | not retained | 2 | MEAL-COPY-INTRA-REF: 2 | 0 / PARTIAL |
| mealie-stories-20261026-160850 | not retained | not evaluable | none observed | 0 / PARTIAL |
| mealie-stories-20261026-174809 | 226 / 4 | 12 | M-D1: 4, M-C1: 4, M-D2: 4 | 0 / PARTIAL |
| mealie-stories-20261026-185652 | 17 / 0 | 0 | none observed | 0 / PARTIAL |
| mealie-v2reg-20261026-233607 | 264 / 4 | 12 | M-D1: 4, M-C1: 4, M-D2: 4 | 0 / PARTIAL |
| vikunja-stories-20261026-203334 | 64 / 2 | 2 | none observed | 0 / PARTIAL |
| vikunja-stories-20261026-205024 | 40 / 0 | 0 | none observed | 0 / PARTIAL |
| vikunja-stories-20261026-210546 | 80 / 0 | 0 | none observed | 0 / PARTIAL |
| vikunja-stories-20261026-210902 | 108 / 2 | 4 | V-F1: 2 | 0 / PARTIAL |
| vikunja-stories-20261026-213955 | 108 / 2 | 2 | none observed | 0 / PARTIAL |
| vikunja-stories-20261026-214347 | 102 / 2 | 4 | V-F1: 2 | 0 / PARTIAL |
| vikunja-v2reg-20261026-232251 | 150 / 4 | 6 | V-F1: 2 | 0 / PARTIAL |
| wger-stories-20261026-162150 | 133 / 0 | 1 | none observed | 0 / PARTIAL |
| wger-stories-20261026-163108 | 142 / 0 | 0 | none observed | 0 / PARTIAL |
| wger-stories-20261026-173331 | 154 / 0 | 0 | none observed | 0 / PARTIAL |
| wger-stories-20261026-181318 | 373 / 0 | 0 | none observed | 0 / PARTIAL |
| wger-stories-20261026-181911 | 116 / 0 | 1 | W-F2: 1 | 0 / PARTIAL |
| wger-stories-20261026-182700 | 732 / 0 | 0 | none observed | 0 / PARTIAL |
| wger-stories-20261026-183640 | 77 / 0 | 4 | W-F4: 2, W-F3: 2 | 0 / PARTIAL |
| wger-stories-20261026-204904 | 206 / 0 | 1 | W-F5: 1 | 0 / PARTIAL |
| wger-stories-20261026-205327 | 200 / 0 | 1 | W-F5: 1 | 0 / PARTIAL |
| wger-v2reg-20261026-230849 | 941 / 0 | 6 | W-F4: 2, W-F3: 2, W-F2: 1, W-F5: 1 | 0 / PARTIAL |

Counts are evidence occurrences, not distinct bugs or independent repetitions. Multiple tags on one event are not separate bugs. All version-confirmed known-bug counts remain zero because observed server versions are absent. Missing retained observations are not zero successful checks.

## New rules on the four v2 regression subsets

- wger: W-F2 remains detected; the new rules add two W-F3 projection read occurrences, two W-F4 projection read occurrences and one W-F5 arithmetic candidate. Source comparisons preserve old/new view sides and operator/iteration values. W-F5 remains a candidate: the contract does not settle intermediate/display rounding semantics.
- Vikunja: two V-F1 projection mismatches are recomputed from accepted bucket changes and the retained parent views. The four 5xx responses remain generic server-error evidence; this release does not invent a lock-log cause.
- Gitea: the 5xx remains visible. The stale-label hypothesis fails its recorded precondition, because snapshot and request labels are empty. The report exposes assignee as another changed field. No G-F1 label-causality credit is emitted, and no alternative root cause is asserted.
- Mealie: M-D1, M-D2 and M-C1 raw-sequence signatures remain. The Git-retained regression subset lacks its original native contribution/copy logs, so those producer result flags are not imported as findings. The earlier Mealie subset with retained native logs still yields separately labeled contribution/copy measurement comparisons.

## G-F1 hypothesis audit (computed)

| Case | Journal record (zero based) | Reference present in snapshot | Reference sent in write | Other changed fields |
|---|---|---|---|---|
| gitea-stories-20261026-214948 | 102 | False | False | assignee |
| gitea-v2reg-20261026-232345 | 102 | False | False | assignee |

This is a failed test/oracle precondition, not proof that no product bug exists. The same occurrence retains the raw 500 and generic error tags. A separate, versioned producer experiment would need to establish the intended reference in a successful pre-read and avoid introducing another invalid reference. The historical run must not be rewritten.

## Why the new move rules can evaluate previously missed evidence

The older greedy logical-ID parser could consume text such as `move N1_0` as part of the story name. v007 binds the story identifier before the first whitespace and keeps the actual step. Clean restarts at step 1 are scoped to separate attempts. Negative fixtures prevent borrowing a preimage from an earlier attempt. Generic relation/projection checks then operate on the qualified recorded sequence.

## Positive and negative controls

The 231-test suite includes the 185 inherited tests and 46 new cases: failed and repaired moves/updates/deletes; missing/foreign actor preimages; wrong parent, identity collision and nested/grouped arrays; rejected moves; intervening writes; unrecognized operators; accepted versus refused operands; duplicate iterations; explicit arithmetic/display rounding; empty reference preconditions; external metadata; contract/product conflicts; parser regressions; and standard/isolated CLI operation. Unseen toy product and route names exercise the same engine without adding a product branch. Passing these fixtures is not a claim of zero false positives on all future products.

## Reproduction and acceptance

Use the script with full clones that contain the pinned producer commit:

```powershell
python .\tools\natchan-box-v007\validate_repository_stories.py --producer-repo C:\work\temp\vikunja_study --output C:\experiment\stories-v007-recheck
```

The output must be fresh. REANALYSIS.json lists original Git member paths, Git blob IDs, SHA256 values, semantic comparisons and explicit gaps without local paths. The full original uploaded ZIPs, login count reconciliation, original model archive acceptance and Windows producer integration remain separate acceptance tasks. No fresh live run is needed to analyze the existing full ZIPs. The producer handoff is HANDOFF_PROMPT_HE.md.
