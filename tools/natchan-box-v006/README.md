# Natchan Box v006 — toolkit stories evidence

Offline Python 3.10+, standard library only. Requires a complete `geraw/library-demo` checkout. This version adds the producer's `stories-dev` format without changing frozen v005, its source catalogs, producer code, experiment settings or experimental results. It sends no SUT requests and launches no test generator.

## Run an existing package

Create an `analysis-request.json` beside the original, immutable run ZIP:

```json
{
  "schema_version": "natchan-request/1",
  "run": {"id": "mealie-stories-174809", "tool": "provengo", "product": "mealie", "product_version": "unknown"},
  "evidence": {"adapter": "toolkit-v1", "archive": "stories.zip"}
}
```

Use `wger` for wger; the observed producer label `mealie-pg` is mapped to canonical product `mealie` by `story_profiles.json`. The original target label is retained. That label alone does not verify the database engine. Request metadata asserts compatibility; it never supplies missing observed version evidence.

```powershell
python -m unittest discover -s .\tools\natchan-box-v006\tests -q
python .\tools\natchan-box-v006\natchan.py --request 'C:\experiment\analysis-request.json' --output 'C:\experiment\analysis-v006-001'
```

The output directory must be new. Optional PowerShell wrapper: `Invoke-Natchan-Box-v006.ps1 -RequestPath ... -OutputPath ...`. That wrapper throws on nonzero results; automation that needs the numeric exit code should invoke Python directly and capture `$LASTEXITCODE` immediately.

## Inputs and outputs

The existing `natchan-request/1` interface and adapter name `toolkit-v1` are retained. The adapter detects both v1 and stories layouts; do not rename `result_stories.json` to `result_v1.json`. Stories input can be a run ZIP, a single directory prefix in a ZIP, or `review_stories.zip` inside an outer ZIP. Existing v1 model/campaign/login/baseline paths remain supported. When an outer result copy accompanies review_stories.zip, the copies must agree and the inner raw evidence is analyzed. Multiple story runs flattened into one directory are explicitly unsupported; analyze separate run archives.

A stories run contains:

- `result_stories.json`: `version=stories-dev`, observed `sut` label, `runner`, story IDs/statuses, reported request count and 5xx summaries. Producer failures/pass arrays are descriptive only.
- `gateway-journal.jsonl`: recorded HTTP research exchanges, bodies, actors and logical story/step labels. Counts and step associations are checked. Raw sequence rules require qualified preconditions; story labels alone cannot establish a finding.
- `compiled/<story>/native.log`, or retained native logs under other story directories: `STORY_CHECK` measurements and completion markers. Pass flags are ignored when recomputing supported comparisons.
- Optional observed `sut_version` in result/ENV, optional seed, and optional hash manifest. Never substitute `sut.json.api.expected_version` or prose notes for observed version.
- Optional `manifest_stories.json`, `manifest_v1.json` or `input_hashes.json`: nonempty object mapping relative member paths to lowercase SHA256. Each listed file is verified. Unknown manifest formats are explicitly unsupported; contradictory hashes are invalid input. A missing manifest is a coverage gap, not fabricated integrity verification.

Outputs are `result.json` (final marker), `findings.json`, `coverage.json`, `provenance.json`, `diagnostics.json`, `report.md` and successful `analysis.json`. The latter retains raw observations, recomputed facts, witnesses, source archive/member hashes, line addresses, rules, candidate links and `stories_evidence_audit`. `coverage.json` exposes evidence gaps. Local outputs may contain local paths: sanitize deliverables before sharing; the analyzer does not promise to redact arbitrary input bodies.

| Exit | Meaning |
|---|---|
| 0 | Analysis completed, COMPLETE or PARTIAL; this does not mean zero bugs |
| 2 | Invalid request, or explicitly detected contradictory stories evidence |
| 3 | Explicit unsupported format/interface/runner |
| 4 | Unexpected internal engine defect |

A journal with neither recognized result file now returns exit 3, fixing the reported exit-4 failure. Unexpected exceptions are not blanket-converted into unsupported formats.

## Recomputed rules

| Rule | Required retained evidence | Tier |
|---|---|---|
| `STORY-DANGLING-REFERENCE` | Successful pre-reads; successful target DELETE; same-actor target GET 404; referrer GET retains the same scalar `Id`/`_id` reference; no observed target recreation | `recorded_http_sequence` |
| `STORY-STALE-REFERENCE` | Above, plus successful PUT/PATCH sending the deleted ID before referrer readback | `recorded_http_sequence` |
| `STORY-MISSING-REFERENCE-5XX` | Qualified target deletion/absence and a 5xx write sending that target ID; does not assert the write committed | `recorded_http_sequence` |
| `STORY-ABSENT-RESOURCE-5XX` | Previously readable resource, mutation returns 5xx, qualified nearby same-resource GET 404 | `recorded_http_sequence` |
| `STORY-AGGREGATE-MOVE` | Bound parent/child identities and accepted move; recorded aggregate baselines and successful addition controls; old parent's post-move aggregate differs from baseline plus remaining child | `recorded_http_sequence` |
| `STORY-MEASURED-CONTRIBUTION` | Recompute previous ± source_sum × scale from retained STORY_CHECK detail; require agreement with the recorded expectation; compare observed | `producer_story_measurements` |
| `STORY-MEASURED-INTRA-REF` | Recompute B minus A from retained projections and require agreement with recorded mismatch list | `producer_story_measurements` |

The last two tiers do not independently establish what full HTTP bodies contained. They are not promoted to raw-sequence verification. Successful generic arithmetic controls support the aggregate hypothesis on the recorded sequence; they do not prove all product business semantics or a root cause. Repeated creates returning the same resource identity are marked as an evidence limitation, not counted as independent resources.

`story_catalog.json` defines generic pattern predicates. `story_profiles.json` defines product aliases and behavior-signature candidate links to M-D1, M-D2, M-C1, W-F2 and the early Mealie contribution/copy observations. Profiles contain neither expected counts nor specific test IDs, seeds or stored response values. Candidate links are additive `known_bug_candidates` fields; they never increase `known_bug_occurrences`. The retained stories results omit observed SUT versions. Consequently these packages produce generic findings and candidate IDs, not version-confirmed known-bug credit. Shared root cause is not inferred. Severity remains subject to product context/human review.

## Validation and integration

See `VALIDATION.json` and `STORIES_REANALYSIS.md`. The four reanalyses used exact Git-retained evidence files at `weissye/vikunja_study@e54368795f0a908879d0bdc77f12e20cc8ad1a53`, assembled as explicitly labeled repository-subset ZIPs. NOTE files were excluded. Original full user-uploaded ZIP bytes were unavailable and were not claimed as tested. The original 1369-exchange login acceptance is the producer's reported v005 result; this release reruns its inherited synthetic login regression tests, not that unavailable original archive.

All inherited box tests plus stories counterexamples run in this release. No Windows PowerShell execution or new live experiment is claimed. Frozen older release files remain unchanged. To integrate, pin this release in a new producer configuration/revision, invoke it after packaging, preserve every exit/status and retain PARTIAL gaps. Never rewrite frozen toolkit tags or reinterpret exit 0 as no findings. The detailed producer handoff is `HANDOFF_PROMPT_HE.md`.
