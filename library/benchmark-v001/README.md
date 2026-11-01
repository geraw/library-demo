# Library mutation benchmark v001

## Git workflow: home and work

Use the existing `library-demo` checkout on `master` on both machines. Work path: `C:\work\temp\library-demo`; home path: `D:\Yeshayahu\Temp\library-demo`. Run from the existing repository folder:

```powershell
git pull --ff-only origin master
git rev-parse HEAD
& .\library\benchmark-v001\Setup-Library-Benchmark-v001.ps1 -InstallNativeTools
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 -Configuration all -Seconds 60 -Seed 1
```

Use Git for updates on both computers. The same source commit must be used for comparisons. Tool paths and `tools.local.json` are local to each computer and ignored by Git, as are environments and run results. Supply the installed Provengo path with `-ProvengoJar` when needed. If fast-forward fails or local changes conflict, preserve them and inspect Git status; do not reset or delete results.

## Scope

This is a new isolated environment. It does not replace the operational SUT, the existing model, v008, previous campaigns, or the fixed Java scenario catalog. Source: `library/sut/sut.py` at commit `30d9b7cb3ec2a151a49633513a5ffa8c6eff6175`. Four successful DELETE handlers now return **204 with an empty body**, matching the original OpenAPI. The original rule of one active loan per user AND per book is retained. Multiple holds remain allowed.

### Exactly four configurations

1. `evomaster`: native black-box EvoMaster search.
2. `restler`: native RESTler compilation and fuzzing.
3. `provengo-sample10`: **ten native sampled scenarios**, generated in ten size-one JVM batches to bound sampling memory, then replayed unchanged on every arm. Sample count is 10, not 100. Duplicate samples are retained and disclosed. Default maximum length: 500.
4. `provengo-java`: the **existing 542-scenario StrictGuidedRun catalog**, executed through the repaired v011 native actuation plumbing. No new scenario definitions are inserted. The original catalog prefix is byte-identical. Only its runtime execution plumbing is patched; the wrapper supplies authenticated case resets. Each scenario gets an empty SUT. This is the existing guided catalog, NOT ten new tests written directly in Java and NOT a newly sampled suite.

The source model is a copy of `library/provengo`, with five users/books, DELETE expectations/event classifiers aligned to 204, and the local `pvg` shadow renamed so callbacks keep the real runtime-value store. No one-loan rule is removed. A model metadata callback absent from the copied inputs is disabled. The fixed Java catalog may include cases unreachable under the strict original baseline: baseline failures are retained, not silently repaired or scored as mutant discoveries. The summary exposes baseline-eligible cases and native failures on those cases.

## Six independent mutants

| ID | Fault | Baseline expectation | Required witness |
|---|---|---|---|
| B1 | Created book is falsely reported missing by raw-string/integer ID mismatch | Existing book read returns 200 | Successful creation, no intervening deletion, GET 404 |
| B2 | Book deletion acknowledges 204 without removing the book | Deleted book is unavailable | Successful deletion followed by GET 200 |
| B3 | Rejected loan persists a candidate row | Rejection leaves business state unchanged | Failed create, subsequent loan readback shows the new pair |
| B4 | Compound loan filters use OR instead of AND | Every supplied filter is satisfied | Response contains a nonmatching loan |
| B5 | Deleting one hold removes another hold of the owner | Only the selected hold is removed | Previously created, undeleted second hold disappears |
| B6 | Loan creation dereferences a missing book | Missing book is rejected with 400 | Known deleted book, later loan request returns 500 |

Default campaign: clean baseline (`none`) plus B1 through B6 **in isolation** = 7 arms x 4 configurations = 28 cells. Combined mutants are not a default research arm because masking complicates attribution. `LIBRARY_MUTATIONS` defaults to `none`; only the managed mutant process receives a switch.

## Two separate evaluators on the same captured evidence

- `oracle.json`: an independent, product-specific **passive** Library oracle. It reads actual tool-origin HTTP history and required readbacks; it does not inspect mutant switches, SUT lists or activation logs. No extra oracle requests are inserted into generation. Missing readbacks produce `NOT_EVALUATED`, not a successful negative result.
- `natchan-result/`: the **independent contract-only Natchan 009-dev.4** from branch `natchan-box-v009`, commit `e4f97dc81b0997578593c67c90aec123a7a87c16`, bundled unchanged. It receives only whitelisted raw HTTP exchanges, the common OpenAPI, and knowledge derived/frozen before campaign evidence. It does NOT receive oracle findings, seed IDs, mutation switches or hand-written per-bug rules. `-AnalyzerHome` at setup can select a newer compatible 009+ CLI; its actual version is recorded and its derive/freeze/analyze interfaces must match.

The frozen v009 is **development/PARTIAL**, not the operational v008 renamed as v009. S4/S6 are unimplemented; other classes have explicit evidence limitations. Directed live checks in this package show oracle confirmation for all six targets, but v009 reports a violation only for B6's server error on these minimal traces. That is a documented analyzer gap, not zero semantic bugs. See `VALIDATION.json`.

Native tool reports remain separate. A common-oracle finding is not called a native EvoMaster/RESTler/Provengo discovery. HTTP status membership alone does not decide B1 through B5. Test failures are not automatically distinct bugs.

### Sequence boundaries

Sampled Provengo and Java runs have authenticated, verified-empty per-case resets and are labeled `sequence-local`. RESTler/EvoMaster search traces are labeled **campaign-diagnostic**: this version does not pretend that an entire fuzzer campaign is one official test. An official sequence-local comparison for fuzzers requires subsequent native-test extraction/replay with verified boundaries. No hidden stitching or invented boundary reconstruction is performed.

## Windows setup and run

Use Python 3.10+, a JDK compatible with your Provengo JAR (normally the existing JDK 21), and the installed native tools. Scripts do not close an existing SUT or modify global PATH. Default managed port is **23443**, leaving existing 23242/23243/23244 work alone. The single managed HTTP gateway serializes backend requests; this is logical interleaving, not backend-overlap testing.

All filenames and script contents are English.

From repository root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Get-ChildItem .\library\benchmark-v001 -Filter *.ps1 | Unblock-File
& .\library\benchmark-v001\Setup-Library-Benchmark-v001.ps1 -InstallNativeTools
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 -Configuration all -Seconds 60 -Seed 1
```

Setup creates `.venv-benchmark-v001` **inside this benchmark folder**, installs the pinned Python requirements, runs the acceptance tests, and writes private `tools.local.json`. It uses the known Provengo installation path or an explicit `-ProvengoJar`. Missing EvoMaster/RESTler may be installed user-locally by the preserved v006 installer with `-InstallNativeTools`; it pins EvoMaster 6.2.0 and the original RESTler source revision, recording package versions/digests. Existing binaries are reused. Provengo itself is not downloaded or upgraded.

To supply exact native paths (recommended when several versions are installed):

```powershell
& .\library\benchmark-v001\Setup-Library-Benchmark-v001.ps1 `
    -ProvengoJar 'C:\Program Files\Provengo\Provengo Cli\Provengo.uber.jar' `
    -EvoMasterJar 'C:\tools\evomaster\evomaster.jar' `
    -RestlerPath 'C:\tools\restler\restler\Restler.exe'
```

A preflight captures native help output and binary hashes. The Java arm also requires a positive runtime-ID/loan transport check and a deliberately wrong-status check that must fail natively; neither enters the research score. Unsupported CLI options or a failed Java compile stop before scoring. RESTler's optional local installer needs network access and may take time to build; progress and installer logs are preserved.

### Small steps before all 28 cells

```powershell
# Derive and freeze analyzer knowledge only: no generators or SUT requests.
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 -PrepareOnly

# Ten sampled scenarios on the clean baseline first.
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 `
    -Configuration provengo-sample10 -Mutation none

# Existing full Java catalog on baseline; JavaLimit=0 means all 542.
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 `
    -Configuration provengo-java -Mutation none

# Infrastructure smoke only; NOT the full fixed catalog.
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 `
    -Configuration provengo-java -Mutation none -JavaLimit 3

# Each fuzzer separately, pilot budget in seconds.
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 -Configuration evomaster -Seconds 60
& .\library\benchmark-v001\Invoke-Library-Benchmark-v001.ps1 -Configuration restler -Seconds 60
```

`Seconds` controls each native fuzzer's search budget. Native sample generation and the fixed Java catalog have different stopping rules; **this is not a matched-time efficacy study**. Defaults: sample watchdog 240s per size-one batch; sampled replay/Java case watchdog 120s; Java arm watchdog 7200s. These watchdogs are infrastructure bounds, not reported equal search budgets. The launcher prints progress and stops only owned processes. A timeout is retained as incomplete execution, not a passing zero-bug arm.

## Outputs

Each run creates a new `runs/benchmark-v001-*` directory and a printed `*-review.zip` even if a later stage fails. It includes the common frozen contract/knowledge/engine hashes, exact native commands/help, unchanged sampled files, native reports, `http.jsonl`, per-cell oracle and analyzer reports, and `summary.json`. Native Java per-case outcomes are in `native.jsonl`. The manifest identifies original and patched sources. Raw reset controls are out of the generator schema; each boundary records empty-state verification. Repeated run directories are not overwritten.

The same passive records can be analyzed again using:

```powershell
& .\library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe `
    .\library\benchmark-v001\analyze_v001.py --folder 'C:\path\to\a\cell'
```

Use a new evidence-cell copy if outputs already exist: the independent analyzer rejects overwriting reports. For a non-default port, pass that run's frozen `openapi.json` with `--contract`. For fuzzer campaigns also pass `--scope campaign-diagnostic`.

## Verification and current limits

`Verify-Library-Benchmark-v001.ps1` runs nine test methods, including a 7-arm x 6-case matrix (42 subcases), strict-rule/204-body checks, schema checks, reset isolation, passive evidence gaps, unchanged Java catalog prefix, and seven independent Natchan integrations. The included `VALIDATION.json` separately records 12 directed real-HTTP cells (six baseline/mutant pairs) and the upstream v009 regression results. Directed tests live outside generator inputs and are never labeled autonomous discovery.

Linux verification covered Python, JS parsing, real loopback HTTP and Natchan. The three external native engines and Windows PowerShell were not available for end-to-end execution in the build environment; native Provengo sampling/replay, full Java compilation/catalog, RESTler and EvoMaster execution therefore remain to be verified on the user's installed tools. No live four-configuration discovery results are claimed by this package.

Setup diagnostics: every tool-configuration attempt writes a timestamped log under `library/benchmark-v001/setup-logs/`, including the Python executable, local tool root, traceback and the failed installer step tail. These logs are local and ignored by Git. A failure stops setup; do not start a campaign until setup completes.

The RESTler installer uses the same benchmark Python interpreter that successfully ran setup's pip and acceptance checks. It does not create a second Windows Python environment or select an interpreter from a stale manifest. Existing broken installer environments remain untouched. The chosen interpreter is recorded in `restler-python-check.log` and the tool manifest.

For upload, use `python library/benchmark-v001/pack_review_v001.py --latest`. This creates a compact diagnostic ZIP with a 32 MiB payload budget, 512 KiB per-file cap, log tails and a complete file inventory; JSONL traffic and binaries stay local. Truncated JSON is named `.tail.txt`. This subset is not sufficient for full evidence replay. Future campaigns produce both archives automatically.

Use `-ReuseRun PATH_TO_ORIGINAL_RUN -Configuration provengo-sample10 -Mutation all` to replay the original ten files after SHA256 verification. Original model inputs and Provengo binary identity are retained; contract/port changes are rejected. Baseline is rerun with mutants in a fresh result directory for paired scoring.

Storage update: sampled replays archive each closed runs-db database losslessly with gzip, verify its content hash and then remove the uncompressed copy before the next JVM. Archives remain local. Only the compact review ZIP is generated automatically. A 2 GiB free-space reserve is checked before and during native processes; the owned process is stopped if the reserve is crossed. Sample JSON remains unchanged and can still total about 2 GB per ten-sample set. Java single-process catalog database growth is not reduced by per-sample archival, but free-space monitoring applies.
