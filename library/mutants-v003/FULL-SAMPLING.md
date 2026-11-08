# Full-model sampling, projected execution and B2 reachability

## What changed

`FullSample` offers the original positive and negative variants, retry loops and
relationship-removal rechecks. No lifetime/creation/deletion policy was changed.
The full-model interface emits plain JSON events without callbacks, REST objects
or runtime-value state. This avoids the old hundreds-of-MiB callback serialization.
It is a transport adaptation, not a claim of bit-identical native REST sampling
probabilities. `Sample` remains the previously released positive-only model.

The native sampler still chooses a path of at most 2,000 events. Field rejection
checks contribute to that cap. Nothing guarantees 2,000 functional actions or
that all paths will reach the cap.

For each case, the pipeline:
1. Uses native Provengo to sample one full path on the work drive.
2. Executes the path on the original Flask app, checks every declared status and
   checks that each rejected operation leaves users/books/loans/holds unchanged.
   This is fast Python actuation; negatives are never executed by the Java actuator.
3. Saves `full-reference.jsonl`, then removes original-rejected events except GET
   404 observations. Preserves order and original event numbers in reference.jsonl.
4. Replays the same projected reference on original, baseline and B1-B6. Full JSON
   and status comparisons apply. Unexpected mutant 4xx remain findings.
5. Copies case files to the archive drive, verifies hashes, then removes completed
   work cases. Raw JSON samples are retained, without gzip or ZIP storage per case.
6. Produces an analysis ZIP after the campaign; partial cases with a summary can
   also be collected. The ZIP is for upload, not the working storage format.

Samples above 8 MiB fail instead of filling the drive. Only one case is sampled
at a time; archive growth still depends on actual lengths and response bodies.
Measure the first cases before claiming a total space requirement. Old evidence
and mutant implementations are unchanged. Original plus baseline are mandatory
control gates. Do not pool compact and full sampling as one distribution.

## Work PC: small native B2 check only

After `git pull --ff-only origin master`, from C:\work\temp\library-demo:

```powershell
& .\library\mutants-v003\Invoke-Full-V003.ps1 -Mode CheckB2 `
    -WorkBase 'C:\work\temp\LibraryRuns\work' `
    -OutputBase 'C:\work\temp\LibraryRuns\results'
```

This is one directed path with 24 requests, not a 500-case random campaign. The
extra guide only blocks events other than the next witness operation; it never
requests an event. It binds role IDs from the existing creation stories. A missing
model offer stops the guide; the runner rejects an incomplete/different path.
Success requires B2_GUIDE_COMPLETED, exact semantic witness agreement, passing
controls and B2 divergence. Other mutations are also replayed independently.
Do not count this guided diagnostic as random bug discovery. Upload UPLOAD_THIS.

## Home: 500 random full paths, one at a time

From D:\Yeshayahu\Temp\library-demo, after pulling master:

```powershell
& .\library\mutants-v003\Invoke-Full-V003.ps1 -Mode FullSample `
    -SampleSize 500 -MaxLength 2000 `
    -WorkBase 'D:\Yeshayahu\Temp\ProvengoWork' `
    -OutputBase 'E:\ProvengoRuns'
```

The B2 guide is NOT loaded in FullSample. JAR lookup is unchanged: local tool
configuration or -ProvengoJar. The same eight apps are actuated through Flask
 test_client, not TCP. Existing saved traces are not modified.

To resume, use Invoke-V003.ps1 -Mode FullSample -ResumeRun '<run>' with identical
SampleSize/MaxLength/Seed/code/JAR and original base paths. The collector can also
be called directly as documented in RUNNING.md. Do not resume an old compact run
with the full model.

## Local validation and boundary

B2's original and baseline API witnesses pass; B2 diverges. The witness uses three
users, three books and 24 requests, with no invalid inputs. The real DAL query
functions accept every planned create/delete action; each hold pair is created
only once and the final read has an available verification opportunity.
`check_b2_model.js` checks those prerequisites but does not emulate Context's
scheduler or lifecycle. The native CheckB2 result is still required.

`check_full_adapter.js` exercises negative and positive offerings, retry loops,
PUT rejection, GET404 and callback-free output. Python tests cover projection,
control equivalence, status-mismatch rejection and B2 semantic/API agreement.
No native JAR or PowerShell runtime was available here. Fake-CLI workflow tests
are not evidence of native scheduling. No rarity qualification is claimed.
