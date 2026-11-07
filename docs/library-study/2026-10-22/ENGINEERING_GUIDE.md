# Library Study Reproduction Guide

Engineering guide dated 22 October 2026

## Purpose and configuration policy

This guide mirrors the research report and gives executable paths, input
requirements, acceptance gates and evidence locations. It covers regeneration
of experiments and offline reanalysis. Exact replay of a historical sample
additionally requires that sample's original archive and matching binary hashes.
Git contains source and a small frozen-input bundle, not the native tool binaries
or every historical sample. A fresh sample is a new experiment even if it contains
ten cases and uses the same model.

The audited code snapshot before report publication is
`cdf56ab05f361d998929227c916ae13bbdb7219c` in `geraw/library-demo`.
The machine-readable evidence manifest pins archive bytes. Use a separate clean
checkout for a pinned source revision; do not reset an existing working tree or
delete untracked environments and results. Run campaigns sequentially because
they share managed ports. The Library study does not require Docker.

## 1 Installation and measurement boundary

### Prepare a clean Windows checkout

```powershell
git clone https://github.com/geraw/library-demo.git C:\work\library-study
if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
Set-Location C:\work\library-study
git rev-parse HEAD
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install flask
java -version
java --list-modules | Select-String '^jdk.compiler@'
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
```

Install the licensed/local Provengo distribution separately. The documented
default is `C:\Program Files\Provengo\Provengo Cli\Provengo.uber.jar`.
Specify `-ProvengoJar` where supported rather than renaming a binary. Record:

```powershell
$jar = 'C:\Program Files\Provengo\Provengo Cli\Provengo.uber.jar'
Get-FileHash -LiteralPath $jar -Algorithm SHA256
& .\.venv\Scripts\python.exe --version
git rev-parse HEAD
& .\.venv\Scripts\python.exe -m pip freeze
```

Flask is the direct requirement; Werkzeug and its dependencies are resolved by
installation. Historical Python/Flask resolution is not reconstructed merely by
installing today's package. Capture `pip freeze` for the new run. No exact Flask
lockfile was present in the reviewed historical evidence. Matching Python major
version is weaker than matching the complete runtime.

### Recorded binary identities

| Input | Recorded SHA256 or version |
|---|---|
| Home study Provengo JAR | e4e9ec6914d8ceb0e2fb91d2322472d8208d9c01b735412dbe4db3cacfd392cc |
| Work study Provengo JAR | 5a8140409e200fb752a97b7317e1b259e668383d9d42814063b3365f0044981b |
| Local API-validation JAR only | dda4be276ff517faa06b942d587cad2d342c66d83c9959f7eb3c6c77a8b2fc2b |
| Recorded EvoMaster | 5.0.2; 11fe832bba91883d6936b3e42fdea6a0e8c9a2b9c4f80bd7cdd043f1a2c86d4c |
| Recorded RESTler executable | 53d9c042539474823e39cd486bf4e0e877459c48a91e18d75cdbc5c955bed820 |
| Frozen SUT in final campaigns | 91b5cbe404afbd9906ab5dd8999710d38257d7d6fc2d8a40b8098b02ef66cb7f |
| Neutral v007 campaign contract | e63f6c2f2f070f7225dd625a019da39fd9038bea0a660225fd3c420acefffae3 |

The validation-only JAR was not substituted into the historical home or work
campaigns. A different JAR is a separately recorded configuration. The managed
v006 installer pins EvoMaster 6.2.0 and RESTler source commit
`6d984deedbc54aad957fa3da0c7e9e5df23a2aee`; this is an alternative installation,
not the observed 5.0.2/legacy executable pair. Rebuilding the RESTler source need
not reproduce the old executable hash. Do not assign that source commit to the
old binary without independent build provenance.

### Service boundaries

Use manual port 23242 only for a manually launched SUT. Managed campaigns own
23243, and older transports also own 23244. Their ownership/health checks fail
if ports are occupied rather than killing an unrelated process. Observer GETs
are logged separately from tool traffic. Reset operations are harness actions.

## 2 Seeded bugs and experimental purpose

`library/sut/sut_buggy_issta.py` is the experiment fixture. Its switches are
`none`, `1`, `2`, `3`, `4`, `5` and comma-separated combinations. Default is all
five. The markers `ISSTA-BUG-1` through `ISSTA-BUG-5` locate the implementations.
The research report explains their semantic contracts and minimal prefixes.

Manual smoke start in a dedicated terminal:

```powershell
$env:ISSTA_BUGS = 'none'
& .\.venv\Scripts\python.exe .\library\sut\sut_buggy_issta.py
```

Restart after changing the mutation set. In another terminal, this harness reset
clears all collections, ID pools and pair history:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:23242/reset `
    -ContentType 'application/json' -Body '{}'
```

Do not assume small IDs. POST responses provide IDs for subsequent loan/hold
operations. Stop the manual process with Ctrl+C when done. Managed campaigns
launch and stop their own fixtures; do not point them at the manual server.

The contract for current clean baselines is
`library/ess-experiment/campaign-v007/library_openapi_v007.json`. Campaign code
copies it and sets the managed server URL. Its resulting file hash is listed
above. Old experiment descriptions must not be merged into a neutral-contract
result. Model JS, input JSON and runtime-value handling are separately versioned.

## 3 Correctness and acceptance checks

Verify the fixture without a running HTTP service:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover `
    -s .\library\sut -p test_sut_buggy_issta.py -v
```

Expect two unittest methods to pass. The mutation method contains 15
configuration/scenario combinations. This is a ground-truth check, not a discovery
campaign. Capture the console result with the source revision.

For each live case, inspect `http.jsonl` for a boundary record with
`empty_verified=true` and zero users/books/loans/holds. Tool records, oracle
records and verdict records have distinct roles. The independent evaluator must
use immutable raw readbacks rather than treating saved candidate labels as proof.
Only the first clean discrepancy per case supports clean-prefix attribution.

V011/v012 automatically run positive and negative transport self-checks before
the fixed catalog. Inspect `preflight_completed.json`: real loan creation must
be true and the intentionally wrong expected status must fail natively. Abort
before scoring if either fails. Nonzero case exits are retained for analysis;
an incomplete campaign or observer exception is not a clean test result.

## 4 Execution campaigns and mutation activation

### Prepare or generate the business workload

```powershell
& .\library\ess-experiment\campaign-v004\Prepare-ISSTA-Models-v004.ps1
& .\library\ess-experiment\campaign-v004\Invoke-ISSTA-Provengo-v004.ps1 `
    -Profile business -SampleSize 10 -ProvengoJar $jar
```

The second command creates a new `library\ess-experiment\runs\issta-business-v004-*`
folder containing the prepared model, SUT, contract, manifest, sample batches,
healthy smoke and control results. Do not substitute the prepared-models-only
folder for a completed reference campaign. Define `$campaign` to the full path
printed by that invocation, after checking its accepted control results.

For a new all-enabled v004 campaign, pass `-IncludeMutant` during generation:

```powershell
& .\library\ess-experiment\campaign-v004\Invoke-ISSTA-Provengo-v004.ps1 `
    -Profile business -SampleSize 10 -IncludeMutant -ProvengoJar $jar
```

This creates a new sample and is not a replay of the historical 19 October sample.
The optional investigator profile is separate: replace `business` with
`investigator`. Its robustness results must not enter the five-business-bug score.
No completed investigator archive was located in this audit.

### Replay one mutation at a time or all five on an existing accepted sample

The accompanying `replay_mutation_set.py` documentation helper calls the existing
v004 replay code through v005's reference validation. It adds no sequences or
assertions. Run from the checkout root:

```powershell
& .\.venv\Scripts\python.exe `
    .\docs\library-study\2026-10-22\replay_mutation_set.py `
    --reference-campaign $campaign --bugs 1
```

Repeat with `--bugs 2`, `3`, `4`, `5`, or `1,2,3,4,5`. It verifies the accepted
control, model/SUT manifests, JAR and sample batch hashes, then writes a unique
output directory. It retains the v004 observer/transport for this route. This is
the route for isolated attribution, not a modification to the v009 timed protocol.
Runtime/native validation of this documentation helper still requires the local
JAR; no new native campaign was executed during report preparation.

The legacy replay reference includes sample source paths in `control/runs.json`.
Moving the archive can break those paths. Restore the original directory layout
or generate a new accepted reference; do not silently change paths and call the
result byte-identical. The compact historical archives do not contain the original
sample batches and are insufficient for exact native replay.

### Replay the original 4 plus 1 protocol

```powershell
& .\library\ess-experiment\campaign-v005\Invoke-ISSTA-Split-v005.ps1 `
    -CampaignPath $campaign
```

The script reuses the accepted reference sample, runs bugs 1/2/3/5 and then bug 4,
and writes `split-v005-business-four` and `split-v005-book-read-one`. Each arm's
`budget.json` includes sampling plus that arm's execution and an integer search
budget. It does not regenerate samples or rerun control. Completed arms are
skipped on restart; incomplete directories are preserved for inspection.

The research report inventories the completed v004 smoke/control/all-enabled,
five isolated runs, v005 two arms, v007 two controls, v008 two searches, v009 three
replays and the home/work fixed catalogs individually. The evidence manifest
distinguishes full logs from compact historical summaries.

## 5 Provengo sample of ten and measured cost

To generate a new sample from an already frozen reference and run the final timed
protocol, define `$campaign` as above, then:

```powershell
& .\library\ess-experiment\campaign-v009\Invoke-ISSTA-Sample10-Split-v009.ps1 `
    -ReferenceCampaignPath $campaign -ProvengoJar $jar
```

The JAR must match the reference hash. Two native batches of five, a 500-event
bound, healthy validation and both mutant arms are automatic. No fault-directed
ranking is added. Save the printed `V009_REVIEW_ZIP` and the complete run folder.
The full historical archive is about 230 MB compressed and includes large sample
members; compact summaries cannot replace it for exact replay.

Inspect `sampling.json`, `sample_manifest.json`, `timings.json`, `results.json`,
each arm's `runs.json`, actual `http.jsonl`, readable test files and native logs.
Verify sample hashes before comparing arms. Charge sampling once in the combined
metric. The reviewed historical values are 41.781 s sampling, 481.780 s
business-four replay and 488.346 s book-read replay. Healthy validation is
641.014 s and is separately reported.

## 6 Provengo and the fixed Java tester

### Git-only continuation with local Provengo

This is the simplest route on a new work computer:

```powershell
& .\library\ess-experiment\campaign-v012\Invoke-ISSTA-Work-v012.ps1 `
    -ProvengoJar $jar
```

V012 restores 18 files from `frozen_inputs_v012.json`, verifies each file hash,
writes a new `work-reference-v012-*` under runs and invokes v011. It bundles no
JAR and installs no binaries. `-PrepareOnly` performs only restoration. The new
environment records original/current JAR hashes and whether they match.

V011 compiles the adapter and patched runtime, runs both transport gates, then
all 542 unchanged scenarios against control, bugs 1/2/3/5 and bug 4. Default case
and arm limits are 120 and 7200 seconds. The expected reviewed result is native
failure counts 2/7/2; read the actual run, do not hard-code that as acceptance.
`JAVA_FIXED_V011_COMPLETE` and `WORK_RUN_V012_COMPLETE` mean orchestration
completion, not 542 passing correctness tests or discovery of every mutation.

### Pinned-reference route

If the original v009 reference directory and matching JAR are retained:

```powershell
& .\library\ess-experiment\campaign-v011\Invoke-ISSTA-Java-Fixed-v011.ps1 `
    -ReferenceCampaignPath $reference -ProvengoJar $jar
```

The fixed runner source is `library/ess-experiment/src/StrictGuidedRun.java`.
`patch_runtime_v011.py` validates its normalized hash
`04084199740dedaeacade4efb4310ec8525181ae2de6b8a6376887146b85f514`.
The recorded patched source hash is
`d0d926677b385dce4515eed0bbdaf0eeea10ce376aa1acb9fc8fd4bfe49582bc`.
Do not edit catalog scenarios while comparing this experiment. V010 is not an
accepted substitute for v011 actuation.

Read `results.json` and `timings.json`, plus `native.jsonl`, `http.jsonl` and
`server_identity.json` in each arm. Exclude control failures 73 and 77 for this
reviewed catalog. Native failures 80/257/260/266/433 overlap five of the 22 hold-loss
observer candidates. The catalog records zero tool GETs. Observer GETs must not
be mistaken for tool coverage of bug 4.

## 7 EvoMaster and RESTler comparison

### Neutral-contract healthy pilot

```powershell
& .\library\ess-experiment\campaign-v007\Invoke-ISSTA-Contract-Pilot-v007.ps1 `
    -CampaignPath $campaign -Seconds 60 `
    -EvoMasterJar 'C:\path\to\evomaster.jar' `
    -RestlerPath 'C:\path\to\Restler.exe'
```

This copies the neutral contract and SUT into a new control directory. Record
the printed path as `$neutralControl`. Both tools get the same numeric budget,
mutations are disabled, and RESTler runs first. The absence of successful
loan/hold creation is a coverage result and must not be repaired with a manual
dependency map inside this frozen configuration.

### All-five mutant pilot

```powershell
& .\library\ess-experiment\campaign-v008\Invoke-ISSTA-Mutants-v008.ps1 `
    -ControlCampaignPath $neutralControl
```

V008 requires the successful v007 input/binary provenance and frozen neutral
contract. It runs RESTler then EvoMaster for 600 seconds each. Each tool gets
fresh empty state. Search is not stopped by the external observer's findings.
Its official sequence-local score remains unassigned until generated sequences
have an appropriate reset/control replay.

### Optional local installation

V006/v007 discover existing tools and can install missing ones locally under
`%LOCALAPPDATA%\ISSTA-tools-v006`. `-InstallLocalTools` deliberately bypasses old
installations and selects the managed versions. Installation requires network
access for release downloads, .NET restore and Python dependencies. It does not
require administrator installation or permanent PATH changes. Record the actual
manifest; installation time is not search time. Selecting this option does not
reproduce the historical binary identities listed in section 1.

The earlier completed selective v006 EvoMaster rerun can be invoked with
`Invoke-ISSTA-Baselines-v006.ps1 -CampaignPath $campaign -Tools evomaster
-PreviousPilot $previousPilot`, using PowerShell line continuation as needed.
Keep its older contract and transport provenance separate from v007/v008 results.

### Offline analysis

The new `tools/natchan-v014/library_study_audit.py` consumes a JSON manifest of
archive paths and gateway layouts. See the accompanying audit manifest. Execute
from the repository root containing the published analyzer update:

```powershell
& .\.venv\Scripts\python.exe .\tools\natchan-v014\library_study_audit.py `
    --manifest .\docs\library-study\2026-10-22\analysis-manifest.json `
    --output .\library\ess-experiment\out\library-audit-new
```

Change only manifest archive paths to your restored locations, then retain that
manifest with results. The output directory must be new. The tool is offline;
it does not start services, execute saved tests or contact a SUT. Archive hashes
and exact members are recorded. Explicit limits accommodate the large v009 sample
members: 512 MiB/member, 2 GiB cumulative and 300,000 events. Unsupported or partial
evidence remains incomplete rather than being converted into a zero score.

For the work v011-layout archive alone, the established command is also valid:

```powershell
& .\.venv\Scripts\python.exe .\tools\natchan-v002\analyze.py `
    --archive $reviewZip --library-v011 --output .\new-analysis.json
```

The v002 gateway and preserved semantic checker are reused by the latest common
classifier; their earlier version numbers do not make them obsolete runtime
dependencies. Native failures, external observations and known-bug matches
remain separate.

## 8 Current status and maintenance decisions

Keep campaigns v004/v005/v006/v007/v008/v009/v011/v012 while their workflows are
supported. V012 calls v011; v011 imports v009; v009 imports v006 and uses v007's
contract; v006 imports v004. V005 imports v004. Removing an old-looking folder in
that chain breaks current commands. Keep original model inputs and the fixed
Java source because preparation and hash-anchored patching depend on them.

Campaigns v001/v002/v003 and v010 are candidates for archival removal from the
active checkout, not immediate evidence destruction. Code-reference search found
only their own/historical documentation references, and no dependency from the
retained runtime chain. V010 is explicitly superseded. If exact historical
non-scoring executions remain in scope, keep an immutable tag and manifests
before removing active files. No deletion is part of this report.

Do not delete `tools/natchan-v002` or v003: they are actual product/tool gateway
dependencies. Do not delete compact evidence merely because it cannot support
full reanalysis: it preserves the historical run inventory. Generated products,
caches and local run outputs are separate cleanup candidates only after checksum
verified archival backup; they must not be confused with tracked source versions.

## Repository location and evidence access

Recommended location is `docs/library-study/2026-10-22/`, with a stable index at
`docs/library-study/README.md`. Keep these Markdown sources beside matching Word
exports, the run/evidence manifest and the cleanup audit. Keep large original
archives in durable artifact storage referenced by filename and SHA256; do not
commit hundreds of megabytes of sampled/generated output to ordinary Git.

Repository access alone is sufficient for the current v012 fixed-catalog route
after installing dependencies and a compatible local JAR. It is not sufficient
for byte-identical historical v004 or v009 replay without the archived samples,
nor for historical baseline binaries absent from Git. Mark this explicitly when
handing the project to another engineer.
