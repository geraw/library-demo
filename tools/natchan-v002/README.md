# Natchan v002 — stage 1 evidence and gateways

Offline evidence import, based on the historical reuse plan. Python 3.9+ standard library only. No generator or HTTP execution. Existing v001 analysis commands and their scores are unchanged.

## Two independent gateway dimensions

| Interface | Responsibility | Current implementations |
|---|---|---|
| `ToolGateway.normalize(label, record)` | Translate a tool's retained record, preserving native metric meaning and source evidence | Generic recorded JSON; Provengo fixed Java v011 recorded test-pass boolean |
| `ProductGateway.describe(record)` | Translate product operations and entities and identify the existing semantic rule provider | Opaque product; current Library resource/path mapping and preserved Ledger provider reference |

Registries `TOOLS` and `PRODUCTS` in `gateways.py` select gateways explicitly by versioned ID, independently of display labels `tool` and `system`. Unsupported IDs fail before import. Unknown display labels remain usable through opaque/recorded gateways; unsupported native files are inventoried without fabricated interpretation. New implementations can implement the protocols and register an ID without changing the other dimension or ingestion engine. This is an in-code registration API, not dynamic execution of modules named by an input archive.

The Library gateway maps recorded public resource paths only. It does not invent business rules or assert that a 404 is a defect. Rules remain in the preserved semantic checker. This stage does not execute them. RESTler/EvoMaster native gateways and other product mappings remain subsequent work; existing v001 native readers still work separately. No claim of full three-tool normalized ingestion is made here.

Archive layout is a separate concern: `--library-v011` declares the known three-arm archive layout and the two gateways, and checks native record counts against `completed.json`. It does not infer the layout from a product name. A generic manifest can use different tool/product gateways in every run, with no pairwise tool×product gateway.

## Run on the work-machine archive

From the repository root:

```powershell
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\tools\natchan-v002\Invoke-Natchan-Import-v002.ps1 `
    -ArchivePath '.\library\ess-experiment\runs\java-fixed-split-v011-20261021-094721-5216-review.zip' `
    -LibraryV011
```

This requires the existing run ZIP at that path. The wrapper uses repository `.venv\Scripts\python.exe` when present, then `python`, or explicit `-Python`. Default output goes to `library/ess-experiment/out/` with a timestamp. Existing outputs are never overwritten. No packages need installing.

```text
python tools/natchan-v002/evidence.py --archive evidence.zip --manifest import.json --output new-evidence.json
python tools/natchan-v002/evidence.py --archive evidence.zip --output new-inventory.json
python -m unittest discover -s tools/natchan-v002/tests -v
```

Input manifest remains compatible with the v001 run inventory shape:

```json
{
  "schema_version": 1,
  "runs": [{
    "id": "run-1",
    "tool": "provengo",
    "system": "library",
    "tool_gateway": "provengo-fixed-java-v011",
    "product_gateway": "library-issta-v006",
    "artifacts": {
      "trace": "control/http.jsonl",
      "native_jsonl": "control/native.jsonl",
      "execution_json": "control/java-suite-execution.json"
    }
  }]
}
```

Manifest artifact values here are exact ZIP member locators, not local filesystem paths (the v001 analyzer uses local paths). Nested locator example: `collection.zip!/campaign/http.jsonl`. Artifact labels other than trace/native_jsonl/execution_json are retained and hashed without decoding. Native log and bucket parsing remains with existing native readers until their gateway migration. Missing run mappings yield inventory with explicit incomplete status.

## Evidence envelope v1

See `evidence.schema.json`. Sources retain outer ZIP SHA256, exact member locator, member hash and one-based record line (null for whole-file execution JSON). Raw payloads are preserved; reports have the same sensitivity as source evidence and are not automatically redacted. Never treat a serialized artifact/member link as permission to fetch or execute it.

- `artifacts`: available, missing via run null reference, invalid, limited, ambiguous or rejected; hashes for successfully read members.
- `runs`: independent identities, tool/product gateway IDs, input metadata, artifact references, ingestion completeness.
- `events`: tool-normalized kind/role, product mapping, explicit case scope and original payload. No new native fault metric is calculated. A recorded verdict is an imported claim.
- `findings`: reserved, empty in this stage; `summary.finding_count` is null because no semantic evaluation ran. A schema for future qualified findings will be versioned when that stage is implemented.
- `issues`: missing records, corrupt members, encoding, limits, contradictory case boundaries and unsupported evidence.

`complete` means the declared ingestion succeeded, not the test suite passed, the run was complete, or no bugs were found. Even a complete import may contain failed tests or nonzero tool exits; these are preserved payloads. Unknown case scope remains unknown. No cross-test reconstruction, native/common finding join or control qualification is attempted. Source payload IDs are not canonical entity identities until a product gateway supplies verified identity mapping.

## Historical reuse and bounds

Reuses the v001 three-arm artifact layout and manifest naming; retains its no-overwrite/unknown principles. Encoding logic follows Vikunja's BOM/BOMless PowerShell UTF16 repair. The gateways identify existing semantic providers rather than copying their rules. The generic TSE verifier and branch reconciliation are still separate planned work.

ZIPs are read without extracting files. Member paths, duplicate names, CRC/decompression errors and nested ZIPs are checked. Defaults: 10,000 members, 32 MiB per member, 256 MiB cumulative decompressed bytes, 2 nested ZIP levels, 100,000 events. These limits include nested archive containers and contents. Exceeding them yields incomplete evidence, never a clean result. Python callers can supply `Limits`; CLI tuning is deferred. Reports are deterministically ordered for a given archive; no wall clock is inserted.

Exit 0: ingestion complete. Exit 2: report saved with incomplete evidence. Invalid manifest/missing outer file is a command failure. A PowerShell wrapper throws after printing the saved report path for incomplete imports. This is the first stage implementation, open to additional requirements.

## Completed stage 1 contract

See [GATEWAY_CONTRACTS.md](GATEWAY_CONTRACTS.md) for the versioned two-dimensional API, capability negotiation, required evidence, output validation and error behavior. Run reports now include both contracts and per-event evidence availability. `python gateways.py` prints the registered contract catalog. The suite now has 18 passing tests.


## Connected Library evaluation

`analyze.py` adds semantic evaluation through the product gateway. It reuses the preserved `semantic-checker-v001` Library checker and Ledger without editing their rules. `evidence.py` remains ingestion-only. Run from the repository root:

```powershell
& .\tools\natchan-v002\Invoke-Natchan-Analyze-v002.ps1 `
    -ArchivePath '.\library\ess-experiment\runs\java-fixed-split-v011-20261021-094721-5216-review.zip' `
    -LibraryV011
```

Python and repeatable compatibility validation:

```text
python tools/natchan-v002/analyze.py --archive evidence.zip --library-v011 --output new-analysis.json
python tools/natchan-v002/validate_connection.py --archive evidence.zip --output new-parity.json
```

A generic manifest selects `product_gateway: library-issta-v006` with its trace artifact; it does not require the Provengo tool gateway. This allows the shared semantic provider to consume correctly scoped evidence from another tool while keeping native decoding independent. Without a semantic provider the run stays NOT_EVALUATED. `--control-run RUN_ID` explicitly requests case-ID comparison; the Library layout supplies `control` automatically. This is catalog pairing, not causal confirmation or input-equivalence proof.

The analysis envelope (`natchan-analysis/1`, `analysis.schema.json`) contains the original ingestion envelope, one semantic report per run, external observation occurrences with exact source-event and same-boundary context references, native results and optional healthy-control comparison. The import envelope schema is unchanged. Original trace/member hashes and the separately re-serialized adapter-trace hash are retained; they are never substituted for each other. Preserved evaluator source and rules-manifest hashes are recorded. Serialized old verdicts remain imported claims and are ignored by the evaluator.

Raw event data is retained, so analysis reports have the sensitivity of the original evidence. Semantic verdicts depend on complete ingestion, recorded verified-empty case starts, ordered readbacks and the existing taint rules. A repeated case ID never joins observation contexts across boundaries. Missing evidence is incomplete, not clean. Native flags are separate from external observations. Twenty-two candidate occurrences are not twenty-two unique bugs. Confirmed unique-bug count remains unknown; this connection adds no automatic bug confirmation.

Validation: 26 unit tests passed. Full reports on all three work-archive arms match the direct preserved checker exactly (excluding adapter-specific provenance fields), all archived candidate cases match, original input hashes verify, and native failed-case lists match. Each arm has 542 evaluable cases. Business-four has 22 candidate cases for bug 5; five native failing tests passed control, while two native failures already occurred on healthy control. See CONNECTION_VALIDATION_20261021.json. This is offline reanalysis; no new SUT execution. PowerShell wrapper is source-reviewed here, not executed on Windows.
