# Library Repository Retention Audit

Audit date 22 October 2026. No files have been deleted.

## Decision scope

This is an active-checkout cleanup proposal, not permission to destroy historical
evidence. A version unnecessary for current commands may still be necessary to
reproduce a historical non-scoring execution. Archive an immutable commit/tag
and manifests before removing any such source from the current branch.

| Candidate | Current dependency result | Recommendation and reason |
|---|---|---|
| library/ess-experiment/campaign-v001 | No retained v004-v012 runtime import found; only its own README and HOME_HANDOFF documentation reference it in code search | Candidate for removal from active checkout after historical archival; original campaign orchestration is superseded |
| library/ess-experiment/campaign-v002 | No retained runtime import found; references are its own README and v003 README | Candidate for archival cleanup; not a dependency of current experiment commands |
| library/ess-experiment/campaign-v003 | No retained runtime import found; its own README references it | Candidate for archival cleanup; the separated business/investigator workloads use v004 |
| library/ess-experiment/campaign-v010 | No retained runtime import found; its own README references it | Strongest source-version cleanup candidate: v011 explicitly replaces execution and preserves the original catalog independently |
| Local generated products and caches | Not experiment source; may be untracked or ignored | Delete only after checking they are reproducible or checksum-archived; no blanket repository deletion proposal |

## Required retained chain

V012 invokes v011. V011 imports v009. V009 imports v006 and reads the v007
contract. V006 imports v004 and launches its own observer. V005 imports v004.
V008 imports v006 and checks v007's contract. V007 imports v006. These folders
remain required by documented current workflows.

Keep library/provengo model inputs, library/sut/sut_buggy_issta.py and its tests,
the experiment contracts, and ess-experiment/src/StrictGuidedRun.java. V004 copies
and patches the model inputs. V011 verifies and patches the fixed Java source.
V012 restores its own frozen inputs but does not remove those runtime dependencies.

The standalone observer-v001 and reference/Old files were not proven unnecessary
for all other consumers in this multi-system repository. They are not approved
for deletion by this audit. Likewise, Natchan v002/v003 remain actual product/tool
gateway and classifier dependencies even though newer analyzer directories exist.

## Reproducibility conditions before removal

1. Retain the pre-cleanup commit and a durable archive of historical sources.
2. Preserve raw run artifacts and exact source/binary/sample manifests.
3. Update HOME_HANDOFF and any navigation references if the active path is removed.
4. Run fixture checks, v012 preparation, analyzer regression checks and reference
   import checks. Perform a native v012 transport preflight on the work machine.
5. Remove only the reviewed paths in a separate cleanup commit. Do not rewrite
   repository history or remove original archives as part of source cleanup.

If reproducing every historical execution from the current branch is a strict
requirement, move candidates under a historical namespace rather than delete
them. The audit does not prove that no external user invokes an old path.

## Inspection method

The dependency graph was derived from the actual campaign Python and PowerShell
sources at cdf56ab05f361d998929227c916ae13bbdb7219c. Repository-wide indexed code
search was additionally performed for campaign-v001, v002, v003 and v010. Search
results are a supporting check, not proof about external scripts or unindexed
files. The proposal therefore uses conditional archival removal rather than an
unqualified claim that historical code is safe to discard.
