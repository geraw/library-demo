# Natchan v016: native evidence -> existing known-bug catalog

This is the missing gateway between the native lifecycle receipts and the shared
Natchan classifier, not a new independent Gitea bug matcher. It reuses the existing
v003 classifier and v014 catalogs (including GIT-C2 and its current product/version
restrictions). Adjacent canonical components take precedence. A frozen copy is
bundled for the Gitea repository, with origin commit and file hashes, so it does
not require another checkout or network access. No catalog predicates are relaxed.

The adapter reads raw native.log and sut.log; cached observations.json verdicts
are ignored. Product route/signature bindings live in profiles/gitea-lifecycle.json.
Other HTTP-producing tools must supply an adapter to the same normalized
observation interface; this profile only parses the native lifecycle receipt
format. It does not claim every known bug/provider is supported by this adapter.

For the current GIT-C2 evidence it proves operation/entity from the actual route
and method, server error from the response, and missing-milestone context from
the server error. Correlation requires matching requested target ID, root ID
confirmed by the item's baseline response, the first following exact router
method/path/status and a unique eligible receipt/log. Missing or ambiguous logs
leave the known bug unmatched. The deleted-reference context and persisted body
are recomputed from the raw sequence and linked as additional witnesses.

Each failed HTTP request has one occurrence ID derived from source bytes/line.
SERVER_5XX and FIELD_PERSISTED_DESPITE_ERROR remain two tags on one occurrence.
GIT-C2 is the canonical catalog ID; deleted_reference_context_verified records
the C2+ deleted-target context. Matching proves a known behavioral signature,
not identical source-code root cause. No server calls or replay occur.

## Run independently

```powershell
python .\tools\natchan-v016\analyze.py --input "$env:USERPROFILE\Downloads\g026-shared-lifecycle-20261022-181151-f23113.zip" --output '.\natchan-v016-g026-output'
python -m unittest discover -s .\tools\natchan-v016\tests -v
```

Use a fresh output directory. The command writes analysis.json and report.md.
--catalogs and --profile select explicit alternate definitions. Input manifest
hashes, classifier hash, profile hash and catalog hashes are recorded/validated.
The ten regression tests include wrong product/version/field/target/root/router,
missing/ambiguous logs, a 404/success response, forged producer verdicts and
one-occurrence/two-tag aggregation. Both synthetic controls and the actual
uploaded g026 archive are analyzed; reviews/ contains the real offline result.

Actual g026 result: 183 HTTP receipts, one failed request, one known-bug occurrence
matching GIT-C2. No new SUT requests. The 201 contract observations in the existing
lifecycle report are not promoted to known bugs by this adapter.

## Automatic g026 export integration

The Gitea repository's g026 launcher now runs this adapter offline after native
execution, writes known-bug-analysis.json and known-bug-report.md, and annotates
the existing observations with known_bug_matches. Both files enter the sanitized
ZIP. The experimental generator, JSON configurations and SUT are unchanged.
Missing analysis prerequisites produce NOT_EVALUABLE and do not block export of
the raw evidence or get counted as zero known bugs.
