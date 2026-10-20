# ISSTA v005: four business faults plus one book-read fault

Reuse the immutable v004 business sample and successful control results. Each
case resets all four collections and starts a fresh Provengo JVM/RTV context.
The two arms are `business-four` (ISSTA_BUGS=1,2,3,5) and `book-read-one`
(ISSTA_BUGS=4). No new sampling, control replay, automatic test repair or
continue-after-failure behavior is introduced. Business faults may still mask
each other; the five isolated runs remain diagnostic validation, excluded from
comparison budgets. Complete arm outputs are skipped on restart; incomplete
outputs are preserved and require inspection. Earlier runs are never replaced.

## Budget and cross-tool comparison

Each arm publishes its own budget: full original sampling time plus that arm's
mutant replay time, rounded up to seconds. The generation charge appears in both
separate comparisons; it is not a claim of additional actual generation time.
Control, smoke, and five-fault isolated validation are excluded. Report both arms
separately for every tool; do not remove bug 4 from EvoMaster or RESTler results.
Keep identical SUT, contract, ports, seed policy and observer within each arm.
Do not interpret 404 responses alone as native detection: retain native generated
assertions/checker reports as well as independent observer verdicts. Record
successful resource creation, actual GET of a known existing book, time to first
such GET/404, native reporting, and independent oracle detection. Missing
coverage is distinct from failure to report a covered bug.

EvoMaster launch (installed JAR required), once budgets exist:

```powershell
& .\.venv\Scripts\python.exe .\library\ess-experiment\campaign-v005\split_v005.py evomaster --campaign $campaign --arm book-read-one --jar $evomasterJar
```

Repeat with `--arm business-four` for the other comparison. This launcher records
campaign-global diagnostics, not a final sequence-local score; exported tests
must be replayed with per-test reset before scoring. No EvoMaster run has yet
been validated on the user's installed binary by this change.

RESTler remains pending installation/version discovery and native runner
integration. It must use both named arms and their respective budgets, the same
contract and observer, with generated-sequence reset replay before scoring.
Do not claim RESTler support or results from this preparation alone. Bug 4 is
explicitly retained as its own required comparison for both baseline tools.

## Evidence

The compact ZIP includes per-case outcomes, budgets, observed actions, reset
boundaries and verdicts. Full native logs remain in the original campaign.
A nonzero native test exit can indicate a detected fault; inspect HTTP evidence
and the native log before assigning a fault. All-on pilot evidence supports
faults 3,4,5, with clean first violations; faults 1,2 were masked/unobserved.
