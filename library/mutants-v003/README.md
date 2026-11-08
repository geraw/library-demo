# Library mutation mechanism repair v003: experimental release

Experimental release authorized for Existing and Sample pilots. Not a qualified rare-fault benchmark. See RUNNING.md for both commands.

All six mutants have directed legal witnesses. All 48 witness/mode combinations
pass their expectations: each witness succeeds on original, baseline, and the five
unrelated mutant modes; only its targeted mode fails. The nine mutation regression groups pass,
including the five former v002 shortcuts, reset, seeded reset, and input validation.
The original source is unchanged. Uses no fixed user numbers, event-sequence recognizer,
probability gates, clocks, numeric mutation counters or extra public endpoints.

## Actual mechanisms

B1: shared reservation ticket retains old borrower across a handoff. The defect only
becomes observable after the handoff borrower returns the book, the last reservation
is canceled, and the original borrower has another loan. A no-handoff control passes.

B2: deferred retirement descriptors form a cycle across three books and three
borrowers. A faulty cycle fallback cascades by borrower rather than the deleted book.
The former straight-line and acyclic chained-retirement counterexamples now pass.
This is an experimental auxiliary cleanup graph, not an existing original-SUT feature.

B3: hold-position repair is deferred across independently pinned borrower regions.
An owner releases a loan, repins a region under a new loan incarnation while another
region is still pinned, and a stale repair overwrites the current position mapping
at final release. The former ordinary single release and non-repin cases pass.
This candidate still occurs in 6/84 old traces, and is rejected for the rarity target.

B4: a filtered loan-query cache is leased by crossed reservations. The queried loan
is returned and recreated; a positive refresh is staged, but final lease release
merges the old incarnation over the refreshed row. Plain return, dirty bypass,
empty refresh and release without positive refresh no longer expose the bug.

B5: a composite loan index retains an incarnation while crossed reservations pin
it. Both its user side and book side are separately rebound before the original
pair is recreated. Missing replacement then deletes the old incarnation instead of
the current loan. Ordinary repeats and a single rebound side now pass.

B6: a deferred book-list page is pinned by a user's holds on different currently
borrowed books. One book is returned, unreserved and deleted while the other lease
remains; final lease release merges a stale page without checking deletion tombstones.
The original simple borrowing/hold/delete shortcut now passes.

The indexed baseline maintains all these structures without their mutation branches.
Added deferred subsystems are synthetic benchmark infrastructure and need a separate
realism/literature review; no top-six prevalence or six-disjoint-families claim is made.

## Local measured screening (84 existing projected traces)

| Mode | v002 different cases | Current different cases |
|---|---:|---:|
| B1 | 33 | 1 |
| B2 | 47 | 0 |
| B3 | 84 | 6 |
| B4 | 40 | 0 |
| B5 | 84 | 2 |
| B6 | 70 | 1 |

Both controls pass all 84 (11,154 retained requests from 124,481 source requests).
An additional independently generated functional probe passes 100 scenarios with
200 operations plus six setup requests each, on both original and baseline (200
control replays). This probe is not a Provengo distribution or a rarity experiment.

Three iterations reused the same 84 traces for calibration. Zero on these traces
is NOT holdout evidence and does NOT establish low detection in 500 scenarios.
B1/B5/B6 still show known activations and B3 remains too easy. Do not describe this as a finished rare-fault benchmark, or silently add further guards just to zero the calibration set.

`witnesses.json` retains full directed traces and greedily reduced traces. Reduction
requires retained-response agreement on both controls and detection on the mutant.
It is NOT proof of globally shortest prefixes. Setup requests are included in counts.
`first-differences.json` stores the first actual divergent request/response per case.

## Reproduce locally

Install requirements, then run from this directory:

```
python -m unittest test_regressions -v
python verify.py
python probe_controls.py
python reduce_witnesses.py
```

For the archived evidence ZIP use replay.py exactly as in v002. The engine remains
Flask test_client, not native Provengo or TCP. New native compact sampling is provided in Sample mode; see RUNNING.md. Old source
ZIP and historical results are unchanged. Windows/PowerShell and native Provengo compact sampling have not been exercised here; see the explicit validation boundary in RUNNING.md.

The clean-scenarios data upload is commit 4201583. v003 is now separately published as an experimental release; v002 remains unchanged.
