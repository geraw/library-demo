# Standalone Library observer v001

This entry point exposes the existing v006 observer unchanged. It is a Library-specific experimental oracle, not a generic OpenAPI validator or an importer for tool reports.

## Files and dependencies

- `observer-v001/Start-Library-Observer-v001.ps1`: standalone foreground launcher.
- `campaign-v006/observed_server_v006.py`: HTTP adapter, in-process SUT host, state ledger and semantic rules. Standard Python libraries plus the SUT's Flask dependencies.
- A frozen `sut_buggy_issta.py` from a campaign directory, with its `BUGS` interface. This is the SUT under test, not the original unversioned server.
- Repository `.venv/Scripts/python.exe` with the same dependencies used for previous campaigns.
- Optional `campaign-v009/resample_split_v009.py::counts`: experiment summary of first clean candidates; not required to run the observer and not a final bug score.

No Provengo, RESTler, EvoMaster, Java or OpenAPI file is required merely to run the observer. Generators have their own requirements.

## Start

From the repository root in PowerShell:

```powershell
& .\library\ess-experiment\observer-v001\Start-Library-Observer-v001.ps1 `
  -SutPath '.\library\ess-experiment\runs\issta-business-v004-20261019-225558\sut_buggy_issta.py' `
  -Bugs '1,2,3,4,5'
```

Default is `-Bugs 'none'`. Other supported launcher groups: `1,2,3,5` and `4`. The underlying Python CLI accepts other comma-separated subsets supported by the SUT. The launcher prints URL and fresh output directory; it stays in the foreground. Stop with Ctrl+C. Port 23243 must be free; do not simultaneously run the managed campaign scripts on the same port.

In a second terminal, start a case. This resets the server and verifies four empty collections:

```powershell
$base = 'http://127.0.0.1:23243'
Invoke-RestMethod -Method Post -Uri "$base/__campaign__/case" `
  -ContentType 'application/json' -Body '{"case":"manual-001"}'
```

Then point the generator at this base URL. For a new independent scenario call the case endpoint again with a new label. For a continuous fuzzing session use one case boundary at the start; do not reset between individual dependent requests. Before initialization requests are logged but semantic checks are inactive.

## Manual example: existing-book read

```powershell
$user = Invoke-RestMethod -Method Post -Uri "$base/users" `
  -ContentType 'application/json' -Body '{"name":"Observer Reader"}'
$book = Invoke-RestMethod -Method Post -Uri "$base/books" `
  -ContentType 'application/json' -Body '{"title":"Observer Book","author":"Observer Author"}'
try { Invoke-RestMethod -Method Get -Uri "$base/books/$($book.id)" } catch { $_.Exception.Message }
```

With bug 4 enabled, inspect the `verdict` row for `EXISTING_BOOK_READ`. With `none`, that particular sequence should produce no verdict. This is an explicit oracle demonstration, not a generator discovery experiment.

To inspect the log, use the printed absolute path:

```powershell
Get-Content 'FULL_PATH_TO_http.jsonl' | ForEach-Object { $_ | ConvertFrom-Json } |
  Where-Object { $_.role -in @('verdict','observer_error','boundary') } |
  ConvertTo-Json -Depth 30
```

## Inputs from each generator

All three generators supply the same interface: HTTP method, path/query, headers and optional JSON body. The observer receives the response by dispatching to the SUT. It receives no tool report, Java class, sample file, RESTler grammar or EvoMaster generated test. Configure the generator's target endpoint to the observer URL. OpenAPI and generated grammars/tests remain generator inputs. Tool-native logs and failures must be collected separately by the campaign runner. The observer does not infer which generator sent a request; record one tool per output session and preserve its configuration externally.

## Algorithm and rules

1. Import the specified Flask SUT, select bug switches, and dispatch through `app.test_client()`. No separate backend TCP server is used. `--backend-port` is a retained unused compatibility argument.
2. On a case boundary, call `/reset`, clear expected state, loan history and taint, and verify `/users`, `/books`, `/loans`, `/holds` are empty.
3. Forward each incoming tool request and log its decoded JSON request and response/status.
4. Track entities acknowledged by a 201 response containing an ID. Expected records come from the actual returned objects, not a complete independently implemented reference SUT.
5. For a loan creation, normalize integer IDs; require known user/book and no current loan of that book. A non-201 response to such a request yields `VALID_LOAN_REJECTED`, with active-loan count and prior successful pair-loan count. History increases only on a successful legal loan.
6. For successful deletion, remove the addressed record in the ledger; loan return addresses `(userId,bookId)`. Removing additional records in the actual server is detected by readback.
7. For GET `/books/{id}`, if the book is already known, require status 200 and an equal object; otherwise emit `EXISTING_BOOK_READ`.
8. After POST/DELETE, including rejected writes, independently read the affected collection and compare full records sorted by ID. User/book deletion triggers readback of all four collections. A mismatch yields `STATE_MISMATCH`; unavailable or non-list readback yields `READBACK_UNAVAILABLE`.
9. First violation has `prefix_tainted:false`; later verdicts have true until reset. This prevents treating cascading consequences as independent clean discoveries. Observer exceptions emit `observer_error` and also taint the prefix. Tool execution continues after a verdict.

## JSONL output

One JSON object per line, with `time_ns` (wall-clock nanoseconds):

| role | Meaning |
|---|---|
| startup | SUT, bug group, process and transport |
| boundary | Case label, reset and verified empty state |
| tool | Incoming tool request, status, decoded response and body metadata |
| oracle | Additional collection readback issued by the observer |
| verdict | Violations, triggering response and prefix taint |
| observer_error | Oracle implementation error; not a SUT bug finding |

Readbacks are extra SUT calls, distinct from tool requests. They do not supply IDs or observations to a generator. Responses are JSON-decoded/re-encoded by this adapter; this is not a transparent wire-level reverse proxy. The observer is synchronous and adds runtime overhead before responding.

## Scope and interpretation

The rules are manually implemented domain knowledge; they are not derived automatically from OpenAPI, stories or bug text. The same oracle code is used for all generators. Generator-native detection must remain separate from observer detection. `VALID_LOAN_REJECTED` is a generic rule; downstream summaries use counts to label bug-1/bug-2 candidates. Likewise DELETE state mismatches suggest bug-3/bug-5 candidates. These are diagnostic candidates, not automatic proof of five distinct bugs.

The ledger is partial: it trusts successful creation response fields, does not comprehensively validate arbitrary GETs, updates, authorization, all errors or all domain rules. It does not fully model legitimate cascades on user/book deletion; such mismatches need manual/control analysis. Absence of a verdict is not proof of correctness. Always compare the same scenario on the healthy control, review the first clean violation and native tool evidence, and distinguish an observer failure from a SUT failure.

Execution is serial and intended for logical sequences, not concurrent backend operations or real-time race detection. Fresh empty boundaries are required; existing server state is not imported. This version supports the specific Flask Library fixture only, not arbitrary deployed servers.
