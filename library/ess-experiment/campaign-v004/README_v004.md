# v004 — Separate business and investigator models

## Scope

Two independent Provengo profiles replace the mixed model for new campaigns.
The original library/provengo and v001–v003 files/results remain unchanged.
The old sampled cases are retained as mixed-model preliminary evidence. New
v004 samples and timings must not be combined with those old measurements.

This version implements model separation, not a reported native discovery result.
Model generation, JavaScript adapter/syntax tests and public-HTTP observer checks
were verified locally. Native Provengo sampling/replay on Windows remains pending.

## Business model

Template: business_stories_v004.js. Retains the original interface's RTV mapping
and DAL in an isolated snapshot. Replaces the old story file entirely with
independent positive-operation stories and reads. At the interface boundary,
only valid variants expecting 2xx are eligible. Invalid shapes, missing-resource
checks, unsupported updates and intentional rejection stories are absent.

Independent behaviors: create readers, create books, borrow an available book,
return it, reserve it, cancel a reservation, delete an eligible reader/book,
and read existing resources. Their order emerges from Provengo scheduling.
No seeded-fault IDs or hand-written trigger sequences guide the scheduler.

Workload bounds: five readers and five books can be created; up to five active
loans/holds; at most three successful creations per reader/book pair for each
relation. Bounds do not guarantee observed coverage. Reader-level loan
exclusivity is removed; book-level exclusivity and deletion eligibility remain.
Numeric-string variants inherited from the interface remain accepted extensions
of the integer OpenAPI schemas; the observer now normalizes them like the SUT.

Business examples are possible compositions, not prewritten tests: one reader
may borrow different available books; a returned book may be borrowed again;
one of several holds may be cancelled. Early deletion can shorten a sampled
lifecycle. The pilot measures whether meaningful states are actually reached.

## Investigator model

Template: investigator_stories_v004.js. It uses a standalone REST event boundary,
with no business DAL or original interface stories. There are 14 finite families:
invalid reader/book/loan/hold bodies; missing and invalid deletes; invalid and
missing book reads. Each family selects ONE offered variant and terminates.
No retry-until-valid loop, no business resource creation and no implicit reuse
of resources from another test. Fixed missing IDs are out of the fixture's
server-assigned range. Unknown-resource calls are deliberate negative tests.

All 14 families execute once in a complete investigator scenario; ordering and
chosen variants vary. A ten-case sample does not guarantee all variant choices
are covered. Investigator outcomes are contract/input robustness evidence,
separate from the five semantic mutation classes.

## Independence and actual evidence

Before EVERY case: POST /reset, require success, GET all four public lists and
require each to equal []. A boundary record logs empty_verified=true and all
four zero counts. Provengo starts in a fresh JVM per replay case, clearing its
model/RTV state. A two-case HTTP regression verifies that a reader created in
case 1 is absent in case 2. Scenario numbering is global in the manifest;
the native log may still say TEST-1 for a selected file-local case.

The observer checks the affected collection after each write rather than all
four. Deleting readers/books still checks all four for relational effects.
Rejected writes get a preservation check for their addressed collection.
These are harness requests, logged separately and never supplied to generators.
They do not overlap backend operations. All future tools must use the same
observation policy for comparable evaluation.

Each completed case saves runs.json immediately and test-NNN-readable.md with
the executed method/path/body and ACTUAL status. Original responses and server
IDs are in http.jsonl, separate from the native expected-code event log.
On a 300-second timeout, exit_code=124/timed_out=true and readable evidence are
retained; execution is incomplete and no comparison budget is published.
Earlier mixed-model 180-second timeouts are not retrospectively reclassified.

The observer reports candidates, not automatically confirmed fault scores.
Findings after the first divergence are marked prefix_tainted. Native failures,
external semantic candidates, trigger coverage and clean-prefix confirmation
remain different measures. The native tool binaries are not bundled.

## Prepare both models without running Java or a server

```powershell
Set-Location 'D:\Yeshayahu\Temp\library-demo'
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\library\ess-experiment\campaign-v004\Prepare-ISSTA-Models-v004.ps1
```

Outputs two complete generated model directories under a new
prepared-models-v004-TIMESTAMP folder, with their source hashes/profile records.

## Ten-case control pilots (run sequentially)

```powershell
& .\library\ess-experiment\campaign-v004\Invoke-ISSTA-Provengo-v004.ps1 `
    -Profile business -SampleSize 10

& .\library\ess-experiment\campaign-v004\Invoke-ISSTA-Provengo-v004.ps1 `
    -Profile investigator -SampleSize 10
```

Each command independently prepares a snapshot, checks one smoke case, samples
in fresh five-case JVM batches with explicit -Xmx2g, and replays control only.
They must not run concurrently because both use managed ports 23243/23244.
Port 23242, VS Code and Vikunja are untouched. Output folders identify the
profile: runs/issta-business-v004-* or runs/issta-investigator-v004-*.
Send the REVIEW_ZIP. No 100-case campaign or mutant run starts automatically.

After reviewing the pilots, an explicit official command can use
-Profile business -SampleSize 100 -IncludeMutant. The budget is published only
after control gates and full mutant HTTP execution pass; it includes sampling
plus one mutant-suite wall time, excluding control/setup. Do not use a control
pilot's timing as if the full mutation campaign had completed. EvoMaster's
native campaign-global trace still needs per-generated-test replay; RESTler
orchestration remains pending.

## Validation

- Both profile snapshots generated against retained repository inputs.
- JavaScript syntax checks passed.
- DSL adapter test executes 14 investigator families with one selection each;
  an interface adapter check exercises the generated business boundary's actual
  variant filter. This is not the native Provengo runtime.
- HTTP checks cover all five isolated mutations and controls, process-launcher
  identity/shutdown, and two successive independently empty cases.
- Batch mapping/failure tests preserve the earlier 100-case manifest behavior.

v004: intentional experimental protocol change following the observed v003
326 tool / 1228 observer request imbalance and case-46 timeout. Models and
observation overhead are changed together and must be versioned in reporting.
