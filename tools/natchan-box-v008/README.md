# Natchan Box v008 — shared offline HTTP analysis

New release based on frozen v007, commit `5cd95f132aa11906d9e42705143f9706a866c403`. Python 3.10+, standard library only. Use a full `geraw/library-demo` checkout: older analyzer directories remain runtime dependencies. v007 and its study integration are unchanged. This analyzer sends **zero SUT requests**.

## Get this release from GitHub

Repository: [geraw/library-demo](https://github.com/geraw/library-demo), branch [`natchan-box-v008`](https://github.com/geraw/library-demo/tree/natchan-box-v008). This branch includes v007 and all older runtime dependencies; v007's branch and frozen files are preserved. v008 is not installed by pulling `master` or `natchan-box-v007`.

For a fresh, separate checkout:

```powershell
git clone --single-branch --branch natchan-box-v008 https://github.com/geraw/library-demo.git library-demo-natchan-v008
if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
Set-Location .\library-demo-natchan-v008
git rev-parse HEAD
python -m unittest discover -s .\tools\natchan-box-v008\tests -q
if ($LASTEXITCODE -ne 0) { throw 'Analyzer tests failed.' }
```

Or, from an existing `library-demo` checkout, keep its local files and create a separate worktree at the fetched release:

```powershell
git fetch origin natchan-box-v008
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
git worktree add --detach ..\library-demo-natchan-v008 FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw 'Worktree creation failed.' }
Set-Location ..\library-demo-natchan-v008
```

Choose a new destination if the example folder already exists. Record the full `git rev-parse HEAD` value in the study integration. The [Hebrew maintainer prompt](HANDOFF_PROMPT_HE.md) contains evidence requirements, commands, acceptance and remaining producer tasks.

## What changed

The same `shared_semantics.py` evaluates retained HTTP from Provengo, EvoMaster, Schemathesis and RESTler. Tool names are provenance, not semantic rule selectors. Product routes, projections, operator meanings, aggregate/contribution/copy hypotheses are JSON metadata bound to a recorded contract SHA256. Native tool reports and producer measurements remain separate evidence tiers.

Supported common families: deleted/stale references, absent-resource 5xx, projection update/delete/move, configured aggregate moves, enum arithmetic, scaled contributions and copy-internal-reference consistency. A common judge does not make missing HTTP, missing controls or different tool coverage equivalent. Unsupported business semantics are explicit limits.

Reference prerequisites are audited on **passing and failing** traces. A scenario that never established its intended relationship is not counted as an evaluated product check. Raw CONTRIB and COPY are now recomputed from request/response bodies when retained; producer STORY_CHECK results do not supply the answers.

See [GAPS_RESOLUTION.md](GAPS_RESOLUTION.md) for every item in the supplied v007 gap report and what remains unverified.

## Use in a pipeline

Create a request beside the immutable input ZIP:

```json
{
  "schema_version": "natchan-request/1",
  "run": {"id": "run-001", "tool": "provengo", "product": "mealie", "product_version": "unknown"},
  "evidence": {"adapter": "toolkit-v1", "archive": "review_stories.zip"}
}
```

`run` fields are assertions checked against recorded evidence. They cannot supply missing observed server versions. Retained story packages use `unknown`; the original login package records `v2.6.0` and must use that version. Alias `mealie-pg` maps to `mealie`, without proving database identity from the name.

```powershell
python -m unittest discover -s .\tools\natchan-box-v008\tests -q
if ($LASTEXITCODE -ne 0) { throw 'Analyzer tests failed.' }
python .\tools\natchan-box-v008\natchan.py --request C:\experiment\analysis-request.json --output C:\experiment\analysis-v008-001
$analysisExit = $LASTEXITCODE
```

Output must be a new directory. Keep the exact analyzer commit, request and input hashes, numeric exit and outputs with the experiment. Both ordinary and `python -I` entry points work. `Invoke-Natchan-Box-v008.ps1` is optional; it throws on nonzero exits. Use Python directly when a pipeline needs the numeric code.

| Exit | Meaning |
|---|---|
| 0 | Processing finished; COMPLETE or PARTIAL does not mean no bugs |
| 2 | Invalid request, invalid supported evidence/configuration, contradictory metadata, or freeze drift |
| 3 | Explicit unsupported interface/format/policy |
| 4 | Unexpected engine defect |

Check `result.json` **last**: it is the final commit marker. A producer run failure and an analyzer failure are separate states.

## Input adapters

| Adapter | Input | Semantic scope |
|---|---|---|
| `toolkit-v1` | Existing model/campaign/login/stories/baseline ZIPs, including supported nested seed ZIPs | Research HTTP uses the shared judge; established RT/atomicity/native readers remain; raw baseline capture is analyzed when present |
| `http-traffic` | Raw JSON, JSONL, HAR, or ZIP containing recognized captures | Shared HTTP rules for any recorded tool/product with matching metadata |
| `restler-network` | Native RESTler `network.*.txt`/`.log`, or a ZIP of such logs | Same shared judge; explicit metadata is needed |
| `gitea-native-tools` | Legacy Gitea EvoMaster/Schemathesis reports | Native-report/log scope only; explicit gap directs callers to the raw route |
| `provengo-native-lifecycle`, `historical-corpus`, `normalized-observations` | Existing legacy inputs | Preserved scopes; no new raw evidence is invented |

Toolkit baseline run folders can contain `http-evidence.json`, `traffic.har`, `traffic.jsonl` or `network.*.txt/.log` beside `run-meta.json`. Use its recorded `sut`, `tool`, `sut_version`, `contract_sha256`, and stable capture actor/reset metadata. Common analysis and native reports coexist. Without captured HTTP, `SEMANTIC_HTTP_TRAFFIC_MISSING` is reported. Existing test reports cannot be reverse-engineered into missing state transitions.

Standalone capture formats, metadata and examples: [HTTP_EVIDENCE.md](HTTP_EVIDENCE.md), `examples/http-traffic.request.json`, `examples/restler-network.request.json`. For toolkit packages use recorded result/run-meta metadata; external `configuration.traffic_metadata` is accepted only by the two raw adapters.

## Outputs and interpretation

| File | Meaning |
|---|---|
| `result.json` | Version, status, exit, counts, hashes of output artifacts |
| `findings.json` | Occurrences with tags, evidence tier, classification role, semantic comparisons, witnesses and optional unique server-log joins |
| `coverage.json` | Missing evidence, applicable rule coverage, all-outcome reference/operation audits, log-correlation audit |
| `provenance.json` | Input/configuration/engine hashes, actual adapter metadata, optional evaluation-freeze verification |
| `diagnostics.json` | Explicit invalid/unsupported/internal-failure reasons |
| `report.md` | Human-readable counts, candidates, raw comparisons, preconditions and gaps |
| `analysis.json` | Full successful engine output, including native reports and original measurement records |

`common_product_behavior_candidates` counts qualified raw semantic occurrences excluding test-precondition failures. `common_semantic_occurrences` also includes those failures. `producer_measurement_occurrences` remains separate. Common counts are **null** when no common HTTP evidence is available, not a clean zero. An observed zero means no supported finding under that retained evidence and configuration, not exhaustive coverage. Category counts `research_records`, `roundtrip_check_records`, `known_failure_records` are separate from finding counts. Multiple observations/tags can describe the same underlying bug: **do not sum them as distinct bugs**.

Every finding remains a candidate needing context; a behavior signature is not proof of root cause or product intent. Unknown observed versions never receive version-confirmed known-bug credit.

## Library: existing four-configuration route

The preserved Library provider and this release were rechecked on three complete original ZIPs covering sample-10, fixed Java, RESTler and EvoMaster. No engine changes were needed: the raw Library archive stage recomputes the observations, then `normalized-observations` classifies them through v008. All 44 source-level seeded-behavior matches agree. This is a configured **two-stage** route; `toolkit-v1` does not automatically recognize these Library archives. Native baseline detection and the new raw-traffic shared-judge metrics are not inferred from that export.

See [the compatibility report and exact reproduction steps](../../docs/library-study/2026-10-27/NATCHAN_V008_COMPATIBILITY.md). The original experiment's metadata profile is `library / issta-v006`; it is not a deployed product version. This check supplements the 29-story-subset acceptance above and keeps native test verdicts separate from Library domain observations.

## Product configuration and logs

See [SEMANTIC_CONFIG.md](SEMANTIC_CONFIG.md) and `schemas/story-semantics.schema.json`. Use embedded `story-semantics.json` or `configuration.story_semantics`, not both. Four bundled profiles: Gitea, Vikunja, wger and a bounded Mealie profile. Exact contract binding is mandatory. Mealie's original OpenAPI bytes were not retained in the available source corpus; the profile records that gap instead of claiming contract regeneration.

Server joins require a unique request ID, or explicitly enabled unique method/path/status/time matching with timezone-aware timestamps. JSONL or a configured named-group regex is supported. Ambiguous/unparsed lines remain gaps. A configured associated error signature is **server-reported context**, not an independently proven root cause; adjacent error lines are never assumed causal.

## Prospective evaluation

Prepare a mechanical freeze **before inspecting unseen result evidence**, with profiles derived only from permitted contract/configuration sources:

```powershell
python .\tools\natchan-box-v008\evaluation_freeze.py --semantic-profile C:\experiment\story-semantics.json --output C:\experiment\evaluation-freeze.json
```

Register/commit the file in the study protocol, then add `configuration.evaluation_freeze` to the analysis request. Code/rule/profile drift is rejected. This mechanism neither proves prior registration nor proves a dataset was unseen. A4's empirical held-out validation remains open; no Tandoor evidence was inspected in this release.

## Validation

275 tests pass, including correct behavior controls, missing/wrong preconditions, identical roleless HTTP across four tool labels, model/baseline integration, parser errors, log ambiguity, separate 294-RT fixture counts, freeze drift and a deliberately injected unexpected exception yielding exit 4. The RT fixture is not the original login ZIP. RESTler is tested against native-format fixtures and the official logger grammar, not a user RESTler campaign.

29 exact Git-retained story evidence subsets at producer `weissye/vikunja_study@62ff20a9da589e3b4ac18189e6f8f7f46f4ccde8` were reanalyzed: 4,903 research exchanges, 57 retained members; all process with exit 0/PARTIAL. Their 57 Git blob IDs were checked against the pinned repository tree. Missing server versions/manifests/logs are preserved as gaps. NOTE/SUMMARY prose is not an analyzer input. See `VALIDATION.json`, `REANALYSIS.json`, [STORIES_REANALYSIS.md](STORIES_REANALYSIS.md).

Original full story ZIPs, original login ZIP, original model packages, Windows PowerShell orchestration and a real RESTler archive were not available for this acceptance. No full-archive or held-out acceptance is claimed. Local outputs can contain source paths/data and require the study's redaction before sharing.

With a complete producer clone containing the pinned commit, reproduce the subset analysis:

```powershell
python .\tools\natchan-box-v008\validate_repository_stories.py --producer-repo C:\work\temp\vikunja_study --output C:\experiment\stories-v008-recheck
```

Detailed integration/producer acceptance instructions: [HANDOFF_PROMPT_HE.md](HANDOFF_PROMPT_HE.md). Producer code and frozen v007 integration were not changed by this release.
