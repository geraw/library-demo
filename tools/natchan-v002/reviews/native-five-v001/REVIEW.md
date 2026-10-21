# Focused audit of the five control-qualified native failures

Date: 2026-10-21. Source: work-machine fixed Java v011 review ZIP, SHA256 `7abd54bd10a41ac0491594ca679112140d92fbe0fb5553cccc04264d5e0d0895`.

## Result

Cases 80, 257, 260, 266 and 433 are five confirmed manifestations of the same seeded defect: **bug 5, deleting one hold removes every hold of its owner**. They are not five distinct bugs. This is an assessment of retained traces and source, not a new execution, and does not change the generic analyzer's conservative candidate labels.

In every case:

1. The recorded reset verifies an empty initial state. Two distinct holds of the same reader are successfully created, and their returned IDs match later paths.
2. The last independent holds readback before deletion contains both holds.
3. The first DELETE returns 200. The immediate independent GET /holds no longer contains either hold, although only one was targeted.
4. The preserved checker independently recomputes the first untainted STATE_MISMATCH at that delete; stored observer verdicts are not trusted.
5. A later tool DELETE addresses the unintended missing hold and receives 404. The fixed Java native report names deleteHold, records one actuator error, no listener errors and no top-level exception, and marks the expected-completion scenario failed.
6. The corresponding healthy case passes. Its first deletion preserves its other hold; the later deletion returns 200.

| Case | First delete step | Deleted target ID, buggy arm | Unintentionally deleted sibling ID | Native failure step |
|---|---:|---:|---:|---:|
| 80 | 6 | 851418 | 725855 | 7 |
| 257 | 6 | 998305 | 499873 | 9 |
| 260 | 8 | 796947 | 306903 | 9 |
| 266 | 6 | 438147 | 712936 | 10 |
| 433 | 6 | 476464 | 204718 | 8 |

## What Provengo detected

The native log reports: `AssertionFail: A REST call returned the unexpected response code. actual 404, expected: [200]`. This is a native HTTP response assertion failure propagated through the Java harness, not a Java VM/compiler crash. The trace shows why that 404 is erroneous: the tool had created the distinct hold and had never requested its deletion. The independent observer detects the underlying state damage earlier than the native failure.

The five native failing cases are a subset of the 22 external candidate cases for bug 5. The remaining 17 external cases do not have this same recorded native failure. This does not establish that all 22 have been individually audited to the same qualification level here.

## Source checks

- Archived `sut_buggy_issta.py:390-395`: with mutation 5 enabled, deletion filters by userId; healthy branch filters by requested hold ID. Other loan/book mutations do not implement this hold deletion.
- Archived `model/spec/js/interfaces.library.js:887-905`: valid deleteHold defaults to expected status 200 and uses the runtime hold ID.
- Archived `src/V011Actuation.java:21-24`: native notOk actuation result raises an exception carrying the original assertion remarks.
- Archived `src/V011GuidedSuiteHarness.java:67-77`: native pass requires expected reachability and zero actuator/listener errors. The `STUCK` wording after the failure does not on its own mean the model blocked the action; the native response assertion is decisive here.
- Exact source member hashes, native records, IDs, before/after readbacks and source line numbers are in `EVIDENCE_20261021.json`.

## Limits and reproduction

The two arms use the same fixed scenario catalog, but request fuzz variants and generated IDs differ. This audit establishes the identity/state/error chain independently within each arm and checks the mutation source; it is not an identical-byte paired replay or an isolated bug-5-only experiment. No SUT, generator or sample was run. No general claim about all Provengo configurations or other tools follows.

Repeat from the repository root:

```powershell
& .\.venv\Scripts\python.exe `
    .\tools\natchan-v002\reviews\native-five-v001\audit.py `
    --archive '.\library\ess-experiment\runs\java-fixed-split-v011-20261021-094721-5216-review.zip' `
    --output '.\library\ess-experiment\out\native-five-review-v001.json'
```

Choose a new output path if it exists. The script is a focused research audit with explicit case IDs, not an additional generic analyzer or a search aid supplied to testing tools. It verifies archive input hashes and requires every stated chain check to succeed.
