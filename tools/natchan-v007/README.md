# Retrospective validation v007

This offline audit reuses the original Mealie receipt adapter, classifies its recomputed observations with the v006 catalog and corrected v005 candidate matcher, and runs isolated historical semantic regressions. It makes no SUT requests.

```powershell
python .\tools\natchan-v007\retrospective.py --history .\natchan-history --output .\retrospective-new
```

Requires Python 3.10+, pytest for development regression checks, and the historical source archive/cache listed in the summary. Historical private evidence is not bundled with public code. An existing output directory is rejected. Missing inputs fail visibly. The source archive is hashed; per-record member hashes are retained in full reports. Filename inventory is not a claim of complete evidence discovery, and does not inspect nested archives recursively.

## Actual result

| System | Evidence exercised | Result | Remaining boundary |
|---|---|---|---|
| Mealie | Eight original receipts; 392 responses | 16 distinct error observations; four also show state change after error; same as previous classification | No qualified named F04/F05 assignment or root-cause confirmation |
| Historical Library, Garage, Pharmacy, NetBox, Todoist | Frozen profile regression suite | 29 tests passed | Fixtures are not historical campaign reanalysis; Todoist is diagnostic only |
| Immich | Archived causal-prefix and concurrency tests, matched archived engines | Three tests passed | Current product gateway and original campaign analysis remain unverified |
| Mealie historical evaluator | Intervening-write safeguards | Two tests passed | Separate from current classifier end-to-end integration |
| Generic historical evaluator | Empirical update/delete tests | Six tests passed | Not six product bugs |
| Keycloak | Archive member inventory only | Not evaluated | Need original HTTP/identity/interval evidence and matching adapter |

The current Gitea/Vikunja reports remain in v005/v006; they are not silently rerun or added again here. The current Library archive parity remains separately recorded. Raw receipt reanalysis and synthetic regression results must not be merged as one coverage count.

## Readiness decision

The shared classifier remains usable for supported evidence contracts. These checks do not establish universal readiness for a new product. Before accepting a new product, require: a versioned product gateway, original request/response evidence, explicit case/reset and identity/resource scope, readback/state witnesses needed by each oracle, known-bug definitions qualified by version, positive cases and healthy/insufficient-evidence controls. Missing evidence must remain unknown. Keep native-tool findings separate from external classifications.

Mealie is supported here for generic response/state-change observations. Immich and Keycloak are not yet end-to-end supported by the current analyzer. Additional original archives or access to their retained run directories is necessary to close that validation gap; code tests alone cannot do so.

Counts in the summary deduplicate (observation ID, pattern ID). Multiple assessment rows may reference one observation; summing their pattern lists would incorrectly turn 16 errors into 20 and four state-change witnesses into eight. The public summary contains no raw credentials or response bodies.
