# v013: the single-event model under the guided catalog, the observer, unguided sampling, a logic-mutant sweep and b-thread ablation

v013 is the first campaign that runs the **repository's live model** (`library/provengo`, branch
`single-event-actions`) rather than a frozen copy of the old one. It replaces nothing: v012 → v011
→ v009 → v006 → v004 keep replaying their frozen inputs and remain the historical evidence.

## What changed in the model, and what that broke

Every action in `interfaces.library.js` now sends exactly one REST request. There is no
`requestOneOfDirect`, no `data.model = {name, valid}` block, no valid/invalid variant names, no
retry-until-valid loop, no malformed request (missing fields, wrong types, bad path ids), and no
`PUT` (405) probe. Negative checks are business-rule rejections only: deletes blocked by a loan
or hold, loans the rules forbid, nonexistent or deleted entities. Events are named after the
HTTP verb; the logical ids live in `data.parameters` on every event, rejection checks included;
list reads are described as `Verify: <Entity> <id> is listed in|absent from <list>` and check the response contents.

Consequences for the experiment code (survey of 2026-11-16, all file references on `master`):

| Dependency | Where | Effect of the new model | v013 answer |
|---|---|---|---|
| Action matching by `data.model.name` containing `valid` | `src/StrictGuidedRun.java` `chooserName`/`chooserNameMatches` | Every step STUCK at step 1 (name is `"POST"`) | `V013Match.actionName()` derives the old-style name from method + path + expected codes + parameters; anchored edits in a frozen copy (`patch_runtime_v013.py`) |
| Rejection = expected code 400 only, never a target | `expectsRejection` | 404 checks not recognised; no rejection can be a scenario step | A 4xx-expecting event is named `reject<Action><code>`, and a step whose action starts with `reject` may target it |
| Old argument orders | `campaign-v004/business_stories_v004.js` | `createHold`, `deleteHold`, `verifyLoanExists` mis-bound | `business_stories_v013.js` |
| `requestOneOfDirect` filter, `randomInt()` replacements | `campaign_v004.py prepare()` | `RuntimeError` / silent no-op | `prepare_model_v013.py` |
| `requestOneOfDirect` adapter test | `test_profiles_v004.js` | Fails | `test_v013.py` |
| Frozen v011 catalog hash, 542-count gates, preflight anchor | v010-v012 | Untouched; they still run their frozen model | Not changed |
| Observer ledger, `counts()`, semantic checker, natchan catalogs | HTTP level | Unaffected | Reused as is |

## Files

| File | Role |
|---|---|
| `prepare_model_v013.py` | Snapshot of `library/provengo` with a rules **profile** (`original`: one active loan per reader, as `sut.py`; `contract`: the experiment contract of `sut_buggy_issta.py` with the v004 workload bounds 5 loans / 5 holds / 3 per pair) and a **stories** choice (`full`: the repository stories; `business`: successes and reads only) |
| `patch_runtime_v013.py` | Frozen `StrictGuidedRun` copy: the four v011 execution edits plus two matching edits; the scenario catalog section is checked byte-for-byte |
| `V013Match.java` | Transport-shape action naming for single-event REST events, rejection checks included |
| `V013Scenarios.java` | 61 added scenarios: `COMMON` (19, legal under both profiles: reads, ISSTA-2/4/5 triggers, bounded extremes, handover reads), `CONTRACT` (10, multi-loan readers, ISSTA-1/3), `NEGATIVE` (23 rejection sequences from bug-mapping chapters 2-3), `NEGATIVE_CONTRACT` (2), `NEGATIVE_ORIGINAL` (2), `GAPS` (5 loans and holds for deleted entities, formerly the known gaps) |
| `V013GuidedSuiteHarness.java` | Runs catalog and/or additions, one fresh runtime per scenario, case boundary through the observer or the SUT's `/reset` |
| `guided_suite_v013.py` | Orchestrator (Linux and Windows): prepare, patch, compile, transport self-checks, arms, `results.json`, review ZIP |
| `sample_coverage_v013.py` | Unguided `provengo sample` coverage: action kinds, abstract states, trigger reachability, degeneracy indicators |
| `sut_mutants_e6.py`, `mutant_sweep_e6.py` | E6: 30 logic mutants of the experiment fixture (one per process, `ISSTA_BUGS=<id>`), each run guided and sampled behind the observer |
| `ablation_e7.py` | E7: one story b-thread disabled at a time, full guided catalog, outcome diff against the baseline |
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

# E6 logic-mutant sweep (guided and sampled), E7 b-thread ablation
.venv/bin/python library/ess-experiment/campaign-v013/mutant_sweep_e6.py --repo . --jar ~/provengo/Provengo-2026-01-10.uber.jar
.venv/bin/python library/ess-experiment/campaign-v013/ablation_e7.py --repo . --jar ~/provengo/Provengo-2026-01-10.uber.jar
```

On Windows replace `.venv/bin/python` with `.venv\Scripts\python.exe`; nothing else differs.
Requirements: the repository `.venv` with Flask, a JDK, a local Provengo JAR (the `provengo`
CLI on PATH for `sample_coverage_v013.py`). Ports 23243/23244 (observer) or 23242 (original
SUT) must be free.

## Results on this machine (2026-11-16/17, Provengo-2026-01-10.uber.jar, Java 25)

All numbers below are from the final model (rejection checks carry ids, every check is an
independent b-thread, rejections are re-issued after relation changes, every read checks the
response contents, loans and holds for deleted entities are attempted, all ids are derived).
Earlier runs of the day are named where they are the only evidence for a finding.

### E1: guided reachability, contract profile, fixture behind the observer

Run `runs/guided-v013-20261117-095647-1810950`. 601 scenarios per arm (542 catalog + 18 common
+ 10 contract + 23 negative + 2 negative-contract + 5 formerly-gap), full stories, 5 readers /
5 books. Both transport self-checks passed. Each arm 70-80 s.

| Arm | Reached as expected | Blocked as expected | Stuck | Reached but expected blocked | Control-eligible native failures | Clean observer candidates |
|---|---:|---:|---:|---:|---|---|
| control (`none`) | 468 | 131 | 0 | 2 (cases 73, 77) | none | 0 |
| bug 1 | 466 | 131 | 2 | 2 | 564, 565 (ISSTA-1 fourth loan → 409) | 2 × bug-1 (the same two) |
| bug 2 | 467 | 131 | 1 | 2 | 546 (third borrowing → 409) | 1 × bug-2 (546) |
| bug 3 | 463 | 131 | 5 | 2 | 566, 567, 568, 570, 595 (a return removed the other loan: the loans-list content check and the second return) | 6 × bug-3 (incl. all five) |
| bug 4 | 464 | 131 | 4 | 2 | 543, 544, 545, 553 (detail read → 404) | 4 × bug-4 (the same four) |
| bug 5 | 463 | 131 | 5 | 2 | 80, 257, 260, 266, 433 (a hold already removed) | 25 × bug-5 (incl. those five) |

Every mutant arm has at least one control-eligible native failure whose case also carries a
clean observer candidate labelled with that bug. With content checks on list reads, bug 3 is
now caught natively in five scenarios (before: one). Cases 73 and 77 (`2.9.3-extreme`, a second
active loan for the same reader "should be BLOCKED") reach in every arm, control included: they
encode the original one-loan-per-reader rule, which the contract profile deliberately removes;
they are the same two control exclusions v011 had. Every rejection sequence reaches on the
healthy control, including the five "loan or hold for a deleted reader/book" scenarios that
were STUCK before the deleted-entity checks were added. Per arm the tool sent 39-45 GETs (v011:
0) and 38-43 expected 4xx rejections (v011: 0).

### E1: guided reachability, original profile, original `sut.py`

Run `runs/e7-ablation-20261117-094647-1630463` baseline (the same selection as `--profile
original --sut original`): 591 scenarios (542 + 19 common + 23 negative + 2 negative-original
+ 5 formerly-gap), no observer, case boundary through `POST /reset`. **458 reached, 133
blocked as expected, 0 stuck, 0 reached unexpectedly**, 0 native failures, 144 s. Under the
original rules the catalog's expectations hold exactly, and every addition, rejection
sequences and deleted-entity attempts included, is reachable.

### E2/E3/E5: unguided sampling

`provengo sample`, max length 500, 5 readers / 5 books, full stories, contract profile, 50
samples (`runs/sample-v013-20261117-094647-1630467`). The earlier 30-sample original-profile
run (`runs/sample-v013-20261116-190152-1792871`, model of commit `ee36747`) is kept for the
comparison column.

| Measure | Contract, 50 (final model) | Original, 30 (ee36747) |
|---|---:|---:|
| Events per sample (mean / min / max) | 199 / 98 / 471 | 156 / 83 / 325 |
| Distinct action kinds (action × outcome), of 22 | 22 | 22 |
| Distinct abstract states, cumulative | 17 → 62 → 176 → 370 → 687 at 1/5/10/20/50 | 6 → 82 → 141 → 342 → 442 at 1/5/10/20/30 |
| Maxima: active loans / loans per reader / holds per reader / holds per book / borrowings per pair | 5 / 3 / 3 / 3 / 3 | 4 / 1 / 4 / 4 / 6 |
| Samples without any loan / without any hold | 8 / 7 | 7 / 8 |
| Samples with a reader or book deleted before any loan or hold | 41 | 23 |

Trigger reachability (samples hitting the predicate / first sample), contract profile, 50:
ISSTA-2 22/#3, ISSTA-3 26/#3, ISSTA-4 49/#1, ISSTA-5 22/#3 (per book 26/#3); the chapter-3
flows 24-33 each; the rejection rules 29-40 each; deleted-entity reads and re-deletes 50/#1;
**3.17 (loan for a deleted book) 50/#1**, which was never hit before the deleted-entity checks.
The one trigger never hit unguided is ISSTA-1 (a fourth concurrent loan for one reader): with
a total-loan bound of 5 and the sampler's eager deletions, four loans rarely pile up on one
reader. The guided catalog reaches it directly, so it is a sampling-weight matter (E8), not a
reachability gap.

A lesson from this measurement: a late-bound `@{...}` reference inside a request body must stay
inside a JSON string. A version of the model that wrote the references unquoted (to make the
service receive JSON numbers) made the sampler end every scenario silently at its first loan,
because the body was not valid JSON before substitution; live runs were unaffected. Sampling
coverage is therefore a required check after any change to the interface layer.

### E6: logic-mutant sweep

Run `runs/e6-mutants-20261116-195058-2246783` (30 mutants, model of commit `615badc`, 69 min)
plus `runs/e6-mutants-20261117-*` (L7, L4, L8 re-run on the final model). 30 logic mutations of
the experiment fixture (bug-mapping chapters 2-3: status codes, missing checks, wrong filters,
collateral deletions, silent state changes), each run as its own arm behind the observer, with
the healthy fixture as control. Two workloads: guided (every scenario set) and sampled (6
unguided samples of 15-85 events, max length 200, replayed identically on every arm). Two kill
channels, counted on control-eligible cases only: native (the model's own expected-code or
content check fails) and observer (first clean semantic verdict in the case).

| | Guided | Sampled |
|---|---:|---:|
| Mutants killed natively | 30 of 30 | 14 of 30 |
| Mutants with an observer verdict | 15 | 7 |
| Mutants killed by either channel | 30 | 14 |

**All 30 mutants are killed**, all of them by the guided workload. Before the content checks,
L7 (`GET /loans` applies the `bookId` filter to all loans instead of the `userId`-filtered ones)
survived, as predicted: status codes do not reveal it, and the observer reads unfiltered lists.
It is now killed natively by the handover scenarios (a reader returns a book, another reader
borrows it, the first pair's filtered read must be empty). The sampled workload misses the
mutants that need a relation to exist at the right moment: the six short samples deleted most
entities early, the same eager-deletion effect as E5. Per-mutant counts and the observer rule
that fired are in `runs/e6-mutants-*/E6_RESULTS.md`.

### E7: b-thread ablation

Run `runs/e7-ablation-20261117-094647-1630463` (original profile against `sut.py`, 591
scenarios, 45 b-threads, ~2.5 h under load). Each b-thread was disabled in turn and the full
catalog re-run; every scenario's outcome was compared with the baseline. **45 of 45 ablations
CONFIRMED**: every scenario whose outcome changed stopped exactly at an action the disabled
b-thread produces, no expected-blocked scenario became reachable, and no remaining request
failed. Every b-thread has at least one dependent scenario, so none is redundant for the catalog
and none is untested. The largest dependents: `createUsers`/`createBooks` (~440 scenarios stuck,
133 blocked prefixes shortened), `createHold` (308), `deleteUser` (176), `deleteBook` (159),
`deleteHold` (81), `createLoan` (60); every rejection, read and deleted-entity check has 1-6
dependent scenarios. The first run of E7 (`runs/e7-ablation-20261116-195058-*`) had 35
CONFIRMED and 6 b-threads with no dependent scenario, which is how the four missing catalog
scenarios were found. This run started before the last two model edits of the day (hold ids
include the pair's occurrence count; deleted-entity checks skip when no counterpart is left);
neither changes which b-thread produces which action.

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
chapters 3-4 and sample-derived sequences), the 61 v013 additions (including 32 rejection
sequences), and the trigger predicates of `sample_coverage_v013.py` (the five ISSTA triggers
plus chapter-3 flows and the rejection rules). Input-validation bugs (chapters 1-2 type bugs)
are out of scope by decision.

| # | Experiment | Measures | Pass criterion | Status |
|---|---|---|---|---|
| E1 | Guided catalog reachability, both profiles, rejection steps included | For each scenario: reached / blocked / stuck | 0 STUCK on expected-reachable; every REACHED-but-expected-blocked explained by the profile | Done: 0 stuck on both profiles |
| E2 | Unguided trigger reachability | First sample hitting each trigger predicate; hit rate | Every trigger hit within N samples; hit rate reported per trigger | Done (10 and 50 samples) |
| E3 | Abstract-state saturation | Distinct abstract states vs. sample count | Growth curve flattens; maxima reach the bounds | Done (curve in `coverage.md`; not yet flat at 50) |
| E4 | Mutation detection, isolated ISSTA arms | Native failures on control-eligible cases and observer candidates per bug | Each of bugs 1-5 has a control-eligible native failure or clean observer candidate | Done: all five, both channels |
| E5 | Degeneracy indicators | Samples without a loan / hold; early deletions; events per sample | Rates reported | Done |
| E6 | Extended logic-mutant sweep | Kill rate per mutant, guided and sampled, native and observer | Every mutant killed unless its survival is explained | Done: 30 of 30 (the last one after content checks were added to list reads) |
| E7 | b-thread ablation | Outcome diff per disabled b-thread | Every change explained by the b-thread's own actions; every b-thread has a dependent scenario | Done, see above |
| E8 | Bound sensitivity | E2/E3 with 3/3, 5/5, 8/8 readers and books, lower deletion weight | Trigger hit rates vs. bounds; the smallest bound that still hits every trigger | Proposed |

Findings that came out of E1/E7 and were acted on in the model:

- The detail read `GET /books/{id}` was reachable only after the list read, because one b-thread
  chained both. Fixed: independent checks are independent b-threads (also applied to every
  after-deletion check).
- "One rejection check per blocking relation" was not enough: BPjs satisfies two live copies
  that request an equal event with a single selection, so after the hold-based and loan-based
  checks of one book were satisfied together, cancelling the hold left no check for the loan.
  Fixed: rejection checks are re-issued after every change to the relations they depend on;
  COBP ends the live copy in the very sync that removes its relation, so no check is issued for
  a relation that is gone (verified in Provengo's `context.js` and by live runs).
- Rejection events carried no logical id, so a rejection could not be bound as a scenario step.
  Fixed: every event carries its ids in `parameters`.
- Six b-threads had no dependent scenario in the catalog (list reads of loans/holds right after
  a reader or book deletion; the "reader and book both nonexistent" checks): four scenarios were
  added so that every b-thread is covered.
- The model never attempted a loan or hold for a **deleted** entity (the user-book row disappears
  with it). Closed: after every deletion the model pairs the deleted entity with whichever
  counterpart exists and expects 400 (`verifyDeletedUserCannot{Loan,Hold}`,
  `verifyDeletedBookCannotBe{Loaned,Held}`); the five `GAPS` scenarios now reach and the 3.17
  trigger is hit in every unguided sample.
- List reads checked only the status code, so a wrong filter (E6 mutant L7) and silent state
  damage could only be seen by the observer. Closed: every read carries a REST callback that
  compares the response with the service ids recorded at creation (`pvg.rtv.get` is available
  in the callback scope); filtered reads must come back empty after a return or deletion. L7 is
  now killed natively.
- Loan and hold numbers came from counters shared by several b-threads, so the same event
  selection produced different traces depending on BPjs's thread scheduling. Closed: no
  counters; every id is derived from the entities involved (`holdIdFor(user, book)`, no loan
  number, `missingId(n)`).
- Two pitfalls found on the way and kept as minimal reproductions in `library/bp-pitfalls/`
  (with `on()`, equal-request merging and chained checks): a late-bound reference written
  outside a JSON string makes the sampler end scenarios silently, and a same-named function in
  a later spec file replaces an earlier one without warning (the DAL's `holdId` was replaced by
  a story helper and every hold got entity id `NaN`, which made a reader with a hold look
  deletable in one live run out of three).
