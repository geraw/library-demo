# Home continuation handoff v001 — Library ISSTA experiment

Checkpoint date: 2026-10-19, Asia/Jerusalem.
Repository: https://github.com/geraw/library-demo
Branch: master
Implementation release: 5db175073178cf19b22b39ff08606a59994c4483

## Objective and agreed scope

Compare a 100-case Provengo sample/replay campaign with EvoMaster and RESTler on
the same controlled Library fixture. Inspect the 100-case results before deciding
whether to increase to 200. Baseline search budgets must come from measured
Provengo sampling plus mutant-suite execution, not the previously proposed hour.

Chat in Hebrew; source, scripts, logs and research documentation in English.
Use versioned scripts. Keep the original SUT and model unchanged.

## Five agreed mutations

1. Reject the fourth simultaneous distinct book loan to one reader.
2. Reject the third borrowing of the same book by the same reader after two returns.
3. Returning one book also deletes another active loan of that reader.
4. First detail GET of an existing book returns 404 (raw string versus integer ID).
   The second-read-only variant was explicitly rejected in favor of this original.
5. Deleting one hold also deletes other holds owned by the same reader.

The experiment contract is library/sut/library_openapi_issta.json. It clarifies
the required business semantics. Do not attribute these detailed rules to the
original sparse OpenAPI. Experiment control is sut_buggy_issta.py with
ISSTA_BUGS=none, NOT original sut.py, which permits only one active loan per reader.

## What is committed

- 16de097: fixture, mutation switches, English bug documentation, companion
  contract and deterministic ground-truth verification.
- 5a43f06: RESEARCH_CHECKPOINT_20261019_v001.md.
- 5db1750: library/ess-experiment/campaign-v001/ with six files:
  Invoke-ISSTA-Provengo-v001.ps1, Invoke-ISSTA-EvoMaster-v001.ps1,
  campaign_v001.py, observed_server_v001.py, test_observation_v001.py,
  README_v001.md.
- This handoff and the local export helper are added after that implementation
  release. No implementation behavior is changed by the handoff.

## Evidence already received

StrictGuidedRun.java was compiled and executed on the work computer against the
original SUT and the intended all-enabled mutant. Each log reports 542 scenarios:
409 REACHED, 133 expected blocks, no STUCK, BUG: REACHED or actuator exceptions.
The logs do not establish HTTP-level mutation execution/detection. Do not report
this as a 0/5 mutation-detection score.

Original log:
strict-guided-original-20261019-172455.log
SHA256 f30ecf097921de45f74c1fb5a2b8540c13bfef8ea3040e649d1dd734657428d3

Mutant log:
strict-guided-buggy-all-20261019-173137.log
SHA256 5784b970d2e1c645a615a8809886615868410dd740095c15190e19138d6a4447

Both were uploaded in this conversation and are preserved in ChatGPT files.
They are not added to Git by the checkpoint. Local copies should be preserved
using the export helper, which includes the library tree and named Downloads logs.

## Validation completed versus pending

Completed in the implementation environment:
- Earlier 15 fixture scenario/configuration combinations plus reset-history check.
- Ten real-HTTP observer combinations: each target against control and its
  isolated mutation, with no false candidate in control.
- Model snapshot preparation and JavaScript/Python syntax checks.

Pending / not received:
- Native Provengo smoke and the 100-case measured campaign on Windows.
- Actual budget.json and the generated review ZIP.
- EvoMaster native search with that measured budget.
- Per-generated-test EvoMaster clean replay and confirmed per-bug score.
- RESTler runner preparation and campaign.

No results from a v001 native campaign were supplied after its run command.
If the work computer has since produced a run, preserve and inspect it before
starting another campaign at home. Partial directories may contain important
failure evidence even when budget.json or a review ZIP is absent.

## Current orchestration behavior

Creates a fresh run directory and a model snapshot with five users and five
books, workload limits of five active loans and holds, and at most three model
loan/hold creations per pair. Counts are bounds, not guaranteed observed coverage.
The copied model removes user-level loan exclusivity and retains book exclusivity.

Uses a managed proxy on 23243 and a backend on 23244. Existing SUT on 23242 can
remain running. Refuses occupied experiment ports. Logs real HTTP separately
from independent collection readbacks and candidate verdicts.

Runs smoke control first, then official sampling, full control replay, and
all-enabled replay. Stops if control fails or real HTTP execution is incomplete.
Each test has an independent reset and JVM invocation; startup and observer
overhead are included in measured execution time. No runtime is yet measured.

budget.json uses ceil(sample time + mutant replay time); excludes preparation,
smoke and control. EvoMaster native internal-test boundaries are not assumed:
its initial search trace is campaign-global diagnostic evidence pending isolated
generated-test replay. External oracle candidates and native tool failures must
remain distinct.

## Before leaving the work computer

If a campaign is running, let it finish if practical. The exporter snapshots files;
it cannot freeze an active process or make concurrently changing logs consistent.
Do not kill unrelated Java/Python processes.

From repository root:
```powershell
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\library\ess-experiment\campaign-v001\Export-ISSTA-Home-v001.ps1
```

Copy the printed ZIP to the home computer (USB or your usual file transfer).
The ZIP contains the current library tree (including local runs/logs/products),
root documentation, Git status/diff, and a Git bundle. It excludes .venv and
installed Java/Provengo/EvoMaster/RESTler binaries, which must be installed or
located separately at home. Exact source bytes are preserved; active runtime
state is intentionally not claimed.

If no local campaign or local edits exist, the Git repository plus this handoff
are sufficient for source continuation; the old uploaded logs remain in this chat.

## At home — isolated fresh checkout

Use a new directory to avoid overwriting another checkout:
```powershell
& {
    $ErrorActionPreference = 'Stop'
    New-Item -ItemType Directory -Force 'C:\work\temp' | Out-Null
    $homeRepo = Join-Path 'C:\work\temp' ('library-demo-home-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    git clone --branch master https://github.com/geraw/library-demo.git $homeRepo
    if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
    Set-Location $homeRepo
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    & .\.venv\Scripts\python.exe -m pip install Flask
    if ($LASTEXITCODE -ne 0) { throw 'Flask installation failed.' }
    Write-Host "Repository ready: $homeRepo"
}
```

Java must be available in PATH. The Provengo script expects an installed
Provengo.uber.jar under C:\Program Files\Provengo\Provengo Cli or an explicit
-ProvengoJar path. EvoMaster requires an explicit JAR path; no assumed work
computer path is portable.

Extract the work ZIP into a separate evidence directory. Do not overlay its
library tree onto the fresh checkout blindly. Inspect source-diff.patch and
git-status.txt first if they show local changes. Historical run directories can
be inspected in place. Copied campaigns may contain absolute work-computer paths
and are not promised to be directly restartable on another machine.

## Immediate next action at home

If no v001 campaign has already run at work:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\library\ess-experiment\campaign-v001\Invoke-ISSTA-Provengo-v001.ps1 -SampleSize 100
```

Do not start a separate experiment server manually. On completion upload the
REVIEW_ZIP path printed by the script. On failure send the newest run directory
or the relevant smoke/help/sample logs. Do not bypass control gates.

Only after a completed budget exists:
```powershell
& .\library\ess-experiment\campaign-v001\Invoke-ISSTA-EvoMaster-v001.ps1 `
    -CampaignPath 'ACTUAL_COMPLETED_CAMPAIGN_PATH' `
    -EvoMasterJar 'ACTUAL_EVOMASTER_JAR_PATH'
```

RESTler follows review of these results. No confirmed discovery score is available yet.

## Context for resuming the conversation

Continue geraw/library-demo master from HOME_HANDOFF_20261019_v001.md and
campaign-v001/README_v001.md. Preserve the original 542-case checkpoint.
First ask whether a v001 run was completed at work only if its output has not
been supplied; inspect existing output before regenerating. Resolve native smoke
compatibility without changing business rules to make failures disappear.
Do not claim completed discovery, measured budgets, or five guaranteed resource
instances without actual retained evidence.
