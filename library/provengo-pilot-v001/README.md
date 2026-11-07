# Library Provengo pilot

Prerequisites: the existing Library benchmark-v001 installation, including its Python
environment, tools.local.json and a working Provengo JAR. Use the original
library/sut/sut.py snapshot from which the included mutants were built. The runner
validates its hash after normalizing Windows line endings.

From an existing checkout, pull the published pilot. In PowerShell:

```powershell
Set-Location 'D:\Yeshayahu\Temp\library-demo'
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git pull failed.' }
& .\library\provengo-pilot-v001\Invoke-Library-Pilot.ps1 -RepoPath (Get-Location).Path
```

Defaults: 100 scenarios, 2,000 maximum model steps, seed 1, port 23443.
Each scenario is sampled in its own JVM to bound memory. The manifest stores
the sample hashes and CLI seeds when supported by the installed JAR.
Use -SampleSize 2 for a smoke run, and -Port to choose an unused port.
Each invocation creates a new campaign directory by default.

Order: original, baseline (all bugs off), B1, B2, B3, B4, B5, B6.
The runner checks both controls before proceeding. It compares native outcomes
and observed HTTP requests/responses in order after binding generated IDs to
creation order. A difference or incomplete control stops the campaign and
preserves its evidence. This is trace agreement on the frozen sample set.
The benchmark model and OpenAPI are adapted in the run directory to match
the original SUT's successful DELETE 200 response. The repository is not edited.

RUN_DIRECTORY contains samples/manifest.json, controls.json, summary.json,
the frozen SUTs, and per-arm native logs, raw HTTP traces and passive oracle
results. Request counts exclude reset and health traffic. B3 has a separate
paired witness file for the first aligned 201-to-400 divergence from a passing
baseline; the v001 passive B3 check tests a different property.

B6 runs the same cases but is reported as BLOCKED_BY_SERIAL_GATEWAY.
Its required overlap cannot occur through this gateway. Do not count a zero
finding for this arm as a detection miss. This pilot measures the serial arms;
B6 requires a concurrent replay configuration.
