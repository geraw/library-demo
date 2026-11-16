# v013: the single-event model under the guided catalog, the observer, and unguided sampling

v013 is the first campaign that runs the **repository's live model** (`library/provengo`, branch
`single-event-actions`) rather than a frozen copy of the old one. It replaces nothing: v012 → v011
→ v009 → v006 → v004 keep replaying their frozen inputs and remain the historical evidence.

## What changed in the model, and what that broke

Every action in `interfaces.library.js` now sends exactly one REST request. There is no
`requestOneOfDirect`, no `data.model = {name, valid}` block, no valid/invalid variant names, no
retry-until-valid loop, no malformed request (missing fields, wrong types, bad path ids), and no
`PUT` (405) probe. Negative checks are business-rule rejections only: deletes blocked by a loan
or hold, loans the rules forbid, nonexistent or deleted entities. Events are named after the
HTTP verb; the logical ids live in `data.parameters`; list reads are described as
`Read: <list> list for <Entity> <id> after create|delete`.

Consequences for the experiment code (survey of 2026-11-16, all file references on `master`):

| Dependency | Where | Effect of the new model | v013 answer |
|---|---|---|---|
| Action matching by `data.model.name` containing `valid` | `src/StrictGuidedRun.java` `chooserName`/`chooserNameMatches` | Every step STUCK at step 1 (name is `"POST"`) | `V013Match.actionName()` derives the old-style name from method + path + expected codes + parameters; one anchored edit in a frozen copy (`patch_runtime_v013.py`) |
| Rejection = expected code 400 only | `expectsRejection` | 404 checks not recognised | Covered by the derived name (`(invalid - expects [404])`) |
| Old argument orders | `campaign-v004/business_stories_v004.js` | `createHold`, `deleteHold`, `verifyLoanExists` mis-bound | `business_stories_v013.js` |
| `requestOneOfDirect` filter, `randomInt()` replacements | `campaign_v004.py prepare()` | `RuntimeError` / silent no-op | `prepare_model_v013.py` |
| `requestOneOfDirect` adapter test | `test_profiles_v004.js` | Fails | `test_v013.py` |
| Frozen v011 catalog hash, 542-count gates, preflight anchor | v010-v012 | Untouched; they still run their frozen model | Not changed |
| Observer ledger, `counts()`, semantic checker, natchan catalogs | HTTP level | Unaffected | Reused as is |

## Files

| File | Role |
|---|---|
| `prepare_model_v013.py` | Snapshot of `library/provengo` with a rules **profile** (`original`: one active loan per reader, as `sut.py`; `contract`: the experiment contract of `sut_buggy_issta.py` with the v004 workload bounds 5 loans / 5 holds / 3 per pair) and a **stories** choice (`full`: the repository stories; `business`: successes and reads only) |
| `patch_runtime_v013.py` | Frozen `StrictGuidedRun` copy: the four v011 execution edits plus the one matching edit; the scenario catalog section is checked byte-for-byte |
| `V013Match.java` | Transport-shape action naming for single-event REST events |
| `V013Scenarios.java` | 26 added scenarios: the five ISSTA triggers, read-bearing chapter-3 flows, bounded extremes (16 `COMMON`, legal under both profiles; 10 `CONTRACT`, multi-loan readers) |
| `V013GuidedSuiteHarness.java` | Runs catalog and/or additions, one fresh runtime per scenario, case boundary through the observer or the SUT's `/reset` |
| `guided_suite_v013.py` | Orchestrator (Linux and Windows): prepare, patch, compile, transport self-checks, arms, `results.json`, review ZIP |
| `sample_coverage_v013.py` | Unguided `provengo sample` coverage: action kinds, abstract states, trigger reachability, degeneracy indicators |
| `business_stories_v013.js` | Business profile for the single-event interface |
| `test_v013.py` | Unit checks (patch anchors, model preparation, classifier, trigger predicates; Java compile with `V013_JAR`) |

## Run

```bash
# Contract profile, fixture behind the observer, healthy control + five isolated mutants
.venv/bin/python library/ess-experiment/campaign-v013/guided_suite_v013.py \
    --repo . --jar ~/provengo/Provengo-2026-01-10.uber.jar --profile contract --arms none,1,2,3,4,5

# Original rules against the original server (reachability only, no observer)
.venv/bin/python library/ess-experiment/campaign-v013/guided_suite_v013.py \
    --repo . --jar ~/provengo/Provengo-2026-01-10.uber.jar --profile original --sut original --arms none

# Unguided sampling coverage
.venv/bin/python library/ess-experiment/campaign-v013/sample_coverage_v013.py --repo . --profile contract --size 50
```

On Windows replace `.venv/bin/python` with `.venv\Scripts\python.exe`; nothing else differs.
Requirements: the repository `.venv` with Flask, a JDK, a local Provengo JAR (the `provengo`
CLI on PATH for sampling). Ports 23243/23244 (observer) or 23242 (original SUT) must be free.

## Results on this machine (2026-11-16, Provengo-2026-01-10.uber.jar, Java 25)

### E1: guided catalog + v013 additions, contract profile, fixture behind the observer

Run `runs/guided-v013-20261116-185353-1652951` (review ZIP next to it). 568 scenarios per arm
(542 catalog + 16 common + 10 contract), full stories, 5 readers / 5 books. Both transport
self-checks passed (one real 201 loan with server ids; the 202-expecting copy failed natively).
Each arm took 47-66 s; the whole run 5.5 min.

| Arm | Reached as expected | Blocked as expected | Stuck | Reached but expected blocked | Native failures | ... of which control-eligible | Clean observer candidates |
|---|---:|---:|---:|---:|---|---|---|
| control (`none`) | 435 | 131 | 0 | 2 (cases 73, 77) | 73, 77 | none | 0 |
| bug 1 | 433 | 131 | 2 | 2 | 73, 77, **561, 562** | 561, 562 | 2 × bug-1 (561, 562) |
| bug 2 | 434 | 131 | 1 | 2 | 73, 77, **546** | 546 | 1 × bug-2 (546) |
| bug 3 | 434 | 131 | 1 | 2 | 73, 77, **567** | 567 | 5 × bug-3 (incl. 567) |
| bug 4 | 431 | 131 | 4 | 2 | 73, 77, **543, 544, 545, 553** | all four | 4 × bug-4 (the same four) |
| bug 5 | 430 | 131 | 5 | 2 | 73, 77, **80, 257, 260, 266, 433** | all five | 25 × bug-5 (incl. those five) |

Every mutant arm has at least one control-eligible native failure whose case also carries a
clean observer candidate labelled with that bug: 561/562 are the ISSTA-1 fourth-loan scenarios
(the fourth `createLoan` got 409), 546 is the ISSTA-2 third borrowing (409), 567 is the reader
whose second return finds its loan already gone (bug 3 removed both loans on the first return),
543-545/553 are the detail reads (`GET /books/{id}` answered 404 for an existing book), and the
five bug-5 cases are exactly the five v011 reported (`deleteHold` of a hold that the earlier
deletion had already removed). Transport per arm: 121-123 real loans, 665-666 real holds,
32-38 GETs of which 4 are book-detail reads; v011 had 0 GETs.

Cases 73 and 77 (`2.9.3-extreme`, a second active loan for the same reader "should be BLOCKED")
reach in every arm, control included. They encode the original one-loan-per-reader rule, which
the contract profile deliberately removes; they are the same two control exclusions v011 had.
No scenario expected to be reachable was STUCK on the healthy control.

### E1: guided catalog + common additions, original profile, original `sut.py`

Run `runs/guided-v013-20261116-185555-1692752`. 558 scenarios (542 + 16), no observer, case
boundary through `POST /reset`. **425 reached, 133 blocked as expected, 0 stuck, 0 reached
unexpectedly, 0 native failures**, 66 s. Under the original rules the catalog's expectations
hold exactly, and all 16 common additions (reads after every write, ISSTA-2/4/5 triggers, five
readers borrowing five books at once, five readers queued on one book) are reachable.

### E2/E3/E5: unguided sampling

`provengo sample`, max length 500, 5 readers / 5 books, full stories. Contract profile: 50
samples (`runs/sample-v013-20261116-185925-1782898`); original profile: 30 samples
(`runs/sample-v013-20261116-190152-1792871`).

| Measure | Contract, 50 | Original, 30 |
|---|---:|---:|
| Events per sample (mean / min / max) | 190 / 85 / 482 | 156 / 83 / 325 |
| Distinct action kinds (action × outcome), of 22 | 22 | 22 |
| Distinct abstract states, cumulative | 50 → 196 → 305 → 521 → 980 at 1/5/10/20/50 | 6 → 82 → 141 → 342 → 442 at 1/5/10/20/30 |
| Maxima: active loans / loans per reader / holds per reader / holds per book / borrowings per pair | 5 / 4 / 5 / 5 / 3 | 4 / 1 / 4 / 4 / 6 |
| Samples without any loan / without any hold | 7 / 7 | 7 / 8 |
| Samples with a reader or book deleted before any loan or hold | 40 | 23 |

Trigger reachability (samples hitting the predicate / first sample):

| Trigger | Contract, 50 | Original, 30 |
|---|---:|---:|
| ISSTA-1 fourth distinct active loan for one reader | 1 / #14 | never (rule) |
| ISSTA-2 third borrowing of the same pair | 32 / #1 | 12 / #3 |
| ISSTA-3 return while the reader has another active loan | 34 / #1 | never (rule) |
| ISSTA-4 detail read of an existing book | 50 / #1 | 29 / #1 |
| ISSTA-5 hold cancelled while the reader has another hold | 31 / #1 | 17 / #3 |
| 3.1, 3.2, 3.4, 3.6, 3.12 (hold/loan interplay, re-borrow, handover) | 33-41 each / #1 | 15-21 each / #2-5 |
| 3.7, 2.4.3, 2.7.3, 2.7.4, 2.9.4 (rejections that must happen) | 36-42 each / #1 | 16-23 each / #2-5 |
| Deleted-entity reads and re-deletes (404) | 50 / #1 | 30 / #1 |
| 3.17 loan for a deleted book (400) | never | never |

Reading: every logic trigger the model is allowed to reach is reached unguided within the first
few samples, with two exceptions. ISSTA-1 (a fourth concurrent loan for one reader) is rare (1
of 50): with a total-loan bound of 5 and eager deletion, four loans rarely pile up on one reader
before a return or a deletion. The guided run reaches it directly, so it is a *sampling weight*
issue, not a reachability gap; E8 (bound sensitivity) and a lower deletion weight are the
follow-ups. 3.17 is never attempted because the user-book row disappears with the book (see
the findings below). The abstract-state curve is still rising at 50 samples; the space is
eight-dimensional and the maxima show the bounds are being touched, so saturation needs the
larger E3 run rather than more dimensions. The degeneracy rates (14% of samples without any
loan, 80% with an early reader/book deletion) quantify the "eager deletion" remark in
`lib_stories.js` and are the motivation for E5's sampling weights.

## Reading the numbers

Reachability is a statement about the **model**: a scenario expected to be reachable that comes
out STUCK is a workload gap, one expected to be blocked that is REACHED is either a model bug or
a stale expectation (the catalog encodes the original one-loan-per-reader rule; under the
contract profile a second loan for the same reader is legal, so those catalog scenarios reach).
Native failures on a mutant arm are detection evidence only for cases that passed the healthy
control; observer candidates (first clean verdict per case) are reported separately, exactly as
in v009/v011. No final per-bug score is assigned by this campaign.

## Experiment plan: is the model degenerate?

The question is whether the single-event model, with at most `NUMBER_OF_USERS` readers and
`NUMBER_OF_BOOKS` books, can still produce every reasonable test that could expose a logic bug.
"Reasonable test" is made concrete by three catalogs: the 542 guided scenarios (bug-mapping
chapters 3-4 and sample-derived sequences), the 26 v013 additions, and the trigger predicates of
`sample_coverage_v013.py` (the five ISSTA triggers plus chapter-3 flows and the rejection rules).
Input-validation bugs (chapters 1-2 type bugs) are out of scope by decision.

| # | Experiment | Measures | Pass criterion | Status |
|---|---|---|---|---|
| E1 | Guided catalog reachability, both profiles | For each of 568 (contract) / 558 (original) scenarios: reached / blocked / stuck | 0 STUCK on expected-reachable; every REACHED-but-expected-blocked explained by the profile | Done, see results |
| E2 | Unguided trigger reachability | First sample hitting each trigger predicate; hit rate | Every trigger hit within N samples; hit rate reported per trigger | Done (10 and 50 samples) |
| E3 | Abstract-state saturation | Distinct `(users, books, loans, holds, loans/reader, holds/reader, holds/book, borrowings/pair)` states vs. sample count | Growth curve flattens; maxima reach the bounds (5/5/5/5/4+/.../3) | Done (curve in `coverage.md`) |
| E4 | Mutation detection, isolated arms | Native failures on control-eligible cases and observer candidates per bug | Each of bugs 1-5 has at least one control-eligible native failure or clean observer candidate in its arm | Done for the catalog; sampling replay (v009-style) is the follow-up |
| E5 | Degeneracy indicators | Samples without a loan / hold; readers or books deleted before any relation; events per sample | Rates reported; a high "eager deletion" rate motivates sampling weights, not model changes | Done |
| E6 | Extended logic-mutant sweep | Chapter 2/3 logic mutants (2.4.1-2.4.6, 2.7.1-2.7.5, 2.9.2-2.9.4, 2.10.1-2.10.3, 2.11.1-2.11.2, 2.12.2-2.12.3, 2.13.1-2.13.2) as `LIB_MUTANT=<id>` switches in a copy of `sut.py`; sampled runs per mutant | Kill rate per mutant with the model's own expected codes plus the observer | Proposed |
| E7 | Scenario-to-trigger ablation | Remove one story b-thread at a time, repeat E1/E2 | Shows which b-thread each trigger depends on; a trigger with a single point of failure is a fragility to document | Proposed |
| E8 | Bound sensitivity | E2/E3 with 3/3, 5/5, 8/8 readers and books | Trigger hit rates vs. bounds; the smallest bound that still hits every trigger | Proposed |

Findings that already came out of E1 (and were acted on):

- The detail read `GET /books/{id}` was reachable only after the list read, because one b-thread
  chained both (`verifyBookExistsAfterCreation`). Under strict guidance the ISSTA-4 trigger was
  STUCK. Fixed in `lib_stories.js` by giving the detail read its own b-thread. Chained
  verifications hide reachability; independent checks should be independent b-threads.
- The model never attempts a loan or hold for a **deleted** book or reader (the user-book row
  disappears with the entity), so the "ghost loan" rejection (3.17) is exercised only through
  the never-created ids of `verifyCannotCreate*WithNonexistent*`. Reachability of the *blocked*
  form is confirmed by the catalog (3.17 expectBlocked); the 400 check itself is a candidate
  story if that distinction matters.
