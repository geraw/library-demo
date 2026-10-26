# Stories reanalysis — Natchan Box v006

This report is generated from the analyzer outputs summarized in REANALYSIS.json. Source: `weissye/vikunja_study@e54368795f0a908879d0bdc77f12e20cc8ad1a53`, the four `results/` directories below. Exact retained member bytes were assembled into deterministic **repository-subset ZIPs**, excluding NOTE.md. These are not the original user-uploaded ZIPs. No new SUT experiment was run.

| Retained case | Research / 5xx | Finding occurrences | Behavior-signature candidates | Evidence tier |
|---|---|---|---|---|
| mealie-stories-20261026-152627 | unknown / unknown | 3 | MEAL-F01: 1, MEAL-COPY-INTRA-REF: 2 | retained producer measurements |
| mealie-stories-20261026-174809 | 226 / 4 | 12 | M-D1: 4, M-C1: 4, M-D2: 4 | recomputed recorded HTTP sequence |
| mealie-pg-stories-20261026-180615 | 226 / 5 | 5 | M-C1: 4, M-D2: 1 | recomputed recorded HTTP sequence |
| wger-stories-20261026-181911 | 116 / 0 | 1 | W-F2: 1 | recomputed recorded HTTP sequence |

All four analyses returned **exit 0, PARTIAL**. Every version-confirmed known-bug count is zero because observed SUT versions were not retained. Candidate links and generic pattern occurrences are still emitted; zero version-confirmed IDs does not mean zero findings. Root-cause identity is not inferred.

Occurrences are source-addressed HTTP/readback/check events, not distinct bugs, independent experiments or statistical reproductions. Generic 5xx tags and semantic tags can refer to the same occurrence; do not sum rule rows. The early copy case has two failing projections (response and readback), not two established copy bugs.

## Recomputed observations

- Early Mealie: one retained contribution comparison differs from recomputed arithmetic; two retained copy projections contain identifiers outside the copied ingredient-ID set. Full HTTP journal is absent in this subset. These are measurement-level comparisons, not independent reconstruction of the complete response bodies.
- Later Mealie: four delete-only dangling-reference read occurrences, four stale-write retained-reference occurrences and four missing-comment mutation 5xx occurrences. The source checks can revisit the same resource. In particular, merged shopping-item identities are explicitly exposed as a coverage limitation, not claimed as independent referrer objects.
- Mealie-pg: four missing-comment 5xx occurrences and one stale label-reference write 5xx. Rejected food/unit deletions do not establish target removal and are not classified as delete-only dangling-reference findings. The label is preserved as mealie-pg; database identity itself is not established merely by this name.
- wger: one old-parent aggregate mismatch after an accepted child move, with successful additive controls and a correct new-parent aggregate. Other non-additive parent/child combinations do not qualify the hypothesis and remain explicit gaps.

## Exact generic rule counts

| Case | Rule | Occurrences |
|---|---|---|
| mealie-stories-20261026-152627 | STORY-MEASURED-CONTRIBUTION | 1 |
| mealie-stories-20261026-152627 | STORY-MEASURED-INTRA-REF | 2 |
| mealie-stories-20261026-174809 | GEN-SERVER_ERROR | 4 |
| mealie-stories-20261026-174809 | STORY-ABSENT-RESOURCE-5XX | 4 |
| mealie-stories-20261026-174809 | STORY-DANGLING-REFERENCE | 8 |
| mealie-stories-20261026-174809 | STORY-MISSING-REFERENCE-5XX | 1 |
| mealie-stories-20261026-174809 | STORY-STALE-REFERENCE | 4 |
| mealie-pg-stories-20261026-180615 | GEN-SERVER_ERROR | 5 |
| mealie-pg-stories-20261026-180615 | STORY-ABSENT-RESOURCE-5XX | 4 |
| mealie-pg-stories-20261026-180615 | STORY-MISSING-REFERENCE-5XX | 2 |
| wger-stories-20261026-181911 | STORY-AGGREGATE-MOVE | 1 |

## Remaining evidence and acceptance gaps

The retained results omit observed SUT versions and seeds. Manifests are absent. Only the early Mealie subset contains native logs; the others retain result/journal/summary files. No server-log cause attribution is made. Supported raw rules cover qualified deletion/stale-reference/aggregate-move evidence; contribution and copy measurements remain separately labeled. This is not full semantic coverage of every future story family.

The original 1369-research-exchange Vikunja login ZIP was accepted by v005 according to the producer report. Its original bytes were not reprocessed here; inherited synthetic login regressions passed in both frozen v005 and v006. The four complete original stories ZIPs also need local acceptance on their original bytes. No new live experiment is required.

## Reproduce the repository-subset check

Use full clones containing the pinned producer commit and this analyzer release. This reads Git object bytes, excluding worktree modifications and NOTE prose:

```powershell
python .\tools\natchan-box-v006\validate_repository_stories.py --producer-repo C:\work\temp\vikunja_study --output C:\experiment\stories-v006-recheck
```

The output directory must not exist. It will contain deterministic subset ZIPs, requests, per-case analyzer outputs and repository-reanalysis-summary.json. REANALYSIS.json records each member path, Git blob ID, SHA256, rule counts, candidate counts and scoped gaps, without local filesystem paths. Compare signatures/counts on these exact subsets; a complete original ZIP may contain additional evidence and legitimately differ.
