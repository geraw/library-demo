# v006 changes

Base: `geraw/library-demo@350cf773652dc2bc52de0617bb6e6f385016c6e7` (v005). Producer evidence/specification: `weissye/vikunja_study@e54368795f0a908879d0bdc77f12e20cc8ad1a53` and its toolkit/v2/stories implementation.

- Add a format adapter for result_stories.json, nested review_stories.zip, research journals and native STORY_CHECK measurements; no producer-format renaming or alteration.
- Fix the reported unrecognized-result layout to explicit unsupported exit 3; classify explicitly contradictory stories metadata/counts/manifests as input exit 2. Preserve unexpected engine errors as exit 4.
- Recompute deletion/reference, stale-write, missing-resource server-error and qualified aggregate-move facts from retained HTTP sequences. Product-neutral rules, product-specific candidate profiles.
- Recompute supported contribution/projection comparisons from retained native measurements, distinctly labeled as weaker than full HTTP evidence. Never trust a producer pass/fail flag as the result.
- Preserve missing versions/counts as unknown; expected configuration is not observed evidence. Candidate IDs do not claim version-confirmed known bugs or shared root causes.
- Add negative controls for actor/path/identity/step association, missing preconditions, repaired behavior, rejected moves, forged producer expectations and hash mismatches.
- Publish a source-addressed reanalysis of four Git-retained evidence subsets and explicit gaps; no claim of reprocessing unavailable original ZIPs.

No frozen v005 file, historical experiment, producer, previous catalog or toolkit tag is edited. Automatic producer orchestration remains a maintainer integration step, with exact commands and acceptance criteria in HANDOFF_PROMPT_HE.md.
