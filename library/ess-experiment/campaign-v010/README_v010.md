# v010: existing fixed Java catalog, separate from sample timing

Run after v009, passing its output directory (not ZIP):

```powershell
& .\library\ess-experiment\campaign-v010\Invoke-ISSTA-Java-Fixed-v010.ps1 `
  -ReferenceCampaignPath 'D:\Yeshayahu\Temp\library-demo\library\ess-experiment\runs\provengo-sample10-split-v009-20261020-143852-69796'
```

Uses the reference campaign's frozen model, SUT and Provengo JAR; verifies reference hashes. Requires the matching JDK (the Java compiler module must be present). Optional `-Java` selects its java.exe. No sample command is executed and no scenarios are generated.

All 542 existing scenarios in `src/StrictGuidedRun.java` run in their original order: first control, then bugs 1,2,3,5, then bug 4. The catalog includes earlier sample-derived scenarios; it is an existing fixed suite, not an independently hand-authored suite. Its normalized source hash is pinned. The adapter invokes the existing private scenario method without changing its selection logic. It replaces the original main's hardcoded reset address with the managed observer's reset endpoint. State is reset and verified empty before each case. Each arm uses one JVM; the existing scenario method constructs a new model for each scenario. The source's unseeded internal selection is retained, so fixed scenarios do not imply fully deterministic execution.

`native.jsonl` records expected/reached states, failed action, caught actuator/listener errors, exceptions and time. Expected-blocked scenarios pass only when blocked with no recorded errors. A native failure alone is not a seeded-bug detection: a scenario must pass the control and its native log must substantiate the failure. `http.jsonl` and `results.json` preserve our independent semantic observations and first clean candidates separately. Candidate labels are not final scores. Source-caught exceptions are surfaced by the adapter instead of treating JVM exit zero as a passed test.

`timings.json` separates compilation, control, both mutant arms, and total wall time. No sampling cost is charged. Each case defaults to 120 seconds, each arm to 7200 seconds. Timeout aborts the arm rather than allowing a live case to overlap the next reset. Partial evidence is always packaged in `V010_REVIEW_ZIP`; absence of `JAVA_FIXED_V010_COMPLETE` means incomplete, not zero bugs.

Local validation: adapter compilation and mock catalog execution; Python syntax and CLI checks. Full compilation against the pinned Provengo JAR and the actual 542-case experiment must run on the study machine. These are preparation checks, not experimental results.
