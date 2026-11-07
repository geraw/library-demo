# Query and story evidence repair — 009-dev.8

## What changed

- Explicit conjunctive filters are evaluated on declared, comparable query fields
  even when additional query parameters exist. Duplicate known predicates,
  unsupported values and absent response fields still cause abstention. Extra
  parameter names are retained in evidence details. No parameter is globally
  deleted from normalized traffic.
- Lifecycle correlation may retain an otherwise qualified create/delete/read
  sequence with undeclared query parameters on operations having no declared query
  parameters. Its contradiction is a **policy observation**, not a proved
  violation. Declared representation/selection query semantics remain unsupported.
  Actor, epoch, case, serial-capture and intervening-mutation guards remain.
  Lifecycle contradictions without an explicit semantic policy are now also
  observations; this closes an older overstatement in the generic checker.
- Story and attempt identifiers are opaque execution boundaries. They do not
  select rules or encode expected outcomes. Different attempts cannot supply
  each other's before/after state.
- `request-timeout` and `infrastructure-error` are not server HTTP answers. They
  increment separate counters and break sequence continuity. Authentication
  records are excluded from product-request counts.
- Explicit enum fields are excluded from inferred foreign-key observations.
  Empty copy reference sets do not establish a broken reference.
- `review_stories.py` reads a package ZIP or its extracted directory, validates the
  supplied contract against the recorded hash, and analyzes the raw journal.
  Producer checks are reported separately: `pass:null` is an observation;
  failed checks from non-completed stories are excluded; empty INTRA-REF checks
  are excluded. Producer results describe the last attempt; raw attempts remain
  separate in independent analysis. Story families and check names are never
  substituted for independent raw evidence.

The supplied [EVIDENCE_FORMATS_STORIES.md](EVIDENCE_FORMATS_STORIES.md) is retained
verbatim as format documentation, not executable oracle rules.

## Validation and limits

- 192 analyzer tests, including new query, attempt boundary, transport gap, enum
  and empty-reference controls. Library acceptance additionally sends real
  in-process HTTP requests with extra query parameters for B1/B2/B4 and baseline
  counterparts. These are small acceptance flows, **not** the long saved campaign.
- Existing 14 real relational witnesses and 14 repaired controls remain valid.
  G014 retains its six 500 state-effect witnesses and ten rollback controls.
- Cycle-5 source: `weissye/vikunja_study`, commit `dc79b7a`.
  Preserved direct reproduction pairs in `results/repro-c5-20261102/` yield
  six Homebox and two Paperless server-500 observations, with eight non-500
  controls. The independent status checker does not infer distinct root causes.
- Two Label Studio captures (`labelstudio-c5-150711`, `labelstudio-c5-152215`)
  each contain 117 research-category records, including 79 authentication records:
  **38 product HTTP responses**, plus **67 infrastructure-error records**.
  Independent analysis reports zero semantic observations/violations and zero
  server 500s; 17 responses have undeclared status codes (9 symptom groups),
  which are not asserted to be confirmed product bugs. Producer summary: one
  completed story and 72 setup failures. The second capture is an extra run,
  explicitly outside the registered comparison budget in RUNS.md.
- Cycle-5 TRIAGE.md classifies Paperless enum-as-reference and Homebox empty-copy
  checks as tool false positives. They must not become acceptance targets for
  positive semantic detection. Its six confirmed root causes are all 5xx-only.
- Complete Homebox/Paperless story ZIPs were not available in the inspected
  results directories. Direct reproduction analysis is not a full story replay.

**Outstanding:** original Library Provengo B1/B2/B4 traffic is still absent from
our uploaded compact artifacts. Therefore recovery of the recorded 10/8/19
Oracle occurrences is **not yet verified**. Query tests use representative extra
parameters, not an invented reconstruction of those original HTTP records.
The conservative intervening-mutation and readback requirements may still limit
recovery; coverage must be checked on the actual traces before changing them.

## Obtain existing raw evidence without rerunning anything

`collect_replay_raw.py` selects the latest B1/B2/B4 and baseline traces for one
configuration from a replay summary. It packages original raw HTTP, their recorder
requests and the contract, with hashes. It never reads oracle verdicts to select
individual requests. It refuses overwriting an archive and caps input at 384 MiB.

```powershell
$replay = Get-ChildItem .\library\benchmark-v001 -Directory -Filter 'analyzer-replay-*' |
    Where-Object { Test-Path (Join-Path $_.FullName 'replay-summary.json') } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $replay) { throw 'No replay summary found.' }
$zip = Join-Path "$env:USERPROFILE\Downloads" ('provengo-raw-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.zip')
& .\library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe `
    .\tools\natchan-box-v009\collect_replay_raw.py `
    --runs-root .\library\benchmark-v001\runs `
    --replay-summary (Join-Path $replay.FullName 'replay-summary.json') `
    --contract .\library\benchmark-v001\openapi.json --output $zip
if ($LASTEXITCODE -ne 0) { throw 'Evidence collection failed.' }
Write-Host "UPLOAD THIS FILE: $zip"
```

## Analyze a story package

Use the exact contract corresponding to its `contract_sha256` and a new output:

```powershell
python .\tools\natchan-box-v009\review_stories.py `
    --evidence <existing-story-package.zip> `
    --contract <matching-contract.json> --output <new-output-directory>
```

This is entirely offline. `story-review.json` separates producer check candidates
from independent results; `analysis/coverage.json` contains ingestion and
abstention counts. The original package, sampling and baseline evidence are preserved.
