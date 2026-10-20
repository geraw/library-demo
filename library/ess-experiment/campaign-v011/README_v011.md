# v011: fixed Java suite with native runtime-value and response-result handling

Supersedes v010 for execution, not for historical evidence. v010 omitted native runtime-value evaluation and ignored returned ActuationSummary failures; its 201 creates were followed by unresolved @{USER...}/@{BOOK...} request bodies and 400 responses. Its apparent passes and timings are not valid business-suite results.

## Run

```powershell
& .\library\ess-experiment\campaign-v011\Invoke-ISSTA-Java-Fixed-v011.ps1 `
  -ReferenceCampaignPath 'D:\Yeshayahu\Temp\library-demo\library\ess-experiment\runs\provengo-sample10-split-v009-20261020-143852-69796'
```

Use the original v009 reference directory, not the v010 directory. JAR and frozen model/SUT hashes are checked against that reference. No tool upgrade or sampling is performed. Optional parameters: `-Java`, `-ProvengoJar`, `-CaseTimeoutSeconds` (120), `-ArmTimeoutSeconds` (7200).

## What changes

The repository's `src/StrictGuidedRun.java` remains untouched. `patch_runtime_v011.py` checks its normalized hash and creates a frozen runtime copy. Exactly four anchored execution edits:

1. Evaluate the selected event through Provengo's RuntimeValuesManager before actuation. The unevaluated event remains the input for symbolic scenario identity matching.
2. Check every native actuator's returned ActuationSummary; a failure is an error, even without a thrown exception. REST response callbacks remain in the native REST actuator.
3. Stop the scenario on evaluation or actuation error before counting the selected action as a reached step.
4. Create a fresh native RuntimeValuesManager/Rhino context for each scenario and clean actuators/context on exit.

All definitions before runScenario, including all 542 scenarios, names, steps, identity constraints, order, expectations and selection logic, are unchanged. The patched source and its hash are preserved. This is a Java adapter using Provengo runtime components; it is not the native CLI runner and is not a new semantic oracle.

## Mandatory transport preflight

Before running the catalog:

- Positive: a separate three-action infrastructure scenario creates a user, book and loan. It must pass natively and the HTTP evidence must show a 201 loan with actual server IDs matching request and response. No observer errors/verdicts are allowed.
- Negative: run the same infrastructure scenario against the healthy server using a separate disposable model copy where creation expects 202 instead of 201. It must fail natively with an unexpected-response-code error. This checks assertion plumbing, not a seeded SUT bug. The catalog's model and scenario definitions are never changed by this self-check.

These checks are excluded from catalog scores and arm timings and recorded separately in `transport_preflight_seconds`. A failed check aborts the campaign and preserves the evidence ZIP.

## Experiment and outputs

Control, bugs 1/2/3/5, then bug 4; all 542 fixed scenarios each. Managed reset and verified empty state before every case. Native failures and observer candidates remain separate; exclude cases failing the healthy control when interpreting mutants. No claim of bug discovery solely from a failed scenario. Nonzero process exit, incomplete catalog, missing boundaries, observer errors, unresolved request-body RTVs, or zero real loans in the control invalidate execution.

`results.json` includes actual successful loans/holds and GET/DELETE counts per arm. `timings.json` separates compilation, transport self-checks, control and both mutant arms. Completion marker: `JAVA_FIXED_V011_COMPLETE`. Partial runs still produce `V011_REVIEW_ZIP`.

## Scope

The existing catalog is primarily a strict reachability checker: it allows the target scenario actions, not all other enabled model events. In particular, model-side verification GETs are not automatically added between steps. Fixing actuation does not insert extra checks, extend scenarios or guarantee all five bugs will be reached/detected. Report actual HTTP coverage and native failure evidence. Some existing expected-blocked scenarios reflect older domain rules; a failure also present on the healthy control is not a seeded-bug detection.

Local validation used official Provengo-2026-01-10.uber.jar (SHA256 dda4be276ff517faa06b942d587cad2d342c66d83c9959f7eb3c6c77a8b2fc2b) solely to validate the adapter API and actual positive/negative transport checks. This differs from the study's pinned JAR; it is not substituted in the campaign and those preparation checks are not study results. The study machine repeats both mandatory checks with its own frozen JAR before the full catalog.
