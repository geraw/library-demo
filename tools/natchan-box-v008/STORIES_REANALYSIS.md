# v008 retrospective story evidence reanalysis

Producer: `weissye/vikunja_study@62ff20a9da589e3b4ac18189e6f8f7f46f4ccde8`. 29 exact Git-retained subsets, 57 members verified against that commit tree, 4,903 retained research exchanges. These are **not original uploaded ZIPs**. No new SUT requests. NOTE/SUMMARY prose excluded. All 29 complete processing with exit 0/PARTIAL; missing evidence remains explicit.

| Retained case | Research HTTP | 5xx | Common product candidates | Precondition finding occurrences | Producer measurements |
|---|---:|---:|---:|---:|---:|
| gitea-stories-20261026-214605 | 134 | 0 | 0 | 0 | 0 |
| gitea-stories-20261026-214948 | 155 | 1 | 0 | 5 | 0 |
| gitea-v2reg-20261026-232345 | 155 | 1 | 0 | 5 | 0 |
| mealie-pg-stories-20261026-180615 | 226 | 5 | 5 | 0 | 0 |
| mealie-stories-20261026-152627 | unavailable | unavailable | unavailable | unavailable | 3 |
| mealie-stories-20261026-155056 | unavailable | unavailable | unavailable | unavailable | 0 |
| mealie-stories-20261026-155119 | unavailable | unavailable | unavailable | unavailable | 0 |
| mealie-stories-20261026-160113 | unavailable | unavailable | unavailable | unavailable | 2 |
| mealie-stories-20261026-160850 | unavailable | unavailable | unavailable | unavailable | 0 |
| mealie-stories-20261026-174809 | 226 | 4 | 12 | 0 | 0 |
| mealie-stories-20261026-185652 | 17 | 0 | 0 | 0 | 0 |
| mealie-v2reg-20261026-233607 | 264 | 4 | 16 | 0 | 0 |
| vikunja-stories-20261026-203334 | 64 | 2 | 0 | 0 | 0 |
| vikunja-stories-20261026-205024 | 40 | 0 | 0 | 0 | 0 |
| vikunja-stories-20261026-210546 | 80 | 0 | 0 | 0 | 0 |
| vikunja-stories-20261026-210902 | 108 | 2 | 2 | 0 | 0 |
| vikunja-stories-20261026-213955 | 108 | 2 | 0 | 0 | 0 |
| vikunja-stories-20261026-214347 | 102 | 2 | 2 | 0 | 0 |
| vikunja-v2reg-20261026-232251 | 150 | 4 | 2 | 0 | 0 |
| wger-stories-20261026-162150 | 133 | 0 | 1 | 0 | 0 |
| wger-stories-20261026-163108 | 142 | 0 | 0 | 0 | 0 |
| wger-stories-20261026-173331 | 154 | 0 | 0 | 0 | 0 |
| wger-stories-20261026-181318 | 373 | 0 | 0 | 0 | 0 |
| wger-stories-20261026-181911 | 116 | 0 | 1 | 0 | 0 |
| wger-stories-20261026-182700 | 732 | 0 | 0 | 0 | 0 |
| wger-stories-20261026-183640 | 77 | 0 | 4 | 0 | 0 |
| wger-stories-20261026-204904 | 206 | 0 | 1 | 0 | 0 |
| wger-stories-20261026-205327 | 200 | 0 | 1 | 0 | 0 |
| wger-v2reg-20261026-230849 | 941 | 0 | 6 | 0 | 0 |

## Mealie raw contribution and copy checks

In `mealie-v2reg-20261026-233607`, 264 research exchanges and four 5xx are retained. v008 independently finds:

- Two RAW-CONTRIBUTION-DISCREPANCY occurrences: a scaled action expects total 19 and observes 20; a zero-net roundtrip expects the original 13 and observes 14. Three other individual contribution actions pass the recorded policy.
- Two RAW-COPY-INTERNAL-REFERENCE occurrences: copy response and later readback both expose unresolved internal references, after a valid source control. These can describe one copy bug, not two independent bugs.
- Existing M-D1/M-D2/M-C1 behavior-signature candidates remain (four occurrences each). The resulting 16 common behavior occurrences are **not 16 distinct bugs**.

The four raw contribution/copy occurrences are linked retrospectively to MEAL-F01 / MEAL-COPY-INTRA-REF. Earlier native-only packages retain weaker producer-measurement evidence; unavailable raw input is not upgraded. Original Mealie OpenAPI bytes were not retained; that metadata limitation is explicit.

## Gitea passing preconditions

In `gitea-v2reg-20261026-232345`, 155 exchanges and one 5xx are retained. The all-outcome audit records six established relationships and six not established, grouped into five precondition finding occurrences. This includes passing DELREF: no failed producer check is required to flag an unestablished setup. The 5xx remains visible, with no label-deletion causal credit and zero qualified common product-semantic candidates in this trace. A server error alone is still evidence of server failure, independent of that failed explanation.

## Preserved supported behavior signatures

In `wger-v2reg-20261026-230849`, 941 exchanges yield six common occurrences: W-F2 (1), W-F3 (2), W-F4 (2), W-F5 (1). Configured roleless aggregate checks record three passed sides and one failed side. Projection/enum semantics retain their prior conditional interpretation, including rounding uncertainty.

In `vikunja-v2reg-20261026-232251`, 150 exchanges/four 5xx retain two qualified V-F1 move-projection occurrences; the four generic 5xx are separate from the two common semantic candidates.

## Interpretation and remaining acceptance

All candidate naming is retrospective. No observed server version is supplied for the retained story subsets; none receives version-confirmed known-bug credit. The exact per-case rules, witness comparisons, precondition fields, input Git blob IDs/SHA256s and engine/profile hashes are in REANALYSIS.json. Counts overlap across rules and cannot be summed as independent bugs.

No held-out/Tandoor evidence, real new tool run, original login ZIP, complete uploaded story archive, full historical server-log correlation or Windows orchestration was tested in this reanalysis. A4 remains open. See GAPS_RESOLUTION.md and HANDOFF_PROMPT_HE.md for the required prospective/original-archive acceptance.
