# v003 execution

This is an explicitly experimental release of the repaired six mutants.
All six have legal directed witnesses. Rarity is NOT qualified; B3 remains detectable
in 6/84 calibration cases. Previously published v002 is not overwritten.

## Existing cases, work PC

From C:\work\temp\library-demo after git pull:

```powershell
& .\library\mutants-v003\Invoke-V003.ps1 -Mode Existing `
    -WorkBase 'C:\work\temp\LibraryRuns\work' `
    -OutputBase 'C:\work\temp\LibraryRuns\results'
```

Default input: library/clean-scenarios-v001. It currently contains **84**, not 86,
validated clean cases. The runner prints AVAILABLE_CASES and runs all of them.
To use a folder/ZIP with additional cases, pass -EvidencePath with its actual path.
Supported inputs: flat case-XXX.jsonl, case-XXX/original/http.jsonl, original evidence
ZIPs, or the case-XXX/reference.jsonl folders produced by new Sample mode.
No new sampling is performed in Existing mode.

## New compact Provengo samples, home PC

From D:\Yeshayahu\Temp\library-demo after git pull:

```powershell
& .\library\mutants-v003\Invoke-V003.ps1 -Mode Sample `
    -SampleSize 500 -MaxLength 2000 `
    -WorkBase 'D:\Yeshayahu\Temp\ProvengoWork' `
    -OutputBase 'E:\ProvengoRuns'
```

Provengo JAR/java are read from library/benchmark-v001/tools.local.json, with fallback
to C:\Program Files\Provengo\Provengo Cli\Provengo.uber.jar. Override with -ProvengoJar
and -Java if needed. Native CLI sampling flags are detected from sample -h.

MaxLength counts up to 2,000 retained model events, not 2,000 old fuzzing events.
Scenarios may naturally terminate earlier. This is a NEW sampling distribution, not
a reproduction of the old 84 projected cases. Five users and five books remain in
the model. Positive story/DAL logic and Context interleavings are retained. Canonical
positive payloads are selected, negative helpers emit no events, and GET 404 absence
checks remain. No invalid fields, invalid routes, or expected state rejection attempts
are sampled. Unexpected mutant 4xx still cause a recorded divergence.

Each sample carries plain JSON events, logical identity metadata and symbolic ID
references, with no JavaScript callback serialization. It is consumed by
sample_campaign.py, NOT native provengo run. Sampled JSON over 8 MiB is rejected.

For each case:
1. Native Provengo `sample --size 1` generates a NEW compact sequence on D.
2. The original SUT materializes its symbolic IDs and checks declared status codes.
3. Original, baseline and six independent mutant apps replay exactly that reference
   through Flask test_client. Full JSON bodies/statuses are compared; each mutant
   stops at first divergence. A control divergence stops the campaign.
4. Case evidence (sample, original reference, traces, commands, timing, summary) is
   copied to E and SHA256-verified before the completed D case is deleted.

FIRST_SAMPLE_CONTROL_GATE_PASSED is printed only after the first real sample passes
both controls. No remaining cases are generated if that gate fails. The loops record
results incrementally. Source sample generation is independent of mutant outcomes.
No old sampling files or existing experimental results are edited.

Keep the machine awake while sampling. No permanent Windows power settings change.

## Resume a stopped sampling campaign

Use the same SampleSize, MaxLength, Seed, code and Provengo binary, adding:

```powershell
-ResumeRun 'E:\ProvengoRuns\library-v003-sample-<printed-id>'
```

Completed archives are checked and skipped. A partial case is moved to an incomplete
folder and retried without deleting the previous evidence. Changed code/JAR or campaign
parameters reject resume. Unrelated existing campaigns are never overwritten.

Selection seed is passed only if native `sample -h` advertises --seed. Otherwise the
code records selection_seed_flag=null and makes no engine-seed reproducibility claim;
exact sampled event files remain available for replay. Model data seeds are recorded.

## Collect results

```powershell
& .\library\mutants-v003\.venv\Scripts\python.exe `
    .\library\mutants-v003\collect_results.py '<RESULT_DIRECTORY>'
```

## Validation boundary

- Six legal directed witnesses and 48 witness/mode expectations pass.
- 14 Python test groups pass locally, including mocked-CLI campaign/resume tests.
- Node interface-adapter smoke passes (13 compact events, no callbacks or field checks).
- All 84 existing cases pass on original/baseline; mutation counts remain 1,0,6,0,2,1.
- 100 independent functional control probes passed; these are not Provengo samples.
- No native Provengo JAR is installed here. Real compact sampling and PowerShell
  execution are NOT claimed as tested locally. The on-machine first-sample gate is
  deliberately mandatory. A fake CLI in a unit test is not evidence of native success.
- The fast replay omits TCP, the native Java actuator and its SQLite result database.
  Its timings are not a fair tool comparison against native Provengo runs.

## Relationship-removal rechecks (post-calibration model update)

Both the main stories and compact sampling stories now register one persistent
Context bthread per active loan. A hold cancellation or loan return offers a new
existence read for each surviving loan. Pending reads may coalesce later removals;
reads are not forced before other operations. Context owns termination on loan
removal, preventing detached checks from surviving into a later incarnation.
This closes an observation gap: a successful creation-time read alone cannot
observe damage caused by a later relationship removal. It is not a rarity guard.

Mutant code and old 84-case results are unchanged. Existing mode replays saved
requests and therefore does not acquire new reads. Only newly sampled sequences
use this updated story. Do not pool old and new sampling results as one unchanged
distribution. Changed model hashes also prevent resuming an older Sample campaign.

Local check: `node library/mutants-v003/check_story_rechecks.js` exercises story
registration, both removal triggers, repeated reads and exclusion of GET triggers
for both model copies. It does not emulate Context cancellation or prove native
Provengo scheduling; those still require a real first-sample control check.

## Full-model sampling and directed B2 check

See FULL-SAMPLING.md. New modes FullSample and CheckB2 retain the full negative
request alternatives at sampling, then project only original-rejected requests
out of execution. Invoke-Full-V003.ps1 also collects an analysis ZIP.
CheckB2 defaults to one diagnostic path and is not random discovery.
