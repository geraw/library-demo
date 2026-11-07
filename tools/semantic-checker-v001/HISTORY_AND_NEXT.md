# Historical reconstruction and next integration boundary

## Distinct components recovered

1. Generic JS generation: `openapi_to_sbt/` infers entities, references and dependencies and emits interfaces/stories. It does not itself prove arbitrary business rules.
2. Generator/artifact validation: `scripts/run_validation_suite.py`, `openapi_to_sbt/validate/static_validate.py`, `validate_artifact.py` check generation, consistency and reference comparison across Library/Garage/Pharmacy/NetBox.
3. Product observation/evaluation: common `scripts/http_trace_proxy.py`, per-system `evaluate_*_trace.py`, NetBox A2A prefix evaluator, plus the Library V38 sequence-local delta.
4. Current Library oracle: v006 `Ledger` + in-process Flask transport + public collection readbacks. Same code was used across all three generators, but its domain rules are specific to the current Library fixture.

The user's recollection of a multi-system framework was correct. Describing the current Library component as specific was accurate for that implementation, but did not account for this broader existing framework. Reuse it instead of rebuilding from zero.

## What v001 actually unifies

- One offline input normalization and case-boundary layer.
- One profile registry and report envelope, with domain semantics kept separate.
- Preserved historical rules, source hashes and historical regression tests.
- Current Library Ledger recomputation from tool/readback evidence; never trust previously stored verdicts.
- One PowerShell command; optional legacy collection/live entry points.
- Separate external findings and native tool results. Runtime-only smoke is never a semantic finding.

Existing historical results are not rewritten. The generator, OpenAPI contracts, SUTs, mutation switches and search scenarios remain unchanged.

## What is deliberately still pending

A product-independent engine needs declared semantics in addition to structural OpenAPI. Next move shared mechanisms out of domain code while preserving witnesses:

- Resource catalog: identity fields, list/detail/create/update/delete operations, state extraction and pagination.
- Relationship rules: parent/child identity, ownership, uniqueness, cardinality and declared lifecycle effects.
- Evidence capabilities: what can be concluded from request/response alone, what requires an independent readback, and what remains unknown.
- Rule instances: known-entity read, non-target preservation on deletion, rejected-write atomicity, declared update persistence and declared legal-operation acceptance.
- Transport adapters: recorded readback, HTTP probing and fixture-local calls. The engine should not depend on Flask.
- Generator adapters: native alerts AND independently retained/replayed sequence boundaries for Provengo, RESTler and EvoMaster; a flat campaign is diagnostic only.
- Scheduling/concurrency: preserve interval/actor evidence separately; serial state checking cannot establish linearizability.

Do not infer a loan limit, cross-household authorization policy or allowed cascade from property names. Such semantics must be explicit product configuration with provenance and modelling effort accounted for. Do not supply known failure sequences to baselines as discovery input. Compare generation reachability and native-vs-common-oracle detection separately.

## Acceptance before replacing the old evaluators

- Exact current Library diagnostic parity on the uploaded home/work traces.
- Healthy-control non-regression and no cross-test stitching.
- Positive and negative counterexamples for each declared rule and evidence mode.
- Missing scope/state evidence returns unknown, not pass/zero.
- Cross-product integration tests on actual frozen evidence, not only synthetic examples.

v001 starts that migration with recoverable, working adapters; it does not claim this acceptance set is complete for every article product.
