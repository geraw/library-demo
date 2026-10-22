# Library Controlled Mutation Study

Research report dated 22 October 2026

## Executive assessment

The Library study separates three questions: can a test workload reach the state
needed to expose a seeded defect, does the tool report a failure, and can an
independent state observer explain the defect? These are different measurements.
The five planted defects are reproducible ground truth. The generated ten-case
Provengo workloads exercised substantially different behavior from the fixed
542-scenario Java catalog. RESTler and EvoMaster reached the short existing-book
read defect but did not successfully create loans or holds in the reviewed neutral
contract pilots. This is evidence about these configurations and runs, not a
general limitation of either tool.

The strongest current result from the fixed catalog is hold deletion collateral
damage: 22 observer candidate cases, five additional native failures after healthy
control qualification, and no tool-issued GET requests in any catalog arm. The
absence of GETs makes the book-read defect unexercised by that catalog, not an
observed miss after reaching the trigger. The home and work configurations agree
on these outcomes despite different Provengo JAR hashes.

## 1 Installation and measurement boundary

The experiment lives in `geraw/library-demo`, branch `master`, under
`library/ess-experiment`. This report audits repository snapshot
`cdf56ab05f361d998929227c916ae13bbdb7219c` and the retained run archives listed in
the evidence manifest. Later report-publication commits do not change those
historical inputs. Implementation paths are configuration identifiers; a version
number alone is not a sufficient binary identity.

The service is a standalone in-memory Flask fixture. Java 21 and a locally
installed Provengo JAR support native sampling, replay and the Java adapter.
Python 3.10.8 was recorded at home; Python 3.12.10 at work. The work JDK reported
21.0.8 and included the compiler module. There is no database or Docker dependency
for this Library fixture. The managed observer uses localhost port 23243; the
earlier observer also used a backend on 23244. Port 23242 is the manual SUT port.
The later v006 observer dispatches to the original Flask application through its
WSGI test client while receiving genuine tool HTTP requests on the proxy.

The measurement boundary excludes observer-generated reads from tool request
counts. The observer performs collection readbacks and maintains an independent
ledger. It does not supply generated identities or recovery sequences to the
tools. Each Provengo case has a verified-empty reset and fresh JVM/runtime state.
The baseline pilot uses a fresh fixture per tool and a campaign-global case;
that boundary does not constitute per-generated-test confirmation.

The original Library service and models used an active-loan restriction that is
different from the mutation experiment's healthy behavior. Therefore the correct
control is `sut_buggy_issta.py` with `ISSTA_BUGS=none`, not the old service. The
experiment contract was subsequently cleaned in v007 without changing its 13
operation boundary. It has no mutation thresholds, prescribed sequences, OpenAPI
links, examples or RESTler annotations. The business model expresses the intended
workflow independently; v004 does not synthesize it from OpenAPI descriptions.

## 2 Seeded bugs and experimental purpose

These are deliberately planted deviations from declared experimental semantics,
not newly discovered production vulnerabilities. Resource identifiers must come
from server responses; their numeric values are not assumed to be sequential.

| ID | Mutation and trigger | Healthy behavior | Why included |
|---|---|---|---|
| 1 | Reject the fourth distinct active loan for one reader with 409 | Four distinct available books can all be borrowed | Requires aggregate history and a legal multi-resource prefix |
| 2 | Reject the third borrowing of the same reader/book pair after two returns | The third borrowing succeeds with 201 | Requires temporal history beyond current active state |
| 3 | Return one loan by filtering all loans of that reader | Only the addressed reader/book pair is removed | Tests collateral state loss despite a successful status |
| 4 | Compare a raw string book path identifier to stored integer identifiers | GET of an existing undeleted book returns 200 with matching identity | Isolates creation-to-read context; 404 is individually allowed in the contract |
| 5 | Delete one hold by filtering all holds belonging to its reader | Only the addressed hold is removed | Tests collateral deletion and later consequences |

The code markers `ISSTA-BUG-1` through `ISSTA-BUG-5` in
`library/sut/sut_buggy_issta.py` locate the mutations. Bug 4 fails on the first
existing-book read; it is not a read-counter mutation. Bug 2 history survives a
return but is cleared by reset. Book-level exclusivity and duplicate active-pair
checks remain healthy preconditions. The removed reader-level exclusivity is a
control definition, not another planted defect.

Bug 4 explains why context matters: an isolated 404 is legal for a missing book.
The violation requires successful creation, the returned identity and absence of
intervening deletion. Bugs 3 and 5 require before/after state evidence; their
successful DELETE status does not describe the lost non-target resource.

## 3 Correctness and acceptance checks

Ground-truth verification uses Flask's in-process client in
`library/sut/test_sut_buggy_issta.py`. It covers each of the five target scenarios
on the healthy fixture, its isolated mutation, and the all-enabled fixture: 15
configuration/scenario combinations. A second test verifies reset clears loan
history. The current audit reran both test methods successfully. This is fixture
verification and is not an autonomous tool-discovery score.

Campaign acceptance requires successful smoke/control execution, a successful
reset and four empty public collections at each case boundary, actual HTTP
requests with resolved identifiers, stable input/sample hashes and no observer
errors. A timeout is incomplete evidence. After the first semantic discrepancy,
later observer effects are tainted and are not independent clean discoveries.

The final Java route adds two mandatory transport checks before the catalog:
a three-action user/book/loan sequence must create a real 201 loan using server
IDs, and a disposable copy expecting 202 instead of 201 must fail natively.
Both checks passed in the reviewed home and work archives. They are excluded
from catalog scores and reported separately in timings.

The neutral contract's recorded development validation checked 22 real healthy
responses, schema structure and the unchanged operation boundary. Baseline
configuration checks verified automatic RESTler body/query dependency inference
and EvoMaster data-pool reuse; no hand-written dependencies were added. These
checks support the invocation used; they are not an exhaustive search for the
best settings of every tool version.

## 4 Execution campaigns and mutation activation

The table lists retained completed campaigns individually. Compact-archive counts
are archived observer/native summaries; they are not presented as newly recomputed
raw-oracle results. Additional preparation-only and non-qualifying historical
executions are catalogued separately from research scores.

| Campaign | Configuration | Cases or budget | Observed outcome |
|---|---|---|---|
| v004 smoke | Healthy business model | 1 | Native exit 0; 100 tool requests |
| v004 control | Healthy business model | Original sample 10 | 10 successful cases; 2,328 tool requests; no semantic candidates |
| v004 all enabled | Bugs 1,2,3,4,5 | Same 10 | 10 nonzero exits; first clean cases: bug 4 in 7, bug 5 in 2, bug 3 in 1 |
| v004 isolated 1 | Bug 1 only | Same 10 | 4 first-clean rejection candidates; 4 native failures |
| v004 isolated 2 | Bug 2 only | Same 10 | 10 first-clean rejection candidates; 10 native failures |
| v004 isolated 3 | Bug 3 only | Same 10 | 10 first-clean loan-state mismatches; 10 native failures |
| v004 isolated 4 | Bug 4 only | Same 10 | 10 existing-book read discrepancies; 10 native failures |
| v004 isolated 5 | Bug 5 only | Same 10 | 10 first-clean hold-state mismatches; 10 native failures |
| v005 business four | Bugs 1,2,3,5 | Reuse original 10 | First clean: 6 hold-loss, 2 loan-loss, 2 loan rejection candidates |
| v005 book read one | Bug 4 | Reuse original 10 | 10 existing-book read discrepancies |
| v007 control baseline | No bugs | RESTler 60 s then EvoMaster 60 s | Neither created a loan or hold |
| v008 mutant baseline | All five | RESTler 600 s then EvoMaster 600 s | Existing-book context reached; no successful loan/hold creation |
| v009 fresh sample | Healthy then 4+1 | New sample 10 | Separate result and timing experiment, detailed below |
| v011 home fixed catalog | Healthy then 4+1 | 542 per arm | Hold-loss evidence; no catalog GETs |
| v012 work launcher | Restored inputs, local JAR, v011 executor | 542 per arm | Same catalog outcomes as home, distinct binary configuration |

The isolated runs show trigger reachability for all five defects. They do not
mean one all-enabled run found all five. Splitting bug 4 prevents its short-prefix
failure from masking later business behavior. The four remaining mutations may
still mask each other. Native fail-fast behavior was retained.

The v005 arm budgets were 485 seconds for business-four and 517 seconds for
book-read-one: each separately includes the original 54.321-second generation
charge plus that arm's replay, rounded up. These are declared comparison budgets,
not evidence that matching RESTler/EvoMaster 4+1 searches were completed. The
reviewed final baseline mutant pilot is all-five v008, not that official paired
budget experiment.

## 5 Provengo sample of ten and measured cost

V009 copies the frozen business model and SUT, uses the neutral v007 contract,
creates ten fresh native samples in two batches of five, validates those samples
on the healthy fixture, and replays exactly the same samples in the two mutant
arms. The event bound is 500. No ranking or fault-directed selection is added.

| Timing component | Seconds |
|---|---:|
| Preparation | 0.506 |
| Native sampling | 41.781 |
| Healthy validation | 641.014 |
| Business-four replay | 481.780 |
| Book-read-one replay | 488.346 |
| Sampling plus business-four | 523.561 |
| Sampling plus book-read-one | 530.127 |
| Sampling once plus both mutant replays | 1,011.907 |
| Total elapsed before packaging | 1,672.707 |

Do not add the two standalone arm totals as actual combined cost: they each
include generation. The combined research measure is approximately 16 minutes
52 seconds; the full workflow including healthy validation is approximately
27 minutes 53 seconds. Model authoring is not measured by this table.

The fresh business-four sample produced first-clean candidates for bug 1 in one
case, bug 3 in four cases and bug 5 in five cases. Bug 2 was not a first-clean
finding in this sample. The book-read arm produced ten bug-4 observations. Both
mutant arms had ten native nonzero exits. These are case observations, not twenty
independent bugs. They must not be pooled with the original v004 sample.

## 6 Provengo and the fixed Java tester

The fixed tester is a Java adapter around Provengo's behavioral-programming and
actuation components. It guides the model through an existing catalog; it is
neither a newly sampled workload nor an independent JUnit baseline. The catalog
contains 542 scenarios, including historically sample-derived scenarios. No
sample is generated during v011 or v012 execution.

The v011 execution evaluates runtime values before actuation, checks native
ActuationSummary failures, stops on failed evaluation/actuation and creates a
fresh runtime context per scenario. It preserves the existing catalog definitions.
The original StrictGuidedRun source remains untouched. Reachability alone is
not accepted as proof of correct HTTP effects.

| Arm | Native failures | Successful loans | Successful holds | Tool GETs | Tool DELETEs |
|---|---:|---:|---:|---:|---:|
| Healthy control | 2 | 78 | 648 | 0 | 616 |
| Bugs 1,2,3,5 | 7 | 78 | 648 | 0 | 615 |
| Bug 4 | 2 | 78 | 648 | 0 | 616 |

Cases 73 and 77 fail in the healthy control and are excluded from mutation
attribution. The five additional failing business-four cases are 80, 257, 260,
266 and 433. The observer identifies 22 clean hold-loss candidate cases, including
those five. Later delete-404 failures can be consequences of a previously lost
hold; they are not additional seeded bugs. Bug 4 has no healthy-eligible native
failure and no tool GET trigger. The catalog therefore does not evaluate that
bug's detection capability.

Both home and work archives have these outcomes. Home compilation/preflight/
control/business-four/book-read timings are 4.959/13.762/54.333/51.885/56.195 s;
total before packaging is 196.155 s. Work timings are
3.324/13.792/55.964/54.718/54.901 s; total 198.551 s. The two mutant arms cost
108.080 s at home and 109.619 s at work. These times exclude sampling because the
catalog already exists. They are not comparable to sample-generation time as
though scenario count and behavior were the same.

## 7 EvoMaster and RESTler comparison

The measured existing installations are EvoMaster 5.0.2 and the archived RESTler
binary identified by its SHA256 in the engineering report. The v006 optional
managed installer instead pins EvoMaster 6.2.0 and an immutable RESTler source
commit; selecting it defines a new configuration, not the historical run.

| Retained run | Tool | Search setting | Tool requests | Successful resource creates | Successful loan or hold creates |
|---|---|---:|---:|---:|---:|
| v006 completed selective replay | EvoMaster | 600 s | 83,655 | 24,649 | 0 |
| v007 healthy control | RESTler | 60 s | 1,712 | 288 | 0 |
| v007 healthy control | EvoMaster | 60 s | 13,277 | 3,912 | 0 |
| v008 all five | RESTler | 600 s | 7,634 | 1,635 | 0 |
| v008 all five | EvoMaster | 600 s | 74,168 | 21,987 | 0 |

V008 process wall times are 608.533 s for RESTler and 604.031 s for EvoMaster;
compilation/startup/finalization are outside the 600-second engine setting.
RESTler uses automatic inference, bfs-cheap and seed 1. Its generated grammar
still uses fuzzable loan/hold userId/bookId numbers and an incorrect inferred
loan-return dependency. EvoMaster uses black-box mode, seed 1 and its native
response-data pool. No manual dependency map, seeded objects or prescribed
sequences were supplied to either tool.

The independent observer can detect the existing-book read problem when these
tools create a book and GET it. A native response-code checker can accept the
same 404 because the endpoint documents it. The interpretation is contextual;
an external observer finding does not become a native tool finding. Native
generated assertions and reports must be inspected separately. Very-long-integer
500s are outside the five planted mutations. A RESTler results-analyzer error is
also not an application defect or proof that search never ran.

## 8 Current status and research conclusions

The updated Natchan engine was used through the preserved Library product
gateway, rather than applying Gitea signatures to Library traffic. The separate
machine appendix records the exact reanalysis results and incomplete datasets.
The recent raw-sequence PR/C11 additions target Gitea and do not alter Library
ground truth. New classification does not itself create a new Library defect.

The central conclusions are workload coverage and oracle context. Isolated
mutation experiments demonstrate reachability of all planted triggers. The
all-enabled and split samples reveal masking. The fixed Java catalog exercises
many actions rapidly but lacks book-detail reads and finds a narrower defect
family. The neutral baseline tools perform many requests yet fail to establish
the loan/hold relationships needed for four business mutations. This is why
request count, case count and reached actions cannot substitute for trigger and
semantic coverage.

The present evidence does not support a universal claim that RESTler or
EvoMaster cannot detect these problems. It also does not support a final fair
4+1 cross-tool score with identical per-test replay and sampling-adjusted budgets.
That comparison remains a separate experiment. Further work should preserve
the current configurations, add clearly named alternative configurations if
desired, and measure native reports separately from common observer findings.

## Current analyzer reanalysis

The current audit completed six full archive datasets through the Library
product gateway and the current common catalog. It did not consume historical
candidate labels as classification proof and sent no new HTTP requests.

| Dataset | Newly recomputed clean observations | Known seeded classes matched |
|---|---:|---|
| Home fixed Java v011 | 22 | Bug 5 in 22 cases |
| Work fixed Java via v012 | 22 | Bug 5 in 22 cases |
| Fresh sample v009 | 20 | Bug 1 in 1 case, bug 3 in 4, bug 5 in 5, bug 4 in 10 |
| Neutral v007 controls | 0 | None in either tool |
| All-five v008 baselines | 2 | Bug 4 context in each tool's campaign-global trace |
| Completed selective v006 EvoMaster | 1 | Bug 4 context in its campaign-global trace |

There are 67 external observation occurrences across these datasets, not 67
independent bugs. Home/work repetitions and generic/product labels overlap.
The current common classifier reproduces four planted classes from the full
sample evidence; the archived isolated bug-2 run is additional historical
coverage, not a new raw-oracle reanalysis result.

The useful new synthesis is that 17 of the 22 clean hold-loss observations per
fixed-catalog configuration do not produce an additional native failing case.
For the other five, the adapter traces later DELETE-404 consequences back to
holds already removed by the earlier deletion. It keeps those consequences
separate from the initiating defect. That explains the gap between five added
native failures and 22 contextual observations without inventing additional bugs.
The three baseline bug-4 observations are campaign-global first-clean witnesses;
they are not three independently replayed generated tests or native tool reports.
No new mutation family was discovered by upgrading the analyzer.

## Evidence and exclusion policy

The accompanying evidence manifest identifies archives by SHA256 and exact JSON
members. Source code, installed binaries, sampled artifacts, native reports,
observer requests and independent classifications have distinct roles. Compact
actions/summaries lack the raw oracle reads needed for full independent state
reconstruction. They support the historical run inventory but not a claim of a
newly recomputed semantic score. No trial-and-error narrative is included.

The pre-instrumentation fixed-runner logs and v010 execution are retained as
non-scoring historical material. They are not included in mutation-detection
totals. This qualification is necessary even when their aggregate outputs look
successful. The investigator profile has an implementation but no matching
completed run archive was located in the reviewed evidence set.
