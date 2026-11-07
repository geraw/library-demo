# Semantic requirements for the external analyzer — research side (31 Oct 2026)

**Purpose.** This document states what the study needs from the external analyzer (Natchan) so that it can act as a
*common, independent semantic judge* for SBT and for the baseline tools (Schemathesis, EvoMaster, RESTler). It states
requirements, inputs, protocol and reporting. It does **not** prescribe the analyzer's internal design, rules or
algorithms; those belong to the analyzer's developers.

**Why.** Today the analyzer judges mainly server errors and a few reference patterns. Most of the study's confirmed
defects are semantic (silent changes, create/update disagreement, partial commits, stale views, dangling references).
They are confirmed only by our own stories and by manual reproduction, so the tool comparison (TSE RQ3) has no common
semantic judge. The analyzer can become that judge only if it understands the system's entities and relations, and only
if that understanding is as independent of SBT as it is of the other tools.

---

## 1. Principles (binding)

| Id | Principle | Meaning |
|---|---|---|
| P1 | Tool-neutral | Every tool's evidence is judged by the same knowledge and the same procedure. Nothing in the judgement may depend on which tool produced the traffic. |
| P2 | Contract-only knowledge | Knowledge about the system comes from the system's public OpenAPI contract (and the observed traffic), never from SBT's stories, oracles, compiled JS or verdicts. |
| P3 | Frozen before evidence | The knowledge derived for a system, the analyzer version and its configuration are frozen (hashed and committed) before any evidence of an evaluation cycle exists. |
| P4 | No producer verdicts | The analyzer never reads a tool's own pass / fail labels as truth. Producer measurements may be shown beside its own verdicts, never merged into them. |
| P5 | Explicit abstention | When evidence or knowledge is missing, the verdict is *not evaluable* (null), never *consistent* and never zero. |
| P6 | Reproducible | The same inputs give the same outputs, byte for byte, on any machine. |
| P7 | Evidence-linked | Every verdict points to the exact recorded requests and answers it rests on. |

## 2. Inputs: allowed, conditional, forbidden

| Input | Status | Condition |
|---|---|---|
| The system's OpenAPI contract (as served by the system, hashed) | **allowed** | the same file all tools received; its hash is recorded |
| The tool copy of the contract (base path applied, recorded normalizations, session-ending paths removed) | **allowed** | the normalization record travels with it |
| Raw HTTP traffic of a run (request + answer, in order) | **allowed** | from any tool, in a documented format |
| The SUT's own log for the run window | **allowed** | for correlation of server errors only |
| Run metadata (tool, repetition, SUT version, start state: snapshot or not) | **allowed** | |
| Knowledge derived by the analyzer itself from the contract | **allowed** | frozen per P3 |
| Knowledge derived by SBT from the contract (SBT's entity table) | **conditional** | only if (a) it is frozen and registered before the cycle, (b) the paper reports that the judge shares SBT's reading of the contract, and (c) a second judgement with the analyzer's own derivation is reported beside it. Default: not used. |
| SBT's stories, compiled JS, family definitions, oracle code, STORY_CHECK records | **forbidden for judging** | allowed only for debugging outside an evaluation; never in an evaluation run |
| SBT's or any tool's verdicts, failure labels, bug ids | **forbidden** | |
| The system's source code | **forbidden** | the judge stays black-box like the tools |
| Knowledge added after looking at the evaluated evidence | **forbidden** | goes into the next frozen version only |

## 3. Knowledge the analyzer must be able to hold about a system

The analyzer must be able to represent, for each system, at least the following, each item **with its provenance**
(contract location, e.g. JSON pointer) or marked **unknown**:

| K | Knowledge | Source in the contract |
|---|---|---|
| K1 | Resources / entities and their identifier field(s) | schemas, path parameters, response bodies |
| K2 | Operations and their role: create, read one, read many, update (full / partial), delete, action | method, path shape, operationId / summary / description, request / response schemas |
| K3 | Which operations act on the same entity, and where it is read back | path templates, response schemas |
| K4 | Fields per entity: type, format, enumeration, bounds (length, range), required, read-only / write-only | schemas |
| K5 | References between entities: which field names which entity, cardinality (one / many), embedded vs by id | field names, `$ref`, id formats, path nesting |
| K6 | Parent / child placement (nested routes, child arrays inside parents) | paths, schemas |
| K7 | Declared error answers per operation | responses |
| K8 | Authentication schemes and session-ending operations | securitySchemes, paths |

Ambiguity is expected (contracts often do not say whether `POST` creates or updates, or which field references what).
Ambiguous items must be marked as such and excluded from verdicts that depend on them (P5), not guessed silently.
The derivation must be documented and versioned; its output for each system is frozen per P3.

## 4. Evidence the analyzer must accept and require

| E | Requirement |
|---|---|
| E1 | Traffic as ordered request / answer pairs with method, full URL (path + query), request headers (secrets redacted), request body, status, answer headers, answer body. Formats needed now: HAR 1.2 (Schemathesis; RESTler converted by the study); a documented journal format (SBT). |
| E2 | Order and grouping: run, repetition, and — where the tool exposes it — test case / sequence, so that "a later read of the same object" is defined. |
| E3 | Start state of the run (fresh snapshot or accumulated), because it changes what a read can expect. |
| E4 | For a tool without a traffic record (EvoMaster today): explicit *not evaluable* for every semantic property; only SUT-log correlation may be reported, labeled as such. |
| E5 | Size: a 20-minute run of a fuzzer (about 90,000 exchanges, several hundred MB of HAR) must be processed, or refused with a documented input error — not an internal error. |
| E6 | Malformed or partial evidence is refused with a documented code (exit 2 / 3), never crashes (exit 4). |

## 5. Semantic properties the judge must be able to evaluate

These are the property **classes** the study needs judged across all tools. For each, the requirement states what a
verdict means and what evidence it needs; how the analyzer detects it is its developers' design.

| S | Property class | Holds when | Needs (knowledge / evidence) |
|---|---|---|---|
| S1 | Read-back consistency | an accepted write is reflected by a later read of the same object (value kept, or a declared transformation) | K2, K3, K4; a successful write and a later read of the same object in the same run |
| S2 | Path consistency | the same value is treated alike by the paths that accept it (create vs update; one entity vs another with the same declared constraint) | K2, K4; the same field value sent on two paths |
| S3 | Constraint conformance | a value outside a declared bound / format / enumeration is refused, not stored | K4; a write with such a value and its answer or a later read |
| S4 | Reference integrity | a stored reference names an existing object; deleting a referenced object leaves no dangling reference, or is refused, or cascades — consistently | K5, K6; create, reference, delete, later read |
| S5 | Failure atomicity | a write answered with an error changed nothing | K2, K3; the failed write and a read before and after |
| S6 | Placement / view consistency | a child appears exactly where its parent's views say, and moves / deletes are reflected | K6; child writes and parent reads |
| S7 | Error answers in context | a 5xx (or an undeclared status) is attributed to an operation, an input class and, where the SUT log allows, a root-cause signature; repeated occurrences of one cause are grouped, not summed | K2, K7; traffic + SUT log |

Each verdict has exactly one of four values: **violation** (a product-behavior candidate), **consistent**,
**not evaluable** (precondition or evidence missing — e.g. the referenced object was never established), **policy
observation** (the contract leaves the behavior open, e.g. cascade vs refusal). Preconditions must be checked from the
evidence itself: a property is judged only if its prefix (the object exists, the reference was established) is visible
in the traffic.

## 6. Output and counting

| O | Requirement |
|---|---|
| O1 | Per verdict: property class, operation(s), entity, field (if any), verdict value, the evidence records it rests on, the knowledge items it used (with provenance). |
| O2 | Grouping into **candidate root causes**: occurrences of the same property class on the same operation and input class are one candidate with a count. Counts of occurrences are never presented as counts of bugs. |
| O3 | Per tool and run: number of exchanges judged, verdicts per class and value, abstentions per class with reason. |
| O4 | The common output schema is identical for every tool. |
| O5 | A share copy without local paths, user or host names (as today). |

## 7. Freeze and evaluation protocol

1. Before a cycle: analyzer version (commit + file hashes), derived knowledge per system (hash), configuration and
   evaluation-freeze file are committed. Any change afterwards is a new version and applies to the next cycle only.
2. The analyzer is run on every tool's evidence of the cycle, including SBT's, with no per-tool configuration.
3. Verdicts are triaged by the researchers *after* the analyzer ran; triage results are reported beside, never fed
   back into, the cycle's analyzer output.
4. Post-hoc analyzer versions may be run on old evidence, but are reported as post hoc and never pooled with held-out
   judgements (as for the toolkit).

## 8. How the judge itself is validated (before it is trusted in the paper)

| V | Requirement |
|---|---|
| V1 | **Ground truth set:** the study's confirmed defects with their recorded evidence (findings index) form a reference set. The analyzer's derivation must not be tuned on this set's systems for the held-out evaluation; it is used to measure recall on development evidence only. |
| V2 | **Recall:** for each confirmed defect present in some tool's evidence, report whether the judge marks it as a violation of the matching class. |
| V3 | **Precision:** on a sample of the judge's violations (all, if fewer than 100), report the share confirmed by direct reproduction with a control request. |
| V4 | **Negative controls:** runs on behavior known to be correct (e.g. stories that pass, replays answered 2xx with a correct read-back) must yield no violation. |
| V5 | **Abstention rate:** report how often each class is not evaluable, per tool; a judge that abstains on most of a tool's traffic must say so. |
| V6 | **Agreement with manual triage:** on a sample, report agreement between the judge's verdict and the researchers' triage (e.g. Cohen's kappa). |
| V7 | **Held-out:** the headline numbers come from a preregistered cycle on a system none of the analyzer's derivation, the toolkit or the researchers had examined. |

## 9. What the paper will report about the judge

- The inputs it used (Section 2) and the statement that it had no access to SBT's stories or oracles.
- Its version, freeze hashes and the derived knowledge per system (in the replication package).
- Per tool and system: verdicts per property class, candidates after grouping, abstentions.
- Its validation (Section 8): recall on the reference set, precision by reproduction, negative controls, agreement.
- Its known limits, including the defects already met (native RESTler logs refused; a large package causing an internal
  error) and any property class it does not cover.

## 10. Out of scope

- Judging with knowledge from the source code or from a language model whose output is not frozen and reproducible.
- Repairing tools' runs (e.g. re-authenticating a tool that logged itself out): the judge reports what the evidence
  allows (Section 5, *not evaluable*), the producer fixes the run.
- Any change of a tool's verdicts.

## 11. Immediate needs of the study (order of priority)

1. S7 for all tools now (server errors grouped by operation and root-cause signature) — closes the counting gap of
   the baselines v2 comparison.
2. S1, S2, S5 (read-back, path consistency, atomicity) — the classes where the confirmed SBT findings concentrate and
   where the tools are expected to be blind; the comparison is meaningful only if the judge can see them in any tool's
   traffic.
3. S4, S6 (references, placement) — present today in part; extend to all tools' traffic.
4. E5 / E6 robustness (large packages; documented refusals).
