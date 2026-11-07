# Natchan: historical reconstruction and implementation plan

Date: 2026-10-21. Scope: results analysis, independent evaluation and finding qualification. This is a design/audit deliverable; no runtime behavior or research scores were changed.

## Decision

Build on the historical evaluators and collectors. Do not implement another evaluator from scratch, and do not treat the two new v001 wrappers as the complete historical foundation. There are at least three complementary families:

1. FSE v38: three-tool result collection, shared HTTP traces, per-product semantic evaluators and sequence-local analysis.
2. TSE OpenAPI verifier: a manifest-driven runtime evaluator with contract, state and concurrency witnesses; multiple historical branches include later fixes absent or incompatible in other branches.
3. Product research qualification: identity/scope audits, serial controls, readbacks, source/log correlation and evidence packaging, especially Mealie, Keycloak and Vikunja.

The generator can supply an independently versioned verification manifest. Natchan consumes that manifest and execution evidence; it does not require regenerating JS or modifying baseline inputs. Static generator validation and sampled-event audits remain separate evidence classes.

## Sources and coverage

See `archive_inventory.json` for 29 retrieved ZIPs, full member inventories, archive hashes and analysis-source hashes. Two generic-fix archives have duplicate content; archive count is not independent implementation count. See `repo_sources.json` for eight directly retrieved TSE files pinned to commit `0a3eb528a4cfa13a3c91d02e67aea195efe73a31`. Existing FSE originals and hashes are preserved in `tools/semantic-checker-v001/provenance.json` and `tools/run-analyzer-v001/history/` at Library commit `ee89c5ac026aea174f1cd07b3c2065076080c453`.

Library searches also identified larger version families for Gitea, Mealie, Keycloak and Vikunja, plus historical conversation evidence. Selected archives were downloaded and inventoried; analysis-relevant Python members were inspected. An inventory entry does not mean every file, embedded archive or historical execution was audited. Metadata-only control/handoff/collector packages are not runtime evaluators. This is a broad reconstruction of the accessible sources, not proof that every past project or every version has been recovered. Mealie/Gitea/Keycloak search result pagination and older unlocated studies remain an explicit discovery backlog. Do not claim complete historical coverage before closing that backlog.

## Reuse map

| Family | Concrete source | What to reuse | Qualification / limit |
|---|---|---|---|
| FSE Library/Garage/Pharmacy/NetBox/Todoist | v38 `scripts/evaluate_*_trace.py`, Library sequence-local delta; frozen under semantic-checker vendor | Existing product rules, sequence parsing, negative examples | Versioned product semantics; Pharmacy hidden markers diagnostic only; Todoist runtime smoke is not semantic coverage |
| Three-tool comparison | v38 `experiments/netbox_a2a/collect_a2a_results.py`, `evaluate_netbox_a2a_trace.py::parse_native` | Tool inventory, native-vs-common distinction, reachability | Remove latest-run collapse, missing-as-zero and unverified input-parity assertions |
| Current Library | campaign-v006 `Ledger` / `observed_server_v006.py`; v011 fixed Java evidence | Business-rule witnesses, independent readbacks, taint and case boundaries, healthy-control pairing | Library-specific; native failed test is not unique confirmed bug; observer traffic is not tool traffic |
| Generic TSE verifier | `generator_baseline/openapi_to_sbt/evaluate_verifiers.py` | Contract/state/concurrency layers, witness reasons, coverage, request preconditions | Requires its manifest dialect; some epoch/group conventions tied to generated runtime |
| Early generic/Gitea fixes | v0.25.6 delta; stage6 generic fix and stage6_11 | Historical lineage, accepted/rejected request handling and identity change logic | Compare function-level variants; do not concatenate whole files |
| Immich causal prefix | prefix evaluator RC2a, `tests/test_causal_prefix.py` | Same-resource, same-story, completed-before-epoch prefix qualification; specific oracle precedence | Prefix without serial control remains inconclusive |
| Mealie interference | v0268 evaluator, `tests/test_intervening_write_verifier.py` | Intervening write invalidates attribution to an earlier epoch | Preserve positive and negative clean-read controls |
| Empirical replay | empirical evaluator replay delta, `tests/test_empirical_update_delete.py`, frozen replay script | Compare both serial orders to race, separate server-error candidates from semantic verdict | Branch uses a different manifest/group dialect from pinned TSE main |
| Immich concurrency specificity | reevaluation delta, `test_concurrency_specific_oracle.py` | Reverse serial control and precise oracle choice | Branch differs from pinned main; must preserve regression before merging |
| Gitea research triage | `scripts/triage_gitea_stage6.py` | Finding qualification, valid setup/identity witnesses, replay outcome classification | File mixes offline summarization and live writes; extract offline part; never run replay during analysis |
| Mealie decisions | `scripts/analyze_mealie_decision.py` | Frozen witness explanations, overlap/prefix/PUT outcomes, missing-body limits | Some inputs are already-evaluated verdicts; distinguish imported claim from recomputation |
| Mealie F04/F05 | consistency v006 `package/analyze_evidence_v006.py`; observation `tools/audit.py` | Nested evidence inventory/hashes, actor/group/household identity, owner before/after readbacks, rejected-write state changes | Explicit campaign step specs, not universal inferred authorization; no root-cause or policy inference from 500 |
| Keycloak | readback binding delta; `verify_keycloak_user_readback.py`; v52 serial oracle | Identity-bound runtime readback and serial qualification | Live probes are collectors/experiments, not offline analyzer functions |
| Keycloak sampled audit | v57 `audit_keycloak_pilot_v57.py`; `audit_parallel_crud.py` | Label static/sample checks explicitly; producer binding checks as diagnostics | Their PASS does not prove HTTP execution, real overlap or SUT correctness |
| Vikunja lifecycle | `evaluate_vikunja_interleaved_bp.py`, `evaluate_vikunja_multi_resource.py` | Lifecycle/relationship resource checks, multiple resource identities and operation evidence | Expected task/label/comment counts and trace conventions need explicit profile config |
| Vikunja concurrency | increment6 conflicts, increment8 epochs, increment8_2 differential archives | Conflict checks, true-concurrency evidence requirements, backend comparison tests | Keep static manifest validation distinct from actual interval evidence |
| Vikunja schedules | `analyze_vikunja_bp_schedules.py`, UTF16 fix v4 | PowerShell BOM/BOMless UTF16 decoding, intent/permit fingerprints, empty parse failure | Schedule variation does not prove HTTP overlap or a defect |
| Handoff/acceptance | Vikunja v103/v112/v119, gap completion v008; Mealie supervisor/collector | Reproduction inventory, checksums, evidence requirements | Packaging/acceptance checks are not bug detectors |
| Current thin integration | `tools/run-analyzer-v001`, `tools/semantic-checker-v001` | Public entry point, run inventory, unknown values, input fingerprints, product/tool registries | Initial bridge only; RESTler file count is not bucket/unique-bug count; boundary import incomplete |

## Compatibility experiment performed

Four historical test modules were run unchanged against their own archived evaluator implementations: causal prefix 2/2; intervening write 2/2; empirical update/delete 6/6; concurrency specificity 1/1. Total 11 passed. This verifies selected local evaluator regressions, not SUT execution or all historical tests.

The same 11 tests against pinned TSE main yielded 4 passes and 7 failures: six empirical tests hit a manifest `method` mismatch; the reverse-control test returned a different reason. These are cross-version compatibility failures, not evidence of seven product defects. `regression_checks.json` records the commands' outputs. Preserve both dialects until an explicit conversion is tested. Selecting the latest file by date would discard or break behavior.

## Target behavior and report model

One offline analysis command consumes a run manifest or a supported frozen archive. Tool adapters decode native artifacts; evidence adapters decode HTTP/event streams; rule engines evaluate versioned product semantics and generic verifiers; qualification joins witnesses and controls. Product and tool registries are independent. A new tool must not require editing product rules, and a new product must not require editing native readers.

Required run keys: run ID, tool/version/configuration, product/version, variant/mutations, seed, budget, stage exits, clock origin, inputs and hashes. Required event keys where available: source artifact/member/offset, test/session/reset/epoch identity, actor, method/path, actual request/response IDs, interval timestamps, response status/body completeness and evidence role. Unknown fields stay unknown. Preserve raw evidence and all repeated runs.

Each finding retains rule ID/version/provenance, event references, preconditions, expected/actual behavior, identity/state witnesses, interference checks, control matches, qualification status, native alert links and limitations. Report separately:

- Execution and infrastructure outcomes, including compiler/engine/postprocessor stages.
- Native tool alerts with their original metric and evidence; no conversion of FAIL lines, potential faults or bucket files into an interchangeable bug count.
- HTTP anomalies and contract deviations; expected rejection and invalid inputs are qualified first.
- External semantic observations and qualified findings; unknown scope/readback is not a pass.
- Reachability and evidence sufficiency: generated, sampled, executed, precondition reached, observable, externally detected, natively reported.
- Occurrences, failed tests, finding groups and mapped benchmark bugs as separate quantities. Grouping records its rule/confidence; do not deduplicate unrelated products/versions/actors.

Do not equate a repeated seeded-bug manifestation with independent discovery. Do not infer arbitrary business rules from OpenAPI property names. Record semantic assumptions, their provenance and modelling effort. Prefix/control markers may qualify external evidence but must not silently be supplied as search guidance to baselines. A flat campaign is never relabelled a single test to manufacture sequence-local proof.

## Implementation work packages

| Order | Work | Reuse first | Acceptance / concrete output |
|---|---|---|---|
| 0 | Finish source lineage and freeze golden corpus | Inventory here, old originals, archived tests | Deduplicate file hashes; compare all evaluator functions and manifest dialects; list every unresolved source family; immutable originals and expected outputs |
| 1 | Evidence schema and archive import | FSE collector, Mealie nested archive inventory, current v001 envelope, Vikunja encoding | Versioned run/event/finding schemas; malformed/missing/partial artifacts explicit; limits on nested archives; redacted reproducible artifact links |
| 2 | Reconcile generic verifier branches | TSE evaluator + prefix/interference/empirical/specificity deltas | All 11 historical tests pass through explicit dialect adapters; additional healthy/missing-evidence cases; versioned witness output; old behavior changes documented |
| 3 | Native adapters and sequence boundaries | FSE native parsing, fixed Java JSONL, v001 adapters | Provengo, RESTler and EvoMaster fixtures with native metric provenance; actual RESTler bucket parsing; test/reset scope established or unknown; no cross-case stitching |
| 4 | Product profiles and qualifications | Historical per-product rules, Library Ledger, Mealie identities, Gitea triage, Vikunja lifecycle | Library first, then Garage/Pharmacy/NetBox and Mealie/Keycloak/Vikunja/Immich; explicit supported rule/evidence matrix; Todoist smoke stays limited |
| 5 | Controls and concurrency | Empirical serial controls, prefix/reset checks, actual intervals, backend differentials | Both serial orders where required; no overlap => no concurrency claim; same identity/resource/reset verified; intervention => inconclusive; retain clock uncertainty |
| 6 | Unified reports and migration | Existing JSON/CSV summaries, native-vs-common separation | One witness-oriented readable report and machine JSON; per-tool/product coverage and gaps; deterministic grouping; no incomparable count aggregation |
| 7 | Dual analysis and release | All frozen legacy outputs + new analyzer | Run both on the same frozen inputs, review every difference, record approved corrections; Windows PowerShell entry point; no API calls during offline analysis |

Dependencies: 0 precedes core selection; 1 supports 2/3; 4 uses 1/2/3; concurrency work may start from preserved tests but official reporting requires 5 qualification. No UI or live replay is needed for the first release. Live collectors/replayers remain separate opt-in commands with their own manifests and side-effect boundaries.

## Golden corpus and release gates

Include real frozen positive, healthy and inconclusive evidence for every supported profile. Include current Library healthy-control failures, mutation arms, fixed Java evaluation and observer evidence without conflating verdicts. Include FSE sequence-local versus campaign-only examples, NetBox engine-success/postprocessor-failure, UTF16 schedule logs, stale Gitea identity/setup, Keycloak sampled-only traces, Mealie same-reader ownership and intervening-write cases, Immich serial/race controls. Where actual evidence is not yet recovered, mark that case as missing and use synthetic unit tests only as unit tests.

For every rule test: actual violation; legal counterexample; missing response/readback; wrong actor/resource; reset/case boundary; intervening write; incomplete run. Require deterministic output and explicit unknown states. No release claim for an unsupported tool/product cell. No rerun of a generator required to audit a saved run. No silent rewriting of historical research tables.

## Immediate next step

Implement package 0 as a reviewable lineage/reconciliation change: compare archived evaluator functions and manifests, freeze the eleven tests plus representative evidence, then propose the core extraction. Keep existing v001 commands available during migration. Do not add another parallel engine before this reconciliation.


## Stage 1 implementation checkpoint — 2026-10-21

Implemented in `tools/natchan-v002/`: bounded offline ZIP inventory, versioned evidence envelope, explicit source locations, separate ToolGateway and ProductGateway protocols/registries, generic recorded JSON and fixed-Java/Library initial gateways. The user requires independent gateways in both dimensions. Layout adapters remain separate from product semantics. Existing v001 evaluators remain unchanged; native gateway migration and verifier reconciliation are pending. Eleven ingestion tests passed; the real work v011 ZIP imported 3 arms, 542 native records per arm, 30,678 events, 77 members and zero ingestion issues. This is not a new bug-finding result. Additional requirements are expected and can extend the interfaces.


Stage 1 contract completion: `tools/natchan-v002/GATEWAY_CONTRACTS.md` defines and implements explicit capability declarations, required/optional artifacts, record output validation, missing-evidence handling and independent extension. Eighteen tests passed; the real archive remains ingestion-complete with no new bug scores. Next stage is connecting the preserved Library evaluator and proving legacy parity.


Library provider connected through ProductGateway.evaluate in `tools/natchan-v002/analyze.py`. No historical rule implementation changed. Full three-arm legacy report parity and archived candidate/native parity verified; input hashes verified. Twenty-six tests pass. Reports separate external candidate occurrences, recorded native failures and explicit healthy-control comparisons. See CONNECTION_VALIDATION_20261021.json. Next migration cells remain RESTler/EvoMaster native gateways and additional product providers.


Classification checkpoint v003: implemented public JSON catalog/schema/template, generic and product-scoped patterns, five Library known-bug definitions, draft Vikunja identities, deterministic multi-label classification/grouping, normalized-observation adapter and JSON/Markdown reporting. Library evidence is recomputed and actual readbacks drive collateral-deletion association; all 22 occurrences map to bug 5 with five later native 404 consequences. Twenty-one v003 tests plus twenty-six v002 tests passed. Actual raw Vikunja/Gitea format qualification and named-bug completion remain pending incoming artifacts. See tools/natchan-v003/README.md.
