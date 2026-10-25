# Machine-output comparison: v003 and v004

Producer snapshot: `d990657a2470d4dbf368d4d5eb592749a292f6ff`. Both ZIP hashes were checked. The input journal has 609 records and 431 research exchanges. Samples were produced by a **route harness**, not a native BP schedule. No SUT requests were sent by Natchan.

| Archive | v003 gaps (ATOM + DIV) | v004 gaps | HTTP / 5xx | v004 status / exit |
|---|---:|---:|---|---|
| review_v1_s1_before-change.zip | 47 | 47 | 431 / 11 | PARTIAL / 0 |
| review_v1_s1.zip | 47 | 4 | 431 / 11 | PARTIAL / 0 |

The old archive produces an exactly equal complete analysis JSON in v003 and v004. All prior rule occurrence counts are also preserved on the new archive. New tags: six generic partial-write occurrences and five generic create/update divergence occurrences, plus their existing Gitea aliases. These are classifications of existing evidence, not additional independent bugs.

## New evidence audit

Eight atomicity checks are recomputed: six partial updates and two rollbacks. Their raw write links, snapshot origins, field states, collateral lists and verdicts all agree. Thirty-five DIV comparisons resolve: five raw response-class differences and thirty equal outcomes. Of these, 21 use pointed readback measurements and 14 require only original response classes. See SAMPLE_AUDIT.json for every source and witness.

## Remaining four model reference comparisons

| Source record | Tested values | Parent context | Producer verdict | Analyzer disposition |
|---:|---|---|---|---|
| 605 | deleted IDs 11 versus 12 | different repositories | class_diverge | unresolved: tested values differ |
| 606 | foreign IDs 3 versus 2 | different repositories | class_diverge | unresolved: tested values differ |
| 607 | missing ID 999999999 on both sides | different repositories | class_diverge | unresolved: parent context differs |
| 608 | own IDs 2 versus 3 | different repositories | same | unresolved: tested values differ |

The producer reports eight response-class differences overall. Five satisfy the current same-value/same-context qualification; three are retained but not promoted to qualified pair findings. This does not deny the observed status differences or establish product correctness. Reference-role equivalence across distinct fixture IDs requires an explicit, witnessed semantic binding, not an expected result count.

## Reproducibility

The exact portable requests are examples/evidence-before.request.json and examples/evidence-after.request.json. Copy them beside the corresponding immutable ZIPs; run the documented CLI with fresh output paths. SHA256 is mandatory in these examples. VALIDATION.json records Python, commands implicit in the request paths, exit codes, output directory names, old/new rule counts, suite summaries and regression checks.

The g026 complete analysis is identical; g018 preserves all 190 logged 5xx and signature/rule counts (temporary extraction paths may differ). The translated toolkit-shaped g018 regression preserves its rule and log signature counts. Native home-run acceptance remains pending.
