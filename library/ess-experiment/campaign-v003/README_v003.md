# ISSTA campaign v003 — bounded sampling batches

## Observed failure and scope

On the home Windows installation, v002 observer verification passed (two tests,
63.411 s). The native smoke control also passed. Sampling 100 cases in one JVM
failed with Java heap space twice: 312.1034434 s with the initial settings and
187.4264678 s with JAVA_TOOL_OPTIONS=-Xmx4g confirmed in the log. Neither attempt
completed the official sample/replay campaign or produced an official budget.
Do not count either as a mutation finding or baseline detection failure.

Machine snapshot supplied during diagnosis: 31.83 GiB physical RAM, 7.83 GiB
free. A separate Vikunja run and VS Code work were active and must remain intact.
This patch does not stop unrelated processes or change machine-wide settings.

## Change from v002

Sample up to five scenarios per fresh JVM, at 500 events per scenario, until
100 retained cases (or explicitly 200) are collected. Each sampling JVM receives
-Xmx2g directly; the limit is per process, and processes run sequentially. This
bounds cross-case retention but is a mitigation, not a demonstrated root-cause
fix. A single batch can still fail; failure stops and preserves all evidence.
Batch size can be reduced explicitly to 1 using -BatchSize 1.

No scenario JSON is merged or rewritten. sample_manifest.json maps each global
case to its original batch file, SHA256 and 1-based run ID. Both control and
mutant replay use exactly that mapping. Canonical complete serialized scenarios
are deduplicated across files; this does not claim semantic deduplication when
metadata differs. sampling.json is updated after each batch and records all
batch commands and accumulated sampling time. Progress prints once per batch.

The five-instance snapshot, three pair-creation bound, business rules and
observer are unchanged from v002. Rejected requests can still repeat within
interface fuzzing loops; the 500-event limit remains. No fault-specific directed
scenario is injected. Generators remain analyst-authored, not OpenAPI-only.

The sampling budget includes every attempted batch command, including extra
batches for serialized duplicates and JVM startups. Official budget publication
still requires successful control and complete mutant HTTP execution. Input
hashes, server identity, state candidates and native outcomes remain separate.
The clock time can be substantial: batching does not reduce the work required
for 100 scenarios. No short runtime is promised.

## Windows command

```powershell
Set-Location 'D:\Yeshayahu\Temp\library-demo'
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\library\ess-experiment\campaign-v003\Invoke-ISSTA-Provengo-v003.ps1 -SampleSize 100
```

No server needs to be started manually. Ports 23243/23244 are owned by this
campaign; port 23242 and Vikunja services remain untouched. Old v002 run
folders are preserved. Output is runs/issta-v003-TIMESTAMP, with a review ZIP
only after completion. If a batch fails, send that batch's log and sampling.json.
Do not bypass control gates or interpret partial counts as a completed suite.

## Validation

Python syntax and batching orchestration tests passed: 100 cases map to 20
five-case native files with correct local indexes; failed batch does not publish
a budget. These tests mock native sampling and do not prove native sampler
compatibility or that 2 GiB will suffice. Observer HTTP and redirected-launcher
regressions are included unchanged under versioned names. Native execution at
home remains required.

## Subsequent stages

EvoMaster wrapper is included under v003 and consumes the measured budget.json.
Its native search output is campaign-global diagnostic evidence until generated
tests are replayed with individual resets. External semantic candidates are not
automatically native-tool discoveries or confirmed per-bug scores. RESTler is
still pending. See campaign-v002/README_v002.md for the observation design and
control limitations; v003 supersedes its single-JVM sampling procedure.
