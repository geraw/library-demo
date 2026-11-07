# Research checkpoint v001 — StrictGuidedRun on original and seeded Library SUTs

Date: 2026-10-19 (Asia/Jerusalem)
Status: PRELIMINARY / EXECUTION AND DETECTION NOT YET VERIFIED
Scope: new ISSTA-oriented controlled experiment; not an update to previously published FSE results.

## Research question

Can the current Library model and StrictGuidedRun runner distinguish the original service from the new five-mutation fixture, without changing the existing test scenarios?

## Artifact provenance

Repository: geraw/library-demo, branch master.
Seeded fixture release: 16de0974fa8430398b10b836147c1c4761e9c23c.
Runner: library/ess-experiment/src/StrictGuidedRun.java.
Model: library/provengo.
Original SUT: library/sut/sut.py.
Mutant: library/sut/sut_buggy_issta.py, intended ISSTA_BUGS=1,2,3,4,5.
Experiment contract: library/sut/library_openapi_issta.json.
Mutation documentation: library/sut/README_ISSTA_BUGS.md.

The supplied logs do not capture the user's local Git SHA, file hashes, JAR hash, effective mutation environment or listening-process identity. The release SHA above identifies the prepared artifact, not a verified byte-for-byte identity of the user's executed installation.

Environment reported during the session: Windows PowerShell, VS Code, Python virtual environment at C:\work\temp\library-demo\.venv; Provengo command at C:\Program Files\Provengo\Provengo Cli\provengo.bat. The CLI previously printed ef04cca/20250714-0453/master. Exact Java/Python versions and the JAR used in these two runs were not recorded in the supplied logs.

## Preserved evidence

The original uploaded log files remain preserved as supplied attachments. Hashes below refer to their original bytes, not a decoded or reformatted copy.

| Run | Evidence filename | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Original | strict-guided-original-20261019-172455.log | 3383492 | f30ecf097921de45f74c1fb5a2b8540c13bfef8ea3040e649d1dd734657428d3 |
| All mutations | strict-guided-buggy-all-20261019-173137.log | 3383454 | 5784b970d2e1c645a615a8809886615868410dd740095c15190e19138d6a4447 |

Library evidence identities for retrieval:
- Original: libfile_1d591a111cb48191961bfd2433797876.
- All mutations: libfile_f58f08cfb2108191a044ed4474ed10aa.

Recorded timestamp spans (first to last timestamped log message, NOT full campaign duration):
- Original: 17:24:56.631–17:25:50.286.
- All mutations: 17:31:37.888–17:33:27.977.

## Observed results

| Runner classification | Original | All mutations |
| --- | ---: | ---: |
| Scenario headers | 542 | 542 |
| Final summary entries | 542 | 542 |
| REACHED | 409 | 409 |
| OK: correctly blocked | 133 | 133 |
| STUCK | 0 | 0 |
| BUG: REACHED | 0 | 0 |
| [actuate exception] | 0 | 0 |
| [ERROR] | 0 | 0 |
| Reset warnings or reset non-200 notes | 0 | 0 |

All 133 expected-blocked results in the original log stop at the final requested scenario step; the longest declared scenario has 14 steps. The aggregate classification counts are identical between runs. This does not mean that the raw logs are identical, or prove that server states or HTTP responses were identical.

The mutant log records these reached action counts:
- createBook: 1231
- createUser: 1218
- createHold: 648
- deleteUser: 269
- deleteBook: 247
- deleteHold: 90
- createLoan: 76
- deleteLoan: 10

No book-read action appears among the recorded reached steps. There are no HTTP URLs, HTTP request/response records or status-code records in the mutant log. These observations concern logging; absence of HTTP log lines does NOT establish that no HTTP traffic occurred.

## Runner semantics and evidence limits

StrictGuidedRun guides the real model through predefined target action sequences with identity binding. REACHED measures reaching the requested action sequence. Expected BLOCKED outcomes measure the model's event eligibility, not a server rejection unless an actual request/response is separately recorded.

The runner's eventSelected listener calls actuators, catches actuator exceptions and continues. Its step counter is not itself a semantic state oracle. No such caught exceptions are present in either supplied log, but the code behavior prevents treating REACHED as a complete success certificate.

Small IDs printed in bindings are logical model IDs. The interface maps these to server-assigned IDs through runtime values; small printed IDs do not prove that the server was skipped or the wrong service ran.

Successful calls to /reset are not logged. The absence of reset warnings is consistent with successful reset calls, but does not establish which SUT build was listening, whether each target mutation was enabled, or whether every selected event was actuated.

## Five-mutation assessment

| ID | Intended fault | Current evidence / limitation | Verdict |
| --- | --- | --- | --- |
| 1 | Reject fourth distinct active book loan to one reader | Existing model restricts per-reader active loans; target prefix requires model alignment. No recorded HTTP-confirmed fourth-loan trigger. | NOT ESTABLISHED |
| 2 | Reject third borrowing of the same returned book by the same reader | A complete three-borrow/two-return trigger with successful HTTP bindings is not demonstrated in the supplied log. | NOT ESTABLISHED |
| 3 | Returning one book deletes another active loan of the same reader | Requires two active loans for one reader and an independent post-return state check; existing model restricts that setup. | NOT ESTABLISHED |
| 4 | GET existing book falsely returns 404 on first read | No book-read step is recorded. Target was not exercised by the recorded scenario steps. | NOT EXERCISED IN RECORDED STEPS |
| 5 | Deleting one hold deletes another hold of the same reader | Create/delete actions alone do not establish preservation or loss of the other hold. A state oracle is required. | NOT ESTABLISHED |

Do not report this run as 0/5 confirmed misses: eligibility and live execution have not yet been established. Do not report 542 passing SUT correctness tests, mutation equivalence, absence of bugs, autonomous discovery success, or superiority/inferiority to RESTler or EvoMaster.

## Contract and control confound

The experiment fixture without mutations is NOT the original sut.py:
- Original SUT limits a reader to one active loan.
- Experiment control permits multiple distinct active loans per reader.
- The companion contract explicitly clarifies unrestricted per-reader lending, repeat borrowing, exact deletion effects and existing-book reads.
- The original sparse contract remains unchanged; its GET-book operation permits both 200 and 404 without explicitly encoding the temporal creation/read obligation.
- Successful DELETE is 200 in the fixture and its companion contract; the original OpenAPI lists 204.

Therefore original-versus-mutant alone does not isolate mutation effects. A proper mutation contrast is the SAME experiment fixture with ISSTA_BUGS=none versus isolated mutations, with the same aligned model and observation rules.

## Separate ground-truth verification already completed

The deterministic Python fixture checks passed before release: five target scenarios each under control, isolated mutation and all-enabled configurations (15 combinations), plus reset-history cleanup. They use Flask's in-process test client. These are ground-truth/reproduction checks, not evidence that the Java runner or a testing tool autonomously found any mutation.

## Required next steps

1. Preserve these two logs unchanged; retain this checkpoint as the pre-instrumentation result.
2. Record local Git/file hashes, JAR hash, versions, server process/entry point and effective mutation configuration.
3. Verify actuator installation and actual outbound HTTP execution; record request method/path, resolved IDs, response status/body and per-scenario boundaries. Fail scenarios on actuator errors.
4. Establish the same fixture with ISSTA_BUGS=none as the proper control.
5. Align model rules with the experiment contract so legal multi-loan and repeated-loan prefixes can be generated. Record changes; do not overwrite the present baseline evidence.
6. Add contract-derived readback oracles for resource existence and deletion isolation. Keep semantic assertions separate from event reachability.
7. Run control and each isolated mutation, then all-enabled as a supplementary masking/interference check.
8. Report generated trigger reachability separately from oracle-confirmed detection. If directed trigger scripts are used, label them confirmation tests, not autonomous discoveries.
9. Supply the same public experiment contract, clean-state policy and external evidence rules to any future tool comparison.

## Suggested wording for a future report

"In a preliminary execution, the unchanged StrictGuidedRun suite produced identical aggregate classifications against the original Library service and the intended five-mutation fixture: 409 reachable sequences and 133 expected model-level blocks across 542 scenarios. No actuator exceptions were logged. The retained runner output did not establish HTTP-level execution, complete mutation-trigger coverage or post-operation semantic state checks. We therefore treat this result as an instrumentation and model-coverage checkpoint rather than a measured mutation-detection score."

## Change log

v001: Preserve observed preliminary results, evidence hashes, uncertainty, baseline confound and verification plan. No runner, model, SUT or contract changes are made by this checkpoint.
