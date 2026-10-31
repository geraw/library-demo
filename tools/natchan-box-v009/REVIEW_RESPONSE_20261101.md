# Response to the producer's v009 development review — 009-dev.3

Source: `weissye/vikunja_study`, `handoff/NATCHAN_v009_CHECK_20261101.md`
(Git blob `6cc49e4dd8d3bc7941e9532f574995c8d9b96797`). The source review describes dev.2
at `24d8c8e5a86fe80e81a19ceb9eae280c13e99eda`. Its reported traffic experiments were **not rerun** for this response.
The six contract derivations and freezes below were run independently against exact Git-blob-verified contract bytes.
No system result evidence was opened for those contract checks.

## Disposition of the requests

| Request | Dev.3 action | Acceptance / remaining scope |
|---|---|---|
| R1 Swagger 2 parameter `required` | Fixed: keep parameter-level boolean outside the schema. Actual object-schema `required` still must be an array. | Original Gitea/Vikunja contracts now derive and freeze; scalar runtime semantics remain bounded. |
| R2 large derived knowledge | Bound nested schema expansion to the levels needed for current scalar rules; retain explicit unknown nodes and deduplicate gap records. No larger memory cap or product-specific exception. | Dependency-Track now derives to 3,230,582 bytes under the existing 32 MiB limit. Nested semantics remain unimplemented, not silently supported. |
| R3 Django routes / missing bindings | Recognize item routes ending in `/{id}/` while preserving the exact declared route during matching. Add checks/reasons and schema pointers to every binding. Schema names such as `Patched...` select no rule. | Tandoor: 79 usable candidates, 15 unknown. wger: 54 usable, 10 unknown. These are contract bindings, not successful checks or bugs. |
| R4 undeclared-status noise | Separate `server_5xx`, `undeclared_status`, semantic and policy streams. One authoritative group array; partitions reference IDs without duplicating findings. Separate summaries in coverage and Markdown. | Undeclared 401/404 candidates are documentation/contract discrepancies, not independently proven product bugs. Existing verdict meanings are not retrospectively rewritten. |
| R5 create/update comparison | Still pending; next semantic priority. | S2 remains null. No product-specific rules or use of producer verdicts were added to fabricate this coverage. |
| R6 start-only captures | Explicitly report complete intervals, start-only, observation-only and missing timing. Accept start-only/observation-only under declared complete/exclusive/serial capture; reject contradicted order. | Serial execution remains a capture assertion, not a fact established by one instant. Journal `t_utc`/`observed_utc` is not reinterpreted as an interval. |

The original Kimai contract (not the tool-normalized copy described by the review) contains empty `[]` schema markers.
These and null schemas are recorded as unknown with exact pointers, never reinterpreted as valid array schemas.
The rest of that contract can now derive/freeze. This does not certify malformed schema fragments as valid OpenAPI.

## Independently reproduced contract acceptance

| Contract source | Operations | Derived bytes | Structural candidates | Candidates with scalar fields | Unknown bindings |
|---|---:|---:|---:|---:|---:|
| Dependency-Track original | 219 | 3,230,582 | 1 | 1 | 32 |
| Gitea original | 537 | 6,582,417 | 38 | 37 | 27 |
| Kimai original | 99 | 953,338 | 7 | 7 | 12 |
| Tandoor original | 351 | 3,108,992 | 79 | 79 | 15 |
| Vikunja original | 170 | 1,118,817 | 1 | 1 | 35 |
| wger original | 256 | 1,980,811 | 54 | 54 | 10 |

All six derived and froze with exit 0. See `CONTRACT_ACCEPTANCE_20261101.json` for exact source paths, blob IDs and
SHA256 hashes. Mealie's exact reviewed contract was not available in the checked repository locations, so no new
Mealie contract/run acceptance is claimed. Unchanged dev.2 Library retrospective results retain their recorded version.

Reproduce contract-only acceptance with a manifest containing `schema_version: natchan-contract-check/1` and a
`contracts` array of `{id, path, sha256}`. Paths are relative to the manifest. A sample shape is documented in README.

```text
python tools/natchan-box-v009/validate_contracts.py --manifest contracts.json --output new-contract-check-directory
```

## Interpretation of the supplied study results

- The review's Mealie `display` examples demonstrate a limitation of the generic persistence assumption. A server-derived
  field not marked read-only cannot reliably be distinguished from a persistence defect using this contract alone.
  Dev.3 adds no hidden Mealie exception. Keep independent candidate output and human triage separate.
- Zero evaluated fuzzer S1/S5 checks describes coverage under this judge, capture and rule subset. Binding limits,
  missing reads, global mutation invalidation, body budgets and timing/capture assertions contribute to abstention.
  It does not establish that a tool can never generate a useful prefix, or that all unevaluated prefixes are absent.
- A 5xx group is an operation/input/signature symptom group. Different causes within one operation may remain grouped.
  The reported operation counts are not independently verified root-cause or distinct-bug counts.

## Corrections/guidance for producer conversion

The HAR 1.2 format description defines entry `time` as total elapsed request time in milliseconds
([format description](https://www.softwareishard.com/blog/har-12-spec/);
[historical format draft, entries](https://webperfwg.org/specs/HAR/Overview.html)).
It is therefore not correct to state generally that HAR has no duration. A particular export may have unreliable or
inconsistent timing, but monotonic starts alone do not prove its durations are wrong. Do not remove contradictory
intervals merely to enable more semantic verdicts. Record the source hash, omitted fields, reason and independent
serial-execution evidence in conversion provenance. Client transaction intervals also do not by themselves prove
overlap inside the SUT; the judge currently abstains conservatively.

- For a journal timestamp written when the response completes, use `observed_utc` (or retained `t_utc`), not
  `started_utc`. Do not add latency to a completion timestamp to invent an end time.
- No Authorization header does not prove an anonymous principal: cookie, query-key and other authentication may apply.
  Record a principal only when the capture knows it; preserve unknown identity instead of inventing one.
- Do not silently fill a missing session with `A` unless the run metadata independently establishes a single principal.
- If resets/restores/recovery occur inside a run, advance the reset epoch at each boundary. Omitting a control endpoint
  from HTTP export must not erase a state reset while keeping the same epoch.
- Keep all normalization and timing omissions auditable. The analyzer accepts supplied capture facts but cannot prove
  their correctness after the original information has been removed.

## Compatibility and limits

Operational v008 is unchanged. Dev.2 remains reproducible at its recorded commit. Dev.3 needs regenerated knowledge
and a new freeze and belongs to a later development/evaluation version. No held-out or full semantic acceptance is
claimed; S2/S4/S6 remain unimplemented and the seven-system traffic comparison still requires reanalysis by its producer.

Validation: 103 v009 tests pass; all 275 operational v008 tests pass unchanged.
