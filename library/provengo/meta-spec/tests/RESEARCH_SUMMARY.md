# State+Parameter Coverage Ranking — Research Summary

**Status as of 2026-10-19.** Written up in full because the planned meeting with the advisor
(Gera) did not happen —
this is the complete, self-contained account of the work so it can be picked up, presented, or
reviewed at any later point without needing to reconstruct it from chat history. Every claim below
was verified against the actual code or actual experiment output during this investigation, not
asserted from memory. Where something is still open or unverified, it is labeled as such rather
than rounded up to a conclusion.

---

## 1. Goal

Build a `rankingFunction` for `provengo ensemble` that selects a small, high-value test suite
("ensemble") from a larger pool of sampled traces, using **State Coverage + Parameter Coverage**
as the selection criterion — as a second, independently-callable option alongside the project's
pre-existing **GOALS**-based ranking, for an A/B comparison. Explicitly **not** a request to merge
GOALS into the new ranking, and explicitly not a request to prove anything about how many
users/books the model "really" has — the deliverable is a ranking function, evaluated on whether
it selects good ensembles.

Design constraints set along the way:
- **State coverage**: reward an ensemble for covering more distinct domain states, not for how
  many times it re-hits the same one.
- **Parameter coverage**: reward distinct parameter values *and* distinct parameter
  *combinations* (so e.g. a new (user, book) pair counts as new coverage even if neither id alone
  is new).
- **No double-counting**: use `Set`s throughout, so repeating a trace or a state never inflates
  the score.
- **Don't touch the shared model** (`lib_stories.js`/`interfaces.library.js`/`dal.js`) unless
  truly necessary — these are reviewed by Gera and Yehoshua.
- **Keep the existing GOALS mechanism intact** — add the new one alongside it, don't replace or
  blend it, so the two can be compared.

---

## 2. Design

### 2.1 Six state features

| Feature | Mirrors DAL query |
|---|---|
| `BOOK_DELETE_ELIGIBLE` | `Book.CanDelete` |
| `USER_DELETE_ELIGIBLE` | `User.CanDelete` |
| `LOAN_CREATABLE` | `UserBook.CanCreateLoan` |
| `HOLD_CREATABLE` | `UserBook.CanCreateHold` (unconditionally true once any user+book coexist) |
| `HOLD_WITHOUT_LOAN` | `Hold.WithoutLoan` (previously dead code — first real use) |
| `MULTI_USER_BOOK_RELATIONS` | no existing single-entity query — at least two active loan/hold relations with a different user *and* a different book; the one feature with no DAL equivalent, proposed by Gera as an example of a state worth tracking beyond basic CRUD gates |

### 2.2 Parameter coverage

Tracked as a tagged union of four kinds of value, each counted once regardless of repetition:
`user:<id>`, `book:<id>`, `op:loan`/`op:hold`, `pair:<userId>/<bookId>`. Only counted from
**genuinely successful** `createLoan`/`createHold` completions (see §4.1/§4.2 for why that
distinction matters).

### 2.3 Score

```
score = 100 * ( ALPHA * (state features hit / 6) + (1-ALPHA) * (parameter tags hit / universe) )
```

`ALPHA = 0.5` (equal weight, not tuned further). `universe` is a **safety ceiling**, not a claimed
true parameter-value count — see §4.3 for why it isn't simply "4 users × 4 books."

---

## 3. Where it lives

| File | What's there |
|---|---|
| `library/provengo/spec/js/lib_stories.js` (lines ~324-383) | `markStateFeature()` + 6 `ctx.bthread`s that emit a `"StateFeature"` event when each feature becomes true, reusing existing DAL queries. **Left in place but unused by scoring** (see §4.4) — removing them was deliberately deferred to keep "fix the measurement" and "change the model" as separate variables. |
| `library/provengo/meta-spec/ensemble-code.js` | All scoring logic: `STATE_FEATURES`, `USER_ID_CEILING`/`BOOK_ID_CEILING`, `PARAMETER_UNIVERSE_SIZE`, `ALPHA`, `reconstructStateFeaturesForTrace`, `distinctStateFeaturesHit`, `genuineEntityEventIds`, `loanOrHoldCreateParameters`, `distinctParametersHit`, `stateParamScore`, `goalsRankingFunction` (the renamed pre-existing mechanism, **logic unchanged**), `stateParamRankingFunction`, `RANKING_MODE` (string, currently `"goals"` — replaced the old `USE_STATE_PARAM_RANKING` boolean), `rankingFunction` (the dispatcher `provengo ensemble` actually calls). |
| `library/provengo/meta-spec/tests/` | Everything written to validate the above: `ensemble-code.test.js` (hand-computed unit tests), `verify_state_features.py` + `compare_state_reconstruction.js` (independent Python/JS cross-validation), `compare_ensembles.py` (independent measurement script used for every pilot below), `comparison_results.md` (raw pilot data/tables), this file. |

**Not touched:** `library/sut/meta-spec/ensemble-code.js` — confirmed via diff early on that it's an
untouched template copy, not the one `provengo ensemble` actually uses for this project (that's
`library/provengo/meta-spec/ensemble-code.js`, confirmed by the project's own `provengo.yml`/
`README.md` and by actually running the CLI from `library/provengo`).

**Current git state:** nothing committed. `git status` shows `ensemble-code.js` and
`lib_stories.js` modified, plus the new `meta-spec/tests/` directory, untracked. Per explicit
instruction during this work: leave everything uncommitted until it's reviewed.

---

## 4. Bugs found and fixed during implementation

Each of these was caught by actually running the code against the live SUT / real samples, not
by code review alone — several would have silently produced wrong numbers otherwise.

### 4.1 `d.model` divergence between `createLoan` and `createHold`

`createLoan` completes via `requestOneOf` (no `event.data.model` field); `createHold` completes
via `requestOneOfDirect`, which *always* sets `event.data.model={name, valid}` (see
`requestOneOfDirect`'s `buildRestEvent` call in `interfaces.library.js`). An early version of
`loanOrHoldCreateParameters` copied `loanCompletion()`'s `!d.model` exclusion check — harmless for
loans (always false there anyway) but it silently dropped **every** hold completion. Fixed by
removing that check entirely from `loanOrHoldCreateParameters` (it was never load-bearing for its
actual purpose).

### 4.2 Nonexistent-foreign-key negative tests polluting parameter coverage

`tryToCreateLoanWithNonexistentUserAndExpectError` and siblings send a real-shaped
`{description, userId, bookId}` parameters object, just with a deliberately-missing id
(`generateMissingId()` = existingId + 1,000,000,000) and a `"Verify: ..."` description instead of
`"Create: ..."`. An early version of the parameter-coverage check only looked for
`userId`/`bookId` presence, so these negative tests polluted the coverage `Set` with garbage ids
like `1000000003`, pushing the score to **136.5 out of 100** in testing. Fixed by additionally
requiring `parameters.description` to match `/^Create: /` — the prefix `createDescription()`
(`lib/utils.js`) only produces for a genuinely successful create.

### 4.3 Real user/book ids exceed `NUMBER_OF_USERS`/`NUMBER_OF_BOOKS` (= 4 each)

Even after fix 4.2, real (non-garbage) ids up to **6** appeared. Root cause, found via a targeted
debug session: `tryToDeleteNonexistingUser`/`Book`/`Loan` (`lib_stories.js`, unguarded `bthread`s
that run from the very first tick) call `generateMissingId(generateUserId())` /
`generateMissingId(generateBookId())` — i.e. they call the **same counter-incrementing
generators** `createRandomUsers`/`createRandomBooks` draw real ids from, purely to seed a
"definitely missing" id, silently burning one real id slot per call. Exactly 2 of these 3
bthreads touch each counter once (`tryToDeleteNonexistingUser` + `tryToDeleteNonexistingLoan` burn
a user id each; `tryToDeleteNonexistingBook` + `tryToDeleteNonexistingLoan` burn a book id each) —
matching the observed ceiling of 4+2=6 exactly.

**Decision (explicit, from the advisor):** do **not** fix this in the shared model just to make a
denominator assumption true. Instead, `USER_ID_CEILING`/`BOOK_ID_CEILING` = `NUMBER_OF_USERS/BOOKS
+ 2` (derived from this analysis, not guessed), used only as a safety ceiling. Key realization
that made this acceptable: `rankingFunction` only ever scores one candidate ensemble at a time
(never sees the full sample pool), and every candidate in one `provengo ensemble` run is scored
against the *same* constant — so the exact ceiling value only bounds the reported 0–100 range, it
does not change which candidate the genetic search prefers, **as long as no candidate's true
value exceeds the chosen ceiling**. (An earlier claim that the ceiling "only affects the displayed
number, never the ranking" was mathematically wrong in general — true only because `ALPHA` splits
the score into two *separately normalized* terms, so rescaling only one denominator changes
relative weighting, not just magnitude; see the ALPHA-sweep point in §7.)

### 4.4 `StateFeature` markers miss 45–78% of genuinely-true occurrences — the big one

Built `verify_state_features.py`: independently replays the real Create/Delete event stream
(mirroring `dal.js`'s own query definitions) and compares "was this condition independently true
at some point" against "did its marker actually fire," per feature, across real sampled traces:

| feature | independently true | marker fired | miss rate |
|---|---|---|---|
| `BOOK_DELETE_ELIGIBLE` | 20/20 | 11/20 | 45% |
| `USER_DELETE_ELIGIBLE` | 20/20 | 7/20 | 65% |
| `LOAN_CREATABLE` | 20/20 | 9/20 | 55% |
| `HOLD_CREATABLE` | 20/20 | 11/20 | 45% |
| `HOLD_WITHOUT_LOAN` | 18/20 | 4/20 | 78% |
| `MULTI_USER_BOOK_RELATIONS` | 4/20 | 1/20 | 75% |

Four of six conditions are reached in **every single trace** (20/20) — the model reaches these
states almost immediately with only 4 users/4 books — yet the marker mechanism missed 45–78% of
those true occurrences. Root cause: `markStateFeature()`'s `bp.sync({request: ...})` is an
**offer**, not a guarantee — it competes for selection against every other event any other bthread
offers at that synchronization step. `Loan.All`/`Hold.All` (the triggers for 2 of the 6 markers)
fire on every single loan/hold creation, a very high-competition moment in this heavily-fuzzed
model, so the marker offer frequently loses the race and is silently never selected.

**This completely overturned the interpretation of the first two "pilot" comparisons** (which
reported 6/6 and 5/6 "state coverage" for both ranking methods) — those numbers reflected marker
unreliability, not the model's true reachability (which is closer to 100% for 4 of 6 features).
Both are flagged as unreliable in `comparison_results.md`, kept for history, not deleted.

**Fix, following the advisor's explicit 5-stage migration plan:**
1. **Ported the reconstruction**: `distinctStateFeaturesHit` now calls
   `reconstructStateFeaturesForTrace(test)` per trace, replaying genuine Create:/Delete: REST
   completions (via `genuineEntityEventIds()`, extending the same "Create: "-prefix trick to
   "Delete: " and to bare `id` fields for users/books) and mirroring each DAL query's actual
   formula. No longer reads `StateFeature` events at all.
2. **Validated exactly against an independent implementation, not just similar rates**: built
   `compare_state_reconstruction.js`, which loads the real `ensemble-code.js` via Node's `vm`
   module and diffs its per-trace output against `verify_state_features.py`'s Python
   reconstruction. Result on a 10-trace pool: **10/10 exact set match, 0 mismatches.** (Node's
   `fs.readFileSync` has a ~536MB string-length ceiling — this comparison must stay at 10 traces/
   `--max-length=80` or smaller; a 20-trace pool at that depth is ~660MB and fails to load.)
3. **Edge cases**: covered in `ensemble-code.test.js` (entity create/delete sequences, a mid-trace
   delete that doesn't erase already-recorded `Set` coverage, a rejected nonexistent-FK attempt
   that must not be mistaken for a real state change).
4. **Confirmed `distinctParametersHit`/GOALS untouched** — only `distinctStateFeaturesHit`'s
   internals changed.
5. Reran the pilot comparisons (§5) only after 1-4 were solid.

**Deeper ground-truth check** (the exact-match test above only proves the two *implementations*
agree with each other, not that either reflects the real SUT/DAL state — flagged explicitly as a
remaining gap, then closed): checked that `dal.js`'s own entity-update effects
(`ctx.registerEffect`) are gated by the *same* classification my reconstruction uses — the
`AnyBookAdded`/`AnyBookDeleted`/etc. `EventSet`s in `interfaces.library.js` key off
`hasExpectedCode(e, 201/200)`, and `hasExpectedCode()` (`lib/utils.js`) checks the event's
*declared* `expectedResponseCodes` field (i.e. "was this a request expected to succeed," set only
on the valid-shaped variant — the same place the `"Create: "/"Delete: "` description prefix comes
from), **not the actual HTTP status code returned by the SUT**. So the reconstruction and the
production DAL are keyed off the same underlying classification, not two independently-invented
heuristics that happen to agree. (Residual, pre-existing, out-of-scope limitation: since neither
checks the SUT's *actual* returned code, a genuine race where a "valid" request unexpectedly fails
— already documented elsewhere in this codebase — could make both the DAL's own model state and
this reconstruction diverge from the real SUT, in the same direction. Not introduced by this work.)

### 4.5 `compare_ensembles.py` itself still used the broken marker-based state counting

Easy to miss: after fixing `ensemble-code.js` (4.4), the *independent measurement script* used to
compare pilot results was still reading `StateFeature` marker events for its own state-coverage
tally. Caught before any pilot used the corrected measurement; fixed by importing
`verify_state_features.py`'s `replay_trace()` instead.

### 4.6 An earlier runtime claim was wrong, corrected explicitly (not quietly)

Pilots 3/4 reported state+param ranking as consistently slower (6/6 paired repeats). A follow-up
message in this investigation mischaracterized one repeat's data as "reversing" that direction —
re-checking the actual numbers showed it did **not** reverse, only the *margin* shrank. Then a
properly controlled benchmark (§5.5) showed the "consistently slower" framing itself doesn't hold
up once order effects are accounted for. Both corrections are recorded explicitly in
`comparison_results.md` rather than silently edited away.

### 4.7 Test file placement broke the real Provengo CLI

`provengo` auto-loads **every** `.js` file directly under `meta-spec/` as project code (not
documented anywhere found — discovered empirically). Placing `ensemble-code.test.js` there broke
`provengo ensemble` outright (a Rhino "redeclaration of const" error, from the test's own
block-scoped `const`s colliding in the shared global scope). Fixed by moving all standalone
Node/Python scripts into `meta-spec/tests/` (a subdirectory) — confirmed the auto-load is not
recursive.

---

## 5. Empirical results

All pilots measured with `compare_ensembles.py`, which reimplements every check independently of
`goalsRankingFunction`/`stateParamScore` (not circular) and, after §4.5, uses the corrected
state-feature reconstruction. Raw ensemble JSON files are not checked in (~160MB each — GitHub's
hard limit is 100MB); they're regenerable via the commands in `comparison_results.md` into
`products/coverage-experiments/` (already `.gitignore`d).

### 5.1 Pilot 1 & 2 (UNRELIABLE — old marker-based state measurement, kept for history only)

Pilot 1 (`--size=10`): both methods 6/6 state, 8/8 GOALS, param tags 16 vs 22. Pilot 2
(`--size=20`): both 5/6 state, GOALS 8/8 vs **7/8** (missing "deleteUser (valid)"), param tags 17
vs **26**. Both are now known to reflect marker unreliability, not true state reachability — see
§4.4. The GOALS/param numbers themselves aren't affected by that bug, only the "state features"
rows.

### 5.2 Pilot 3 (`--size=10`, corrected measurement, 3 repeats)

State features and GOALS **identical between methods in all 3 repeats**. Parameter tags higher
for state+param in all 3 (+1, +2, +7).

### 5.3 Pilot 4 (`--size=20`, corrected measurement, 3 repeats)

State features identical (6/6) in all 3. Parameter tags higher for state+param in all 3 (+10,
+13, +2 — larger magnitude than pilot 3). GOALS: identical in 2/3, but **1 repeat showed state+
param losing exactly one target** ("deleteBook (valid)") — a real, if occasional, trade-off,
confirming it wasn't purely a pilot-2 measurement artifact, just not guaranteed every run.

### 5.4 Extended parameter-coverage sample, n=8 (`--size=10`)

5 more independent repeats (all showing 6/6 state, 8/8 GOALS, no regressions), combined with
pilot 3 for n=8 total. **All 8 paired differences positive**: +1,+2,+7,+4,+8,+7,+1,+7. Mean diff
= **+4.62**, stdev = 2.97, approximate paired t ≈ 4.40 (df=7) — exceeds the two-tailed p=0.01
critical value (~3.50). This is now a reasonably solid finding at this specific scale
(`--size=10`/ensemble-size=5), not just a directional trend — though n=8 is still modest and
normality of the differences wasn't separately checked.

### 5.5 Controlled runtime benchmark — overturns the "consistently slower" claim

One **fixed** sample pool reused for every run (removes pool-content variance as a confound), 1
discarded warm-up run per method, 5 timed runs per method:

| method | 5 timed runs (s) | mean | stdev |
|---|---|---|---|
| GOALS | 54.1, 44.6, 99.4, 113.3, 127.7 | 87.79 | 36.68 |
| state+param | 97.9, 42.8, 89.6, 112.2, 107.5 | 90.00 | 27.78 |

Difference of means (2.2s) is negligible next to the within-method stdevs (~30-37s). **Both
methods independently show the same strong increasing trend across their own 5 sequential runs**
— the same ranking function run 5 times on identical input, so the trend cannot be caused by which
function runs; it points to a session-level effect (JVM/GC, or rising background load) making
later invocations slower regardless of method. Since every prior repeat ran GOALS then
state+param in that fixed order, state+param always executed later — exactly the position this
benchmark shows is slower independent of method. **The "runtime cost" in pilots 3/4 was very
likely an order artifact, not a real property of the ranking function.** Caveat: this benchmark is
still a block design (all GOALS, then all state+param), not interleaved, so it demonstrates the
drift effect is large enough to plausibly explain the earlier finding entirely, but doesn't fully
isolate the two effects. A proper follow-up would interleave runs or use a fresh process per run.

### 5.6 Why state+param occasionally misses a GOALS target — root cause, not just observation

Directly inspected the two actual ensemble files from pilot 4's regression repeat. GOALS-selected
ensemble: 4/5 traces contain a genuine `"deleteBook (valid): N"` completion. State+param-selected
ensemble: **0/5** traces contain any valid deleteBook completion — every deleteBook attempt across
all 5 is an invalid variant. **Not a bug** — the direct consequence of what each function
optimizes for: `goalsRankingFunction` explicitly rewards that completion as 1 of its 8 goals, so
it reliably selects for it. `stateParamRankingFunction` has no preference at all about whether a
specific CRUD action *completes successfully* (it only tracks `BOOK_DELETE_ELIGIBLE` — a book
*becoming* eligible, not that deletion was actually completed — and loan/hold parameter
diversity), so when the most parameter-diverse 5-trace subset happens to consist of traces where
the delete-retry loop never resolved to "valid" within the depth budget, nothing stops it from
being selected. This is a real, mechanistically-understood limitation of `stateParamRankingFunction`
as it stands — it has no visibility into GOALS at all, so nothing anchors it to preserve a
specific action's successful completion if a more parameter-diverse candidate set happens to lack
one. Not yet addressed; see §7.

### 5.7 GOALS array itself — verified correct, no changes needed

A reviewer flagged the 8 `GOALS` entries as unverifiable without seeing the implementation. Traced
each one against the actual code: `loanCompletion(/^createLoan \(invalid/)` looked suspect at
first glance (does the match target the event name or the description?) but `requestOneOf`'s own
fallback chain (`chosen.parameters || {description: chosen.description || selectedEvent.name}`)
makes an invalid loan completion's `parameters.description` end up equal to the chooser's
descriptive name anyway — so the match against `parameters.description` (which is what
`loanCompletion()` checks) works correctly, just non-obviously. The other 6 (`createHold`/
`deleteUser`/`deleteBook` × valid/invalid) go through `requestOneOfDirect`, which always sets
`model.name` to the exact variant name — `nameMatches()` checks that correctly too. All 6 were also
directly observed present/absent in real pilot data during this investigation (e.g. §5.6's
`"deleteBook (valid): 3"` sighting). The separate `makeGoals`/`Ctrl.markEvent("Classic!")`
function in the same file is dead code — defined once, never called anywhere — left over from the
original Provengo project template, irrelevant to anything above.

---

## 6. Honest framing for presenting this work

- **Parameter-coverage gain**: the strongest finding. Consistent in *direction* across all 11
  independent paired repeats (8 at size=10, 3 at size=20), statistically significant at size=10
  (n=8, t≈4.40, p<0.01). Magnitude varies a lot run-to-run (stdev is 60-96% of the mean) — report
  as "consistently positive, magnitude uncertain," not a precise expected percentage.
- **State-feature coverage**: genuinely identical between `goalsRankingFunction` and
  `stateParamRankingFunction` in every paired repeat (11/11) — the cleanest claim available. No
  observed cost.
- **GOALS coverage**: a real but infrequent cost of `stateParamRankingFunction` — occurred in 1 of
  11 paired repeats (pilot 4's repeat 2; mechanism understood, §5.6: it has no visibility into
  GOALS at all, so nothing anchors it to preserve a specific action's successful completion). 1 of
  11 is not enough occurrences to estimate a reliable harm *rate* — call it "a real but infrequent
  trade-off, rate unknown," not a quantified risk.
- **Runtime cost**: explicitly **not established**. The apparent consistent slowdown did not
  survive a controlled benchmark; order effects likely explain the original finding. Open
  question, not a known cost.
- **Overall**: eleven independent paired repeats are encouraging preliminary evidence that
  `stateParamRankingFunction` trades a small, infrequent, mechanistically-understood risk to
  GOALS coverage for a statistically consistent and sometimes substantial parameter-diversity
  gain, with no observed state-coverage cost and no established runtime cost — **not yet
  sufficient for a general superiority claim**, and the GOALS-risk rate and any runtime cost both
  need more data before being quoted as numbers.

---

## 7. Open items / recommended next steps

1. **Properly interleaved runtime benchmark** (GOALS/SP/GOALS/SP/... or fresh process per run) to
   actually isolate method-specific cost from session drift — still not done. The single
   remaining genuinely open question from the measurement side of this investigation.
2. ~~The `origin/master` merge~~ — **DONE, 2026-10-18.** Merged cleanly (`git merge
   origin/master`, local commit `a226c10`, not pushed — stashed/popped this work around it, no
   conflicts). `ensemble-code.js` was untouched by the merge (origin/master's own copy there is
   an old toy placeholder that was never actually ahead of this branch, so git correctly kept
   this branch's version). As predicted, `9c423cb` (deletes `requestOneOf`, moves `createLoan`
   onto `requestOneOfDirect`) broke `loanCompletion()`'s `!d.model` guard and the invalid-loan
   `GOALS` entry's description match — both confirmed via fresh live-SUT samples and fixed (guard
   removed; invalid-loan entry switched from `loanCompletion(...)` to `nameMatches(...)`, since
   invalid completions now have `parameters: {}` with no description, only `model.name`).
   Re-validated: `goalsRankingFunction` achieves 8/8 GOALS again post-merge, the exact-match
   state-reconstruction check still passes (5/5), unit tests pass. Also discovered in passing:
   origin/master's `lib_stories.js` already contained the exact "Step two: Coverage" text from the
   very start of this investigation (§1) — it existed in the repo all along, just not in this
   branch yet; and origin/master's own `a961922` review comments independently flag the same
   `generateMissingId(generateUserId())` id-burning bug found in §4.3, from a separate Claude
   session — external confirmation that diagnosis was correct.
3. **Retest pilot 4's scale (`--size=20`) at a larger n** (§5.4 did this for size=10), to get a
   comparable statistical read on both the parameter-coverage gain and the GOALS-risk rate at that
   scale.
4. **Address the GOALS-loss risk from §5.6** — not yet done. A ranking function that's aware of
   GOALS alongside state+parameter coverage (in whatever form) would need its own design and
   validation before being adopted.

## 8. eventPriority fix validated against the live SUT (2026-10-24)

Context shifted since §5-7 above: the project moved from the goals/state-param/two-stage design
documented there to a simpler committed design (branch `RANKINGFUNCTIONIMPL`, commit `e975739`) —
pure state-feature coverage, no GOALS, 7 features (added `USER_WITH_TWO_BOOKS`). Brought onto
`guided-ess-reachability-check` via cherry-pick. `HOLD_CREATABLE` was then dropped (2026-10-24):
its DAL query (`UserBook.CanCreateHold`) is `e.type === 'user-book'` with no other condition, so
it's true for any existing user-book pair — confirmed vacuous, not just suspected — leaving 6
features: `BOOK_DELETE_ELIGIBLE`, `USER_DELETE_ELIGIBLE`, `LOAN_CREATABLE`, `HOLD_WITHOUT_LOAN`,
`MULTI_USER_BOOK_RELATIONS`, `USER_WITH_TWO_BOOKS`.

This section addresses §7's unresolved "not yet fixed" marker-reliability finding (the 45-78%
miss rate from the original 6-feature measurement, superseded above). Fix applied:
`markStateFeature()` in `lib_stories.js` now requests the event with `eventPriority: 1010` (same
convention `controlLib.js`'s `Ctrl.markEvent` uses) instead of a bare offer.

**Method:** two fresh `provengo sample --overwrite --size=10 --max-length=80` runs against the
live SUT, same parameters, only the fix toggled — Baseline (`eventPriority` absent, the
pre-existing behavior) vs Candidate (`eventPriority: 1010`). `verify_state_features.py` was
extended to compute both miss rate (ground-truth true, marker absent) and false-positive rate
(ground-truth false, marker present) per feature, independently reconstructing ground truth from
the raw REST create/delete stream exactly as before — not from the markers themselves.

| feature | Baseline miss rate | Candidate miss rate | Baseline false+ rate | Candidate false+ rate |
|---|---|---|---|---|
| BOOK_DELETE_ELIGIBLE | 50.0% (5/10) | **0.0%** (0/10) | n/a (always true) | n/a |
| USER_DELETE_ELIGIBLE | 40.0% (4/10) | **0.0%** (0/10) | n/a (always true) | n/a |
| LOAN_CREATABLE | 70.0% (7/10) | **0.0%** (0/9) | n/a (always true) | 0.0% |
| HOLD_WITHOUT_LOAN | 100.0% (4/4) | **0.0%** (0/7) | 0.0% | 0.0% |
| MULTI_USER_BOOK_RELATIONS | 100.0% (1/1) | **0.0%** (0/2) | 0.0% | 0.0% |
| USER_WITH_TWO_BOOKS | n/a (0 true) | **0.0%** (0/2) | 0.0% | 0.0% |

Candidate: 0% miss and 0% false-positive on every feature, 10/10 traces. Baseline reproduces the
same severe miss pattern §5.6/§5.7 already found (40-100% across the features that were true at
all in this run). Raw sample files kept (not committed, `products/` is gitignored):
`products/coverage-experiments/samples_baseline_no_eventpriority.json` and
`samples_candidate_eventpriority_fix.json`.

**Caveats, not yet addressed:**
- Single run per arm (n=1), not repeated like §5's paired-repeat methodology — a 0%-vs-high%
  contrast this large is unlikely to be noise, but a second independent pair of runs would make
  this a repeat-backed claim rather than a single comparison.
- Small pool (10 traces/depth 80): `MULTI_USER_BOOK_RELATIONS` was true only 1-2/10 times in
  either run, and `USER_WITH_TWO_BOOKS` only 2/10 in the candidate (0/10 in baseline) — too few
  true occurrences in this sample to treat those two features' rates as reliable on their own,
  independent of the overall pattern.
- Did not check whether `eventPriority: 1010` changes the sampled traces' own REST-level behavior
  (e.g. selection order of non-marker events) — only that it fixes marker detection. The two
  sample files were generated independently (not paired/seeded), so some of the per-feature
  true-count differences (e.g. LOAN_CREATABLE 10/10 baseline vs 9/10 candidate) reflect ordinary
  run-to-run sampling variance, not the fix itself.

### 8.1 Three independent repeats per arm (2026-10-24, same day)

Addresses the first two caveats above. 3 independent `provengo sample --overwrite --size=10
--max-length=80` runs per arm (6 runs total, same live SUT, un-paired/un-seeded - no `--seed`
flag available in this Provengo version, same limitation noted in the earlier §5 pilots). Each
run's raw `samples.json` was measured in place immediately and NOT kept (only repeat 1's two
files, already saved under `products/coverage-experiments/`, were retained) - avoids piling up
further hundreds-of-MB files without reason.

**Per-run miss rate (3 runs per arm), with per-run true-occurrence count in parentheses:**

| feature | Baseline run1/2/3 | Candidate run1/2/3 |
|---|---|---|
| BOOK_DELETE_ELIGIBLE | 50.0%(10) / 60.0%(10) / 70.0%(10) | 0.0%(10) / 0.0%(10) / 0.0%(10) |
| USER_DELETE_ELIGIBLE | 40.0%(10) / 40.0%(10) / 60.0%(10) | 0.0%(10) / 0.0%(10) / 0.0%(10) |
| LOAN_CREATABLE | 70.0%(10) / 80.0%(10) / 70.0%(10) | 0.0%(9) / 0.0%(10) / 0.0%(10) |
| HOLD_WITHOUT_LOAN | 100.0%(4) / 71.4%(7) / 71.4%(7) | 0.0%(7) / 0.0%(3) / 0.0%(7) |
| MULTI_USER_BOOK_RELATIONS | 100.0%(1) / 100.0%(1) / n/a(0) | 0.0%(2) / 0.0%(2) / 0.0%(3) |
| USER_WITH_TWO_BOOKS | n/a(0) / 66.7%(3) / 75.0%(4) | 0.0%(2) / 0.0%(5) / 0.0%(4) |

False-positive rate was 0% in every run, every feature, both arms, all 3 repeats - omitted from
the table above for space.

**Pooled across the 3 repeats (30 traces per arm)** - resolves the "too few true occurrences"
caveat for the two rare features, which now have real sample sizes:

| feature | Baseline pooled miss rate | Candidate pooled miss rate |
|---|---|---|
| BOOK_DELETE_ELIGIBLE | 60.0% (18/30) | **0.0%** (0/30) |
| USER_DELETE_ELIGIBLE | 46.7% (14/30) | **0.0%** (0/29) |
| LOAN_CREATABLE | 73.3% (22/30) | **0.0%** (0/29) |
| HOLD_WITHOUT_LOAN | 77.8% (14/18) | **0.0%** (0/17) |
| MULTI_USER_BOOK_RELATIONS | 100.0% (2/2) | **0.0%** (0/7) |
| USER_WITH_TWO_BOOKS | 71.4% (5/7) | **0.0%** (0/11) |

Candidate: 0% miss in every one of 3 independent repeats, for every feature, with no exception -
including the two rare features now backed by 7-11 true occurrences each (pooled), not 1-2.
Baseline: consistently high miss rate (40-100%) in every repeat, every feature - the pattern is
stable across repeats, not a one-off from the single-run comparison in §8 above.

**Still not addressed:** runs remain unpaired (independent samples, not matched/replayed traces)
- the advisor's suggested mitigation (paired/matched traces) wasn't attempted, since Provengo
sampling has no seed control to make that practical here. Given the 0%-vs-40-100% contrast
reproduces identically across 3 independent repeats per arm, run-to-run sampling variance is not
a plausible alternative explanation for the result at this point.

## 9. Does `provengo ensemble` actually select for state coverage? (2026-10-24)

§8's unit tests proved `rankingFunction` computes the right number given a set of events; this
checks the next question - does the real `provengo ensemble` command (GeneticOptimizer) actually
use that number to prefer better-covering subsets, against a real sampled pool, not a synthetic
one.

**Method:** `provengo sample --overwrite --size=20 --max-length=80` against the live SUT (one
fresh pool), then `provengo ensemble --size=5` (GeneticOptimizer, default `rankingFunction`).
Compared the optimizer's chosen 5-trace subset against three naive 5-trace subsets drawn from
the *same* 20-trace pool: first 5, last 5, and a deliberately worst-case subset (the single
shortest trace in the pool, duplicated 5x - zero diversity by construction). Verified every
score two independent ways: (a) `verify_state_features.py`'s marker-count reconstruction, (b)
calling the real `rankingFunction` from `ensemble-code.js` directly (via Node's `vm` module) on
each candidate file - not trusting the optimizer's self-reported number alone, per the
methodological lesson from the earlier goals/state-param investigation (§5's "don't trust one
opaque number" principle).

| candidate | rankingFunction score | features covered |
|---|---|---|
| GeneticOptimizer's choice (`provengo ensemble --size=5`) | **100.0** | 6/6 |
| naive: first 5 traces in the pool | 100.0 | 6/6 |
| naive: last 5 traces in the pool | 83.3 | 5/6 (missing MULTI_USER_BOOK_RELATIONS) |
| worst case: shortest trace duplicated 5x | 33.3 | 2/6 (only the two always-true features) |

Both independent scoring methods (marker-count script and the real `rankingFunction` called
directly) agreed exactly on all four numbers.

**Conclusion:** the ranking does discriminate correctly - a subset missing one feature scores
noticeably lower (83.3 vs 100), and a maximally-undiverse subset scores far lower still (33.3).
The optimizer's claimed rank 100 is independently confirmed, not just self-reported. The fact
that a naive first-5 pick *also* reached 100 here is the same small-pool ceiling effect already
documented in §5/§5.7 (BOOK_DELETE_ELIGIBLE/USER_DELETE_ELIGIBLE/LOAN_CREATABLE are easy to hit
with only 4 users/4 books) - not a flaw in the ranking function, which still correctly penalizes
the two inferior naive picks tried here. Not yet checked: whether the optimizer outperforms naive
selection reliably at a larger pool/ensemble size where the ceiling effect is less dominant (§5.7
found a real GOALS-vs-coverage trade-off only appeared at `--size=20` scale, not `--size=10`) -
this one pool/one optimizer run is a single data point, not a repeated-trial result like §8.1.

Transient files from this check (`samples.json`, `ensemble_candidate.json`, three naive-subset
files) were deleted after extracting these numbers - not kept, per the same "don't accumulate
raw files without reason" guidance as §8.1.

### 9.1 Optimizer vs. the actual distribution of naive picks, repeated, at larger scale (2026-10-24)

§9 only compared against 3 fixed hand-picked naive subsets (first-5/last-5/worst-case), one pool.
Addresses that gap: at each pool, generated 2000 random 5-subsets (or 3-subsets - see below) and
looked at where the optimizer's score falls in that actual distribution, not just against 3
arbitrary points. Computed efficiently in Python by pre-computing each trace's own marker-feature
set once (via `verify_state_features.py`'s `replay_trace`), then scoring each random subset as a
cheap set union - avoids reloading/reparsing the ~900MB-1GB raw files repeatedly, and avoids
Node's ~536MB `fs.readFileSync` string-length ceiling hit when first attempted here.

**Repeat 1** (fresh `--size=30 --max-length=80` pool, `provengo ensemble --size=5`):
optimizer score 100.0. Random 5-subsets (N=2000): min=50.0, median=100.0, mean=93.48, max=100.0 -
**66.0%** of random picks already reach the maximum.

**Repeat 2** (fresh pool, same settings): optimizer score 100.0. Random 5-subsets (N=2000):
min=66.7, median=100.0, mean=93.71, max=100.0 - **66.5%** reach the maximum. Near-identical to
repeat 1 - the ceiling effect at pool=30/ensemble=5 is stable, not a one-off.

**Third data point, varying the other lever (ensemble size, same pool as repeat 2):**
`provengo ensemble --size=3` instead of 5. optimizer score 100.0. Random **3**-subsets (N=2000):
min=50.0, **median=83.3**, mean=86.57, max=100.0 - only **38.9%** reach the maximum.

**Conclusion:** at ensemble size 5, naive selection is frequently as good as the optimizer at
this pool scale (66% tie rate) - the open question from §9 stands for that specific setting.
Shrinking the ensemble to size 3 (same pool, more selective) surfaces a real, meaningful gap: the
optimizer still reliably finds a maximum-score (100) ensemble, while a *typical* naive pick does
not (median 83.3, mean 86.6) - the optimizer beats the median/mean naive pick by a clear margin,
even though occasional lucky naive picks (~39%) still tie it. This reframes §9's open question:
the right comparison isn't "does the optimizer ever beat naive," it's "how often, and the answer
depends heavily on how constrained the ensemble-size/pool-size ratio is" - a smaller/more
selective ensemble relative to the pool is where the optimizer's value is clearest.

**Not yet done:** didn't test larger pool sizes (only pool=30 tried) or ensemble sizes between 3
and 5, so the exact point where naive selection stops being competitive isn't pinned down - only
that it's somewhere between these two ratios (5/30=1:6 vs 3/30=1:10). All raw files from this
subsection were deleted after extracting the printed numbers above; only those numbers are kept.

## 10. Does the GeneticOptimizer actually optimize Parameter Coverage? (2026-10-25)

Same question as §9/9.1, now for `parameterCoverageFunction` (added after §9.1, in a separate
commit - see git history) instead of `rankingFunction`. Per the documented CLI rank-reporting
quirk (see `ensemble-code.js`'s `parameterCoverageFunction` doc comment), the CLI's own printed
"rank" was NOT trusted - every number below comes from independently re-scoring the actual
written ensemble file (or raw pool) via a direct call to `parameterCoverageFunction`/a matching
Python reimplementation, never from the CLI's live log line.

**Method:** fresh `provengo sample --overwrite --size=20 --max-length=80` against the live SUT,
`provengo ensemble --size=5 --ranking-function=parameterCoverageFunction`. Compared against: (a)
2000 random 5-subsets of the same 20-trace pool (Python, precomputed per-trace pair-sets, same
technique as §9.1), (b) the TRUE maximum achievable, found by exhaustively scoring all C(20,5) =
15,504 possible 5-subsets (feasible to brute-force at this size, same precedent as the old grid
search in §5.8-equivalent work).

| candidate | parameterCoverageFunction score (re-scored, not CLI-reported) |
|---|---|
| GeneticOptimizer, default generations | 21.875 |
| GeneticOptimizer, `--num-of-generations=200` | 28.125 |
| random 5-subsets (N=2000): min / median / mean / max | 6.25 / **21.875** / 21.8 / 40.625 |
| TRUE maximum (exhaustive C(20,5)) | **40.625** |

**This is a materially different result from §9/9.1's state-coverage finding.** For state
coverage, the optimizer reliably found the true maximum in every test run. Here, at default
settings, the optimizer's chosen ensemble scored EXACTLY the median of 2000 random picks - 57.6%
of random 5-subsets scored at least as well. Raising `--num-of-generations` from its default to
200 improved the result (21.875 -> 28.125) but still fell well short of the true maximum (40.625)
that genuinely exists in this exact pool (traces 1, 3, 4, 5, 14 together cover all 13 of the
pool's 13 total distinct in-range pairs).

**Interpretation:** the metric itself is not the problem - it correctly spans a wide range
(6.25 to 40.625 depending on which 5 traces are picked), so it clearly can discriminate between
good and bad ensembles. The GeneticOptimizer's default search specifically underperforms on this
metric at this pool/ensemble size, in a way it did not for state coverage. Plausible reasons not
yet distinguished: (a) genuinely harder fitness landscape for this metric (e.g. more local optima
from 32 independent loan/hold pair "slots" vs. 6 state features), (b) the metric's wider
dynamic range makes the optimizer's default generation count simply insufficient here even
though it was enough for state coverage's smaller, more saturated landscape. Not yet tested:
whether an even higher generation count (500+) closes the remaining gap to 40.625, or whether
this pool is unusual (only one pool tested, n=1, same single-data-point caveat as §9).

**Practical takeaway for now:** don't assume `provengo ensemble`'s default settings are adequate
for parameterCoverageFunction the way they were (independently confirmed) for state coverage -
this needs either a higher `--num-of-generations` or a documented caveat about optimizer quality
whenever parameter coverage is used for real test-suite selection, not just measurement.

All raw files from this section (`samples.json`, both ensemble output files) were deleted after
extracting the numbers above, per the same "don't accumulate raw files" practice as earlier
sections.

### 10.1 Repeat on a second independent pool (2026-10-25)

Same method as §10, fresh `--size=20 --max-length=80` pool, independent of the first. Addresses
§10's "only one pool tested" caveat directly.

| candidate | parameterCoverageFunction score |
|---|---|
| GeneticOptimizer, default generations | 15.625 |
| GeneticOptimizer, `--num-of-generations=200` | 25.0 |
| random 5-subsets (N=2000): min / median / mean / max | 6.25 / **15.625** / 16.7 / 28.125 |
| TRUE maximum (exhaustive C(20,5)) | **28.125** |

**The core pattern reproduces exactly:** the default-generation optimizer again scored precisely
the median of 2000 random picks (15.625 both times, on two different pools - not a coincidence
of one unlucky run). 200 generations again closed most but not all of the gap - this time 25.0
vs. the true max 28.125 (gap of 3.125, proportionally smaller than §10's gap of 12.5 at
40.625 - though this pool's overall ceiling was lower too, so the two gaps aren't on identical
scales).

**What this settles vs. what it doesn't:** two independent pools now agree that
`provengo ensemble`'s *default* generation count underperforms for `parameterCoverageFunction`,
tying the random median rather than beating it - this specific finding is no longer a single-pool
fluke. Still open, per H1/H2 from §10: whether the remaining gap at 200 generations is a search-
budget issue (H2 - keeps shrinking with more generations) or a landscape issue (H1 - plateaus
short of the optimum regardless of budget) can't be distinguished from two data points at only
one generation-count step (default vs. 200) - that needs a sweep across several generation
counts on the same pool, not another independent pool. Also still not tested: run-to-run
variance from the optimizer's own randomness (no `--seed` available) holding the pool fixed -
the two "default" and two "200-gen" numbers above each come from a different pool, not repeated
runs on the same one, so they conflate pool-to-pool variation with the optimizer's own
run-to-run variation.

Raw files from this repeat (second `samples.json`, two ensemble output files) deleted after
extracting the numbers above, same practice as before.

### 10.2 Generation-count sweep on one fixed pool, 2 repeats each (2026-10-25)

Directly targets distinguishing H1 (hard landscape) from H2 (insufficient search budget) from
§10, by holding the pool fixed and varying only `--num-of-generations`, with 2 independent repeats
per setting (no `--seed` available, so repeats are the only way to separate generation-count
effect from the optimizer's own run-to-run randomness - exactly the methodological point raised
before this experiment).

One fresh `--size=20 --max-length=80` pool, reused for all 12 runs below. Reference for this pool
(random 5-subsets, N=2000): min=3.125, median=18.75, mean=17.46, **max=25.0** (which also equals
the exhaustive true optimum over all C(20,5) - confirmed separately). Every score below is
independently re-scored from the CLI's own written output file (never the CLI's printed rank).
Run durations (24s -> 34s as generations rose from default to 500) confirm `--num-of-generations`
was genuinely honored, not silently capped.

| generations | repeat 1 | repeat 2 | mean |
|---|---|---|---|
| default | 6.25 | 9.375 | 7.81 |
| 10 | 15.625 | 15.625 | 15.625 |
| 50 | **25.0** | 12.5 | 18.75 |
| 100 | **25.0** | 12.5 | 18.75 |
| 200 | 12.5 | 21.875 | 17.19 |
| 500 | 21.875 | 21.875 | 21.875 |

**This does not cleanly settle H1 vs. H2 - it shows a third factor dominates at this scale:
run-to-run variance from the optimizer's own randomness is large enough to swamp any smooth
generations trend in this range.** Within a single generation-count setting, scores swing from
12.5 to 25.0 (50 and 100 generations both show one repeat hitting the true optimum exactly and
the other landing at less than half that) - a bigger spread than the difference between most
adjacent generation-count rows. The mean-per-setting column shows a rough, noisy upward drift
(7.81 -> ~17-19 -> 21.875), consistent with H2 (more budget helps on average), but §10's
H1-style plateau also shows up at the top end: 500 generations gave the most *consistent* result
of the sweep (identical 21.875 both repeats - the only setting where the two repeats agreed) but
still fell short of the true optimum (25.0) in both of its repeats, not just on average.

**Honest interpretation for presenting this:** default generation count is clearly worse on
average than higher settings (this part is solid - 7.81 vs 500's 21.875, and default never once
got close to the optimum in either repeat here or in §10/§10.1's two single-repeat runs).
Beyond that, the data doesn't cleanly separate "search budget" from "landscape difficulty" as
the cause of the remaining gap to 25.0 at 500 generations, because run-to-run noise at the
SAME setting is itself large relative to the gap being measured. A cleaner test would need many
more repeats per setting (e.g. 5-10) to get a reliable mean/variance per generation count, or a
search method with reproducible seeding - neither done here (cost/time tradeoff, per the
"don't rush into hundreds of runs" guidance this experiment was already following).

**Practical takeaway, unchanged in direction from §10/§10.1 but now better grounded:** don't use
`provengo ensemble`'s default generation count for parameter-coverage-driven ensemble selection -
it was the worst-scoring setting in each of the three pools/experiments checked so far (§10,
§10.1, §10.2), a consistent finding within that specific sample, not a general claim about every
possible pool or configuration. Raising generations materially helps on average in what's been
tested, though exactly how many are "enough" remains open given the observed run-to-run variance.

All 12 raw ensemble output files plus the pool's `samples.json` were deleted after extracting the
scores above - only this table and the reference numbers are kept, per the same practice as
every earlier experimental section.
