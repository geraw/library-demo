# Steps 3–4: collections, relationships, views and numeric actions

Version **009-dev.7**, 2026-11-02. The same runtime is vendored in the Library
benchmark. This milestone adds bounded checks, not a universal business oracle.
It does not resample Provengo, generate campaigns, or send new requests to the
real systems. Library acceptance uses small in-process SUT tests.

## Implemented behavior and evidence level

| Check | Evidence required | Result on contradiction |
|---|---|---|
| Conjunctive filters (Library B4) | Explicit affirmative operation description, unique declared query parameters, comparable returned scalar fields | Contract violation for a returned item failing a supplied predicate; no claim of completeness |
| Collateral deletion (Library B5) | Adjacent collection GET / successful item DELETE / same collection GET, unique identities, isolated serial capture | Violation only with both a complete-list declaration and non-target preservation policy; otherwise a conditional observation for unparameterized flat collections |
| Reference to absent resource | Same actor and post-write read interval, matching reference/resource names, observed 404/410 | Structural observation: 404 can reflect access policy, and relationship semantics are not guaranteed |
| Nested view after move | Entity preimage, nested view preimage, update and view readback | Observation of continued membership under another parent; flat lists are not parent membership |
| Aggregate transfer | Entity preimage, child and both parent metrics, applied move and both parent readbacks | Observation when the old-minus-child/new-plus-child hypothesis fails; additive semantics remain inferred |
| Scaling | Same action URI, two successive writes with different numeric factors, container preimages and responses | Observation of nonlinear quantity deltas; rounding/business rules may explain it |
| Copy references | Explicit copy/duplicate operation summary, source and copy, unique inferred internal reference-to-target correspondence | Observation when copied references do not resolve within corresponding copied targets |

The actual Library `/holds` contract does **not** promise a complete collection.
Therefore B5 is reported as `policy_observation`, not silently promoted to a
proven violation. Its acceptance flow adds a pre-delete GET; old runs without
that preimage are not retroactively treated as covered. B4 is a contract violation.

No checker reads story IDs, expected checks, mutation IDs, producer pass/fail,
or product bug catalogs. Test labels and expected reasons exist only in the
acceptance harness. The contract parser recognizes a narrow set of affirmative
sentences; this is not unrestricted natural-language understanding.

Relationship checks are bounded to 128 retained snapshots, a 32-exchange join
window, 256 KiB bodies, and 4,096 walked nodes. Actor/epoch/case changes, unknown
writes, unordered timestamps and body limits invalidate relevant observations.
Background concurrency is never asserted absent for historical journals.
The collection checker uses the existing 64 KiB state body budget.

## Verified results

- **183 analyzer unit tests**, including neutral-resource positive/negative pairs,
  duplicate query rejection, actor/epoch/time boundaries, ambiguous copy links,
  intervening writes, flat-view controls and offline four-configuration dispatch.
- **12 benchmark tests**. Live baseline/mutant acceptance covers B1–B5. Baseline
  counterparts have no semantic violations or policy observations in these flows.
- **14 real-evidence witnesses** replay independently from their retained HTTP
  evidence. All 14 synthetic repaired controls suppress the corresponding finding.
  Controls are counterfactual data, not additional successful SUT runs.

| Existing capture | New structural observations | Acceptance controls |
|---|---:|---:|
| Mealie v22rc2 | 7 reference-to-absent observations, 1 nonlinear scaling, 1 copy reference | 9 |
| wger v22rc | 3 aggregate transfer mismatches | 3 |
| Vikunja v22rc3 | 2 nested view membership observations | 2 |

These are **14 occurrences, not 14 distinct bugs or proven business violations**.
Reference 404s may be policy-dependent; scaling may be intentionally nonlinear;
views may be eventually consistent. Each record retains evidence line pointers,
contract provenance, the inference used, and explicit uncertainty.

The seven-system audit processed eight stored captures. All seven contracts
match their recorded contract hash (allowing a transport-added trailing newline).
The Mealie contract was recovered from `weissye/mealie_sbt_study`,
`model/mealie-openapi.v3.28.0.reviewed.json`, blob
`9ae6edeecab4f8b75aec460cb9b9795d9ee112d7`, SHA256
`90e19aa713ab4ba15352627aca7dc37290f868b213eb65a3e1564f3b7a7ff292`.
Kimai and Dependency-Track captures contain setup failures; zero semantic findings
there is **not** evidence that their business behavior is correct. Tandoor's 34
existing input-constraint observations remain separate. Older wger numeric
rounding is not covered by the new scaling rule.

Regression retains the Gitea G014 six 500-state-effect witnesses (four partial,
two applied only on comparable fields), four 4xx observations and ten rollback
controls. Full RESTler baseline replay: **2,499 product HTTP exchanges, zero
semantic/policy findings**, and the same five server-500 responses. A server 500
is not counted as a newly discovered semantic bug.

## Four Library configurations: honest coverage boundary

The available compact archives for EvoMaster, RESTler, Provengo sample10 and
Provengo Java do not contain `http.jsonl`. Only the separately supplied RESTler
baseline archive contains a full raw trace. Thus full historical mutant replay
for all four configurations remains **blocked by missing retained raw traffic**,
not completed by the small adapter-dispatch test. No new native campaigns ran.

From the existing checkout, update with `git pull --ff-only origin master`, then
reanalyze all raw traces still present locally without calling the SUT:

```powershell
& .\library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe `
  .\tools\natchan-box-v009\replay_library.py `
  --runs-root .\library\benchmark-v001\runs `
  --contract .\library\benchmark-v001\openapi.json
```

This creates a new sibling `analyzer-replay-*` directory. It preserves original
baselines, samples, traces and results. It reuses capture declarations only from
the matching cell's original `natchan-request.json`; it never invents isolation.
`replay-summary.json` lists each analyzed trace and configurations with missing
raw evidence. Existing compact summaries cannot replace discarded HTTP bodies.

## Reproduce acceptance from existing private study checkouts

```powershell
python .\tools\natchan-box-v009\acceptance_relational_real.py `
  --study-root D:\Yeshayahu\Temp\vikunja_study `
  --mealie-contract D:\Yeshayahu\Temp\mealie_sbt_study\model\mealie-openapi.v3.28.0.reviewed.json `
  --output .\step34-acceptance-new
```

Use actual existing paths and a new output directory. The manifest pins original
Git blob identities, content hashes and exact witness lines. Verification permits
CRLF/LF and terminal blank-line differences in Git checkouts; contract JSON is
canonicalized for content verification. The private original journals are not
republished. See `VALIDATION_DEV7.json` and
`tests/fixtures/step34-real-manifest.json` for machine-readable evidence.
