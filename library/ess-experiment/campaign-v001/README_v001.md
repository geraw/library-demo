# ISSTA Library campaign v001

## Status and scope

Prepared orchestration for steps 1–5: observation/contract provenance, isolated
five-instance model preparation, a 100-case Provengo sample and replay, measured
budget creation, and a budget-matched EvoMaster native search. This is NOT a
record of a completed Provengo or EvoMaster discovery campaign.

No Provengo/EvoMaster executable is included or downloaded. The implementation
environment had Java but no installed Provengo or EvoMaster JAR and no access to
the user's local installation. Native sampling, replay compatibility and the
actual budget therefore remain to be verified on Windows. A guarded smoke stage
is mandatory. If that stage fails, preserve its output; do not bypass the guard
or substitute a guessed result/budget.

RESTler is the next stage after review of the measured Provengo campaign; no
RESTler campaign is claimed by this version. No automatic expansion from 100 to
200 occurs: inspect the first campaign before selecting 200 explicitly.

## Start on Windows

From repository root, use the existing Python virtual environment with Flask:

```powershell
Set-Location 'C:\work\temp\library-demo'
git pull --ff-only origin master
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\library\ess-experiment\campaign-v001\Invoke-ISSTA-Provengo-v001.ps1 -SampleSize 100
```

The wrapper automatically locates the installed Provengo.uber.jar. Pass
`-ProvengoJar 'C:\actual\path\Provengo.uber.jar'` if it finds more than one or none.
It runs the JAR with Java's executable main entry, not StrictGuidedRun.java.

The script manages its own SUT and proxy at ports 23244 and 23243. The existing
service on 23242 can remain running. Occupied experiment ports cause a stop;
unrelated processes are never terminated. Child processes created by this
campaign are stopped on normal completion or a handled error.

Run output is under `library/ess-experiment/runs/issta-v001-TIMESTAMP/`.
Send the completed output directory for review; if stopped, send the newest
directory, especially the smoke/sample/help logs. Do not interpret a partial
directory as a completed experiment.

## Model preparation (original files remain unchanged)

The model is copied into the run directory, excluding generated products and
editor configuration. Checked source transformations:

- Five user and five book creation attempts, with stable descriptive text.
- Up to five active loans and five active holds as workload bounds, not SUT
  restrictions. These bounds are not assertions that exactly five will be reached
  in every randomly sampled test, nor five lifetime creations of every type.
- At most three successful model-level borrowings and three hold creations per
  user/book pair. Rejection variants inherited from the original interface are
  not globally deduplicated; the 500-event bound also limits those loops.
- Remove the old user-level single-active-loan restriction; retain book exclusivity.
- Change the corresponding negative-loan query to reject only busy books.
- Point the copied interface to the recording proxy, keeping its RTV binding.
- Bound each official sampled scenario to 500 events.

No hand-written fault-trigger sequence is injected into the sample. The model
remains analyst-authored; the script does not claim generation solely from OpenAPI.
The original interface accepts some numeric-string variants beyond the integer
OpenAPI schema. This inherited extension is recorded as a limitation; the
external legal-loan rejection oracle conservatively scores integer-ID payloads.
State-preservation checks still run for other payload variants.

Sample options are selected from the installed CLI's help (max-length versus
max-depth). CLI help and the JAR hash are retained. Sampling is stochastic; no
unverified seed option is supplied. The saved sample file and SHA-256, rather
than regenerating a sample, define the replay identity. The script recognizes
top-level lists or lists under scenarios/runs/samples and refuses unknown formats
or a count different from the requested size.

## Execution and timing

1. Copy/freeze inputs and capture local Git HEAD and JAR hash.
2. Generate one short smoke sample and replay with all mutations disabled.
3. Require real HTTP activity, no native failure and no semantic candidate.
4. Generate the official 100-case sample (or explicitly selected 200).
5. Replay every saved case in control, resetting before each case.
6. Require all cases to send HTTP, no control native failure, no control semantic
   candidate, and at least one successful dependent resource creation.
7. Replay the SAME saved cases with all five mutations enabled, with per-case reset.
8. Publish budget.json only after complete HTTP execution.

The budget is ceil(official sampling wall time + all-enabled suite execution wall
time). Control, preparation and smoke are measured separately/excluded. Each
case currently uses a new JVM; its startup cost, proxy readback overhead and
managed-service lifecycle are included in execution wall time and explicitly
reported. This can materially increase a 100-case run. No runtime is promised.
Native failures can stop a case early; runs.json retains each exit code rather
than treating an early stop as a complete scenario.

Per-case timeout: 180 s; official sample timeout: 600 s. These are orchestration
guards, not baseline search budgets. A timeout stops the pipeline; partial
results must be reviewed rather than counted as complete. A generated sample
that ends at the length bound is not a proof that every modeled lifecycle ended.

## Observation and semantic evaluation

The proxy logs actual tool requests/responses, independent oracle readbacks,
server identity, boundaries and semantic candidates to http.jsonl. The observer
uses public collection GETs after writes; it does not inspect SUT lists directly
or provide oracle-derived IDs/data to generators. Book existence is checked when
the tool itself requests a book detail read. The fixture is imported only for
managed startup and recording the effective mutation switch configuration.

The observer tracks successful creations and exact requested deletions, then
compares readback state. It checks valid integer-ID loan rejections and existing
book detail reads. Subsequent findings after a first mismatch are marked with
prefix_tainted=true; they cannot independently establish another fault.

This external observer is more than each tool's native fault oracle. Its
candidates must be reported separately from native tool failures. The observer
does not fully validate arbitrary API payloads or every possible business rule.
The common proxy serializes requests: this is a logical-sequence experiment,
not a backend-concurrency benchmark. Oracle GETs do not change this fixture's
state; all tools in a later comparison must use the same instrumentation.

The current summary deliberately says NOT_YET_SCORED: verify clean-prefix
candidates and replay against isolated mutations before a confirmed per-bug
score. No enabled flag is itself evidence of discovery.

## EvoMaster after the measured campaign

```powershell
& .\library\ess-experiment\campaign-v001\Invoke-ISSTA-EvoMaster-v001.ps1 `
    -CampaignPath 'C:\work\temp\library-demo\library\ess-experiment\runs\issta-v001-ACTUAL-TIMESTAMP' `
    -EvoMasterJar 'C:\actual\path\evomaster.jar'
```

Supply actual paths; the script refuses to guess a budget. It records the JAR
hash/help and chooses schema/base option names from the installed binary's help.
It passes the measured budget as maxTime and seed=1, and saves generated tests,
native output and HTTP evidence. Wall time can exceed maxTime because startup
and postprocessing are separate from native search. An additional 300 s is an
orchestration timeout allowance, not extra authorized search time.

Native EvoMaster black-box search may accumulate state across its own internal
tests. Its live proxy ledger is therefore explicitly campaign-global diagnostic
evidence, with official score UNDETERMINED. Generated-test replay with one reset
per test is still required for sequence-local confirmation. No undocumented
per-test-reset support or arbitrary test boundaries are assumed.

Installed EvoMaster versions differ. Unsupported help options stop the script
before search. No claim is made that an untested version is compatible.

## Validation performed before committing

- Python syntax compilation passed.
- Model snapshot preparation and JavaScript syntax checks passed against the
  retrieved source. This does not substitute for execution by the installed
  Provengo runtime.
- Ten real-HTTP integration combinations passed: all five trigger cases against
  control and against the corresponding isolated mutation. Control has no
  semantic candidate; the mutant's first candidate has an untainted prefix.
- The fixture's earlier deterministic ground-truth tests remain separate.
- Full native CLI execution and Windows PowerShell execution were not available
  in the implementation environment; they are pending the mandatory local smoke.

Run observer checks separately from discovery measurements:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover `
    -s .\library\ess-experiment\campaign-v001 -p test_observation_v001.py -v
```

References used for command preparation:
- https://docs.provengo.tech/ProvengoCli/0.9.5/subcommands/sample.html
- https://docs.provengo.tech/ProvengoCli/0.9.5/subcommands/run.html
- https://github.com/WebFuzzing/EvoMaster/blob/master/docs/blackbox.md
- https://github.com/WebFuzzing/EvoMaster/blob/master/docs/options.md

v001: initial guarded campaign infrastructure. Preserve the earlier 542-case
checkpoint; it is not replaced or retroactively reinterpreted by this version.
