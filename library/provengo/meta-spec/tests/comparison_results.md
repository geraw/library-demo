# GOALS vs State+Parameter ranking - comparison pilots (2026-10-15)

Measured with `compare_ensembles.py` (reimplements the coverage checks independently of
`goalsRankingFunction`/`stateParamScore`, so the comparison isn't circular). Both rankings run
with `--algorithm=genetic --size=5 --num-of-generations=50` on the identical `samples.json`.
Raw ensemble JSON files are NOT checked in (each ~160MB, regenerate via the commands below into
`products/coverage-experiments/` - already gitignored).

> **2026-10-18 update:** merged `origin/master` into this branch (4 commits, including `9c423cb`
> which deletes `requestOneOf` and moves `createLoan` onto `requestOneOfDirect`). This broke
> `loanCompletion()`'s `!d.model` guard and the invalid-loan GOALS entry's description-based match
> (confirmed empirically against fresh live-SUT samples) - both fixed; see `ensemble-code.js`'s
> updated `loanCompletion()` comment and the `GOALS` array (`nameMatches` instead of
> `loanCompletion` for the invalid-loan entry). All pilots below predate this merge and were run
> against the pre-merge event shapes; re-validated post-merge via a fresh sample + GOALS ensemble
> run (8/8 goals achieved again) and the exact-match state-reconstruction check (still 5/5 exact) -
> no pilot numbers are expected to change, but they were not literally rerun post-merge.

> **⚠️ Pilots 1 and 2 below use an UNRELIABLE state-feature measurement and must not be used to
> draw conclusions about State Coverage.** They measured state features via the in-model
> `StateFeature` marker events, which were later found (2026-10-15, same day, after these pilots)
> to miss 45-78% of genuinely-true occurrences - see `verify_state_features.py` and the
> `reconstructStateFeaturesForTrace` fix in `ensemble-code.js`. The GOALS and parameter-coverage
> numbers in pilots 1-2 are unaffected by that bug and remain valid; only their "state features"
> rows are unreliable. Kept below for history/comparison, NOT overwritten - see "Pilot 3+" for
> results using the corrected, cross-validated state measurement (10/10 exact match against an
> independent Python reconstruction).

## Pilot 1: `provengo sample --overwrite --size=10 --max-length=80`

| metric | GOALS-selected | state+param-selected |
|---|---|---|
| state features | 6/6 | 6/6 |
| GOALS | 8/8 | 8/8 |
| distinct param tags | 16 | 22 (+37.5%) |
| duplicate traces | 0 | 0 |

Both methods saturated on state/GOALS coverage - likely a ceiling effect of the small (10-trace)
pool, not evidence the methods are equivalent on those axes. See pilot 2.

## Pilot 2: `provengo sample --overwrite --size=20 --max-length=80`

| metric | GOALS-selected | state+param-selected |
|---|---|---|
| state features | 5/6 (missing MULTI_USER_BOOK_RELATIONS) | 5/6 (also missing it) |
| GOALS | 8/8 | **7/8** (missing "deleteUser (valid)") |
| distinct param tags | 17 | **26** (+52.9%) |
| duplicate traces | 0 | 0 |

Neither method saturated this time, confirming pilot 1's ceiling-effect hypothesis. This run
surfaces a real trade-off pilot 1 didn't: `stateParamRankingFunction` buys substantially more
parameter diversity but loses one GOALS target entirely, because it has no visibility into GOALS
at all - nothing anchors it to preserve that coverage if a more param-diverse candidate set
happens to lack it.

## Caveats

- Single run per method per pilot - the CLI has no `--seed` flag for the genetic optimizer, so
  true run-to-run variance from the search itself (vs. the ranking function's effect) wasn't
  isolated. `--num-of-generations` was matched across both methods as the one controllable
  "equal budget" variable.
- `PARAMETER_UNIVERSE_SIZE`'s denominator (`USER_ID_CEILING`/`BOOK_ID_CEILING` = entity count + 2)
  is an experimental safety ceiling derived from a real bug (see `ensemble-code.js`'s comments
  near those constants), not a validated true parameter-value universe. It affects the
  state-vs-parameter weighting inside the score, not just the displayed number - confirmed
  mathematically and empirically (changing it alone changed which candidate ensemble won on a
  held-fixed sample set).
- Not yet tried: a ranking function combining all three signals (GOALS + state + parameters), or
  sweeping `ALPHA` to see whether the GOALS regression in pilot 2 can be avoided while keeping
  most of the parameter-coverage gain.

## Pilot 3: controlled 3-repeat comparison, CORRECTED state-feature measurement (2026-10-15)

Follows the advisor's stage-5 plan: 3 independent sample pools (same settings each:
`--overwrite --size=10 --max-length=80`), same `--size=5 --num-of-generations=50` budget for
both ranking functions on each pool, measured with the now-corrected `compare_ensembles.py`
(uses `verify_state_features.py`'s cross-validated reconstruction, not `StateFeature` markers).
No `--seed` flag exists in this Provengo version, so true seed control wasn't possible - each
repeat uses an independently freshly-sampled pool instead (documented limitation, per advisor's
fallback guidance).

| repeat | method | state features | GOALS | param tags | sample time | ensemble time |
|---|---|---|---|---|---|---|
| 1 | GOALS | 6/6 | 7/8 | 19 | 20.4s | 24.4s |
| 1 | state+param | 6/6 | 7/8 | **20** | (same pool) | 27.1s |
| 2 | GOALS | 5/6 | 7/8 | 16 | 21.7s | 26.4s |
| 2 | state+param | 5/6 | 7/8 | **18** | (same pool) | 29.1s |
| 3 | GOALS | 5/6 | 8/8 | 14 | 20.5s | 26.3s |
| 3 | state+param | 5/6 | 8/8 | **21** | (same pool) | 29.2s |

**Result: state features and GOALS coverage were IDENTICAL between the two ranking methods in
all 3 repeats** - no trade-off observed at this pool size, unlike pilot 2's apparent GOALS
regression (which used the since-corrected, unreliable state measurement and a larger pool,
`--size=20`; it's not yet known whether that regression was pool-size-specific, a one-off, or an
artifact of the old measurement - not re-tested at `--size=20` yet). **Parameter-tag coverage was
higher for state+param in all 3 repeats, with no exceptions**: +1 (19→20), +2 (16→18), +7
(14→21) - directionally consistent, though the magnitude varies considerably (5%-50%). This is a
more encouraging, cleaner result than pilot 2's apparent trade-off: at this scale, state+param
ranking's parameter-coverage advantage came at no observed cost on the other two axes across 3
independent repeats.

**Caveat:** 3 repeats is still a small number for a variance claim, and all three used the same
`--size=10 --max-length=80` settings as each other - the pilot 2 trade-off was observed at
`--size=20` and hasn't been retested with the corrected measurement at that scale. Worth
rerunning this same controlled design at `--size=20` before concluding the trade-off was purely a
measurement artifact.

## Pilot 4: controlled 3-repeat comparison at `--size=20` (pilot 2's scale), CORRECTED measurement (2026-10-15)

Same design as Pilot 3, but matching pilot 2's actual scale exactly: `provengo sample --overwrite
--size=20 --max-length=80` (20-trace pool, not 10), `--size=5 --num-of-generations=50` for the
ensemble itself (unchanged). Goal: find out whether pilot 2's GOALS/state trade-off was real or an
artifact of the old unreliable state measurement.

| repeat | method | state features | GOALS | param tags | sample time | ensemble time |
|---|---|---|---|---|---|---|
| 1 | GOALS | 6/6 | 8/8 | 16 | 37.0s | 41.4s |
| 1 | state+param | 6/6 | 8/8 | **26** | (same pool) | 79.0s |
| 2 | GOALS | 6/6 | 8/8 | 16 | 47.3s | 43.7s |
| 2 | state+param | 6/6 | **7/8** (missing "deleteBook (valid)") | **29** | (same pool) | 48.1s |
| 3 | GOALS | 6/6 | 8/8 | 21 | 44.3s | 67.9s |
| 3 | state+param | 6/6 | 8/8 | **23** | (same pool) | 117.6s |

**Result: more nuanced than pilot 3.** State features were identical (6/6) in all 3 repeats, both
methods - still no state-coverage cost. Parameter-tag coverage was higher for state+param in all 3
of 3 repeats again (+10/62.5%, +13/81%, +2/9.5%) - the consistent directional win holds at this
larger scale too. But GOALS coverage was NOT always identical this time: repeat 2 shows state+param
losing exactly one GOALS target ("deleteBook (valid)") that GOALS-ranking kept - a real, if
occasional (1 of 3 repeats), trade-off, milder than pilot 2's finding (which also lost "deleteUser
(valid)") but pointing the same direction. **Conclusion: the GOALS trade-off from pilot 2 was not
purely a measurement artifact - it reappears at this scale, just not in every run.** The parameter-
coverage advantage is the more robust, consistently-reproduced finding across both pilot 3 (size=10)
and pilot 4 (size=20); the GOALS cost is real but intermittent/probabilistic at these sample sizes,
not guaranteed each run.

## Combined statistical summary, pilots 3+4 (paired analysis, 2026-10-15)

Both methods were run on the SAME pool within each repeat, so this is a paired comparison -
analyzed as per-pool (state+param minus GOALS) differences, not separate unpaired averages, per
the advisor's explicit methodological point.

**Correction:** an earlier message in this investigation claimed ensemble runtime "reversed" in
size=20 repeat 2 (state+param faster than GOALS there). Recomputing properly below shows that is
WRONG - state+param was slower in all 3 size=20 repeats too, just by a much smaller margin in
repeat 2 (+4.4s) than repeats 1/3 (+37.6s, +49.7s). Flagging the correction rather than quietly
fixing it - this is exactly the kind of thing to double check with code instead of eyeballing a
table when the margin is small.

| metric | pool size | GOALS mean | state+param mean | paired mean diff | paired stdev | n |
|---|---|---|---|---|---|---|
| param tags | 10 | 16.33 | 19.67 | **+3.33** | 3.21 | 3 |
| param tags | 20 | 17.67 | 26.00 | **+8.33** | 5.69 | 3 |
| state features | both | 6/6 or 5/6 (identical per pair) | same | 0 in all 6 pairs | - | 6 |
| GOALS | both | - | - | 0 in 5/6 pairs, -1 in 1/6 | - | 6 |
| ensemble runtime (s) | 10 | 25.70 | 28.47 | +2.77 | **0.12** (tight) | 3 |
| ensemble runtime (s) | 20 | 51.00 | 81.57 | +30.57 | **23.45** (huge) | 3 |

**Honest reading, per the advisor's three cautions:**
1. Parameter-coverage gain is directionally consistent (positive in all 6 pairs, both pool sizes)
   but the MAGNITUDE varies a lot even within one pool size (stdev is 60-96% of the mean) - report
   it as "consistently positive, magnitude uncertain," not as a precise expected percentage.
2. State-feature cost: genuinely zero across all 6 pairs so far - the strongest, cleanest claim
   available. GOALS cost: occurred in only 1 of 6 pairs - far too few occurrences to estimate a
   reliable probability of harm (a 1/6 rate has a very wide confidence interval with this little
   data); call it "a real but infrequent trade-off, rate unknown," not a quantified risk.
3. Runtime cost is real and consistent in DIRECTION (state+param slower in all 6 pairs, no
   exceptions) but the size=20 magnitude is wildly inconsistent (12% stdev/mean at size=10 vs.
   77% at size=20) - 3 repeats is not enough to characterize this reliably, especially at the
   larger scale; needs a proper timing benchmark (more repeats, ideally isolating warm-up/JVM
   effects) before quoting a number.

**Overall framing for presenting to the advisor:** six independent paired repeats are encouraging
preliminary evidence that state+param ranking trades a small, inconsistent risk to GOALS coverage
and a consistent runtime cost for a consistent and sometimes substantial parameter-diversity gain,
with no observed state-coverage cost - NOT yet sufficient evidence for a general superiority claim,
and not yet enough to reliably quantify the GOALS-harm rate or the runtime cost at scale.

## Extended parameter-coverage sample, n=8 at size=10 (2026-10-15)

Per the advisor's 3-point plan: prioritized strengthening the parameter-coverage statistic (the
most robust finding) over chasing runtime further. Ran 5 MORE independent `--size=10
--max-length=80` repeats (same design as pilot 3), bringing that pool size's total to n=8.
State features and GOALS: identical between methods (6/6, 8/8) in all 5 new repeats, no
exceptions - no regression in this batch.

| repeat | GOALS param tags | state+param param tags | diff |
|---|---|---|---|
| 1 | 19 | 20 | +1 |
| 2 | 16 | 18 | +2 |
| 3 | 14 | 21 | +7 |
| 4 | 17 | 21 | +4 |
| 5 | 14 | 22 | +8 |
| 6 | 13 | 20 | +7 |
| 7 | 21 | 22 | +1 |
| 8 | 18 | 25 | +7 |

**n=8, all 8 diffs positive.** GOALS mean=16.50, state+param mean=21.12, mean diff=**+4.62**,
stdev diff=2.97. Approximate paired t-statistic = 4.40 (df=7), which exceeds the two-tailed
critical value at p=0.01 (≈3.50) - i.e. this result would conventionally be called statistically
significant at the size=10 scale, not just "directionally consistent." Caveats: n=8 is still
modest, normality of the differences wasn't separately verified, and this applies specifically to
the size=10/ensemble-size=5 scale tested here - the size=20 pilot 4 data (separate n=3 group,
mean diff +8.33) point the same direction but weren't pooled into this statistic since they used
a different pool size.

## Controlled runtime benchmark (2026-10-15) - OVERTURNS the earlier runtime finding

Design: ONE fixed sample pool (`--size=20 --max-length=80`, generated once, reused for every run
below - removes pool-content variance as a confound). 1 discarded warm-up run per method, then 5
TIMED runs per method, same `--size=5 --num-of-generations=50` each time. Run order: all 5 GOALS
runs first, then all 5 state+param runs (a block design, NOT interleaved - see caveat below).

| method | run 1 | run 2 | run 3 | run 4 | run 5 | mean | stdev |
|---|---|---|---|---|---|---|---|
| GOALS | 54.1s | 44.6s | 99.4s | 113.3s | 127.7s | 87.79s | 36.68s |
| state+param | 97.9s | 42.8s | 89.6s | 112.2s | 107.5s | 90.00s | 27.78s |

**Difference of means: 2.2 seconds - negligible compared to the within-method standard
deviations (36.68s / 27.78s).** Both methods independently show a strong INCREASING trend across
their own 5 sequential runs (GOALS: 54→45→99→113→128; state+param: 98→43→90→112→108, same shape)
- this is the same ranking function run 5 times on identical input, so the trend cannot be caused
by which ranking function is used. It points to a session-level effect (e.g. JVM/GC warm-up
continuing past the single discarded warm-up run, or rising background load over the ~15-minute
session) that makes LATER invocations slower, regardless of what they compute.

**This directly explains pilots 3 and 4's "state+param consistently slower, 6/6 repeats" finding
as a likely ORDER ARTIFACT, not a real property of the ranking function**: every prior repeat ran
`sample → GOALS ensemble → state+param ensemble` in that fixed order within one session, so
state+param always executed chronologically LATER - exactly the position this benchmark shows is
slower regardless of method. The apparent "runtime cost of state+param" in pilots 3/4 was likely
measuring "cost of running second," not "cost of this ranking function."

**Caveat on this benchmark's own design:** it still isn't interleaved (all 5 GOALS runs happened
before any state+param run), so it can't fully separate "session drift over time" from "method B
specifically" either - it only shows the effect is at least as large as, and plausibly entirely
explains, the earlier finding. A proper follow-up would interleave the two methods run-by-run
(GOALS, SP, GOALS, SP, ...) or restart the process between every single run, to isolate the two
effects cleanly. Not done here due to time - flagging the correction is more important than
fully completing the ideal design right now.

## Reproducing

```powershell
cd library\provengo
provengo sample --overwrite --size=20 --max-length=80 .
provengo ensemble --algorithm=genetic --ranking-function=goalsRankingFunction --size=5 --num-of-generations=50 -o products/coverage-experiments/ensemble_goals.json .
provengo ensemble --algorithm=genetic --ranking-function=stateParamRankingFunction --size=5 --num-of-generations=50 -o products/coverage-experiments/ensemble_stateparam.json .
python meta-spec/tests/compare_ensembles.py products/coverage-experiments/ensemble_goals.json products/coverage-experiments/ensemble_stateparam.json
```
