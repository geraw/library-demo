# Library mutation candidates v002

## Status: rejected for the requested rarity target

This package implements six proposed fault mechanisms and an efficient replay path.
Directed witnesses pass on the original and indexed baseline and expose every mutant.
The local empirical pilot shows these candidates are TOO EASY. This is not a qualified
rare-fault benchmark and does not justify another long user campaign.

Pilot on 84 existing recorded original traces: original and baseline both pass all 84.
Differences by mutant: B1 33, B2 47, B3 84, B4 40, B5 84, B6 70.
See validation-summary.json and pilot-84-results.json for per-case evidence.
No independent holdout or rarity confidence claim is made. These traces were already
used during development. Random IDs are rebound per resource kind, with ambiguous q
bindings rejected. Entire response bodies and status codes are compared; replay stops
at the first difference in each arm. Counts are detection-per-case, not activation rates.

## Contents and semantics

- original.py: byte-for-byte copy of the inspected original SUT (see SHA256.json).
- mutants.py: separately instantiated Flask app and maintained indexes/cache.
- verify.py: directed legal scenarios; three users and three books suffice.
- replay.py: streaming input from analysis ZIP; projected successful actions plus GET
  absence observations. Unexpected mutant 4xx remain failures, never filtered away.
- Invoke-Pilot.ps1: local environment setup, witnesses, small replay pilot, verified archive.

The six mechanisms are:
B1 reservation ownership left with the old borrower, causing a false occupancy rejection;
B2 stale retired relation causes book deletion to cascade by borrower instead of book;
B3 hold-position index is not repaired after erasure, deleting the wrong hold;
B4 missing loan-query cache invalidation on return;
B5 composite pair index retains an old loan incarnation;
B6 book-list index retains a deleted book with prior borrowing history.
B4 and B6 are broader than the narrative examples: the implementation does NOT require
all example interleavings. This is explicitly one reason these candidates are easy.
B2 similarly retains the first retired relation, which makes the defect reachable early.
The six mechanisms are distinct, but their failure-family boundaries overlap; no claim
of a literature-backed top-six taxonomy is made.

All auxiliary structures are maintained by the baseline. Original source is not patched.
/reset clears auxiliary state and initializes indexes from seeded rows.
Invalid requests are still handled by the original validation logic.

## Efficient engine: what it is and is not

This is Flask test_client replay in one process, serial and independently reset per arm.
It exercises routing, JSON handling and SUT logic but does not use TCP, Provengo's
actuator, Java callbacks or its SQLite database. It is a screening engine, NOT a measured
speedup of Provengo and NOT a fresh Provengo sample. Removing expected failures from
an original trace is validated by requiring full agreement with original retained
responses on both controls. It is not a new valid-only BP generator.

84 traces retained 11,154 of 124,481 source HTTP requests (~91% fewer).
Local case execution total was ~15.4 seconds; machine and engine differ from Windows
Provengo, so elapsed times are not a fair tool comparison.

Only one projected scenario is active on D at a time. Per-case results are copied to E,
SHA256-verified, then the completed D case directory is deleted. Failures retain D.
Use a new output directory; existing output is never silently overwritten.
No compression, sampling, external server reset, or old-run modification is performed.
HTTP raw source traces remain in the user's ZIP. Source ZIP must contain original/http.jsonl.

## Windows

Extract the package to D:\Yeshayahu\Temp\Library-Mutants-v002.
In PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& 'D:\Yeshayahu\Temp\Library-Mutants-v002\Invoke-Pilot.ps1' -Limit 10
```

The latest existing analysis ZIP on E:\ProvengoRuns is auto-selected and printed indirectly
through the results; pass -EvidenceZip explicitly to pin the source.
Limit 0 screens all archived cases. Python and pip connectivity are required for first setup.
Scripts were validated with Python 3.11 and Flask 3.1.3 on Linux; the PowerShell wrapper
has been inspected, not executed on Windows here.

Optional manual separate HTTP servers (the fast runner does not use these):

```powershell
python .\mutants.py --mode original --port 23600
python .\mutants.py --mode baseline --port 23601
python .\mutants.py --mode B1 --port 23602
```

Use separate terminals/processes. No HTTP parallel orchestration is claimed in this package.

## Next qualification step

Replace or refine the easy mechanisms before treating this as the requested final
benchmark. Validate meaningful lifecycle-dependent faults with directed witnesses,
then an independently sampled valid-only campaign. Do not add arbitrary counters or
pattern-match a predetermined event sequence to manufacture rarity.
