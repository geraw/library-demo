# Gateway contracts v1 — completed stage 1

## Boundary

Gateway API version: `natchan-gateway/1`. Gateways are in-process Python adapters registered in code. They do not act as network proxies. Evidence envelopes use `natchan-evidence/1`; new contract/presence fields are additive. Input manifest remains version 1.

The two dimensions are independent:

| Tool gateway supplies | Product gateway supplies |
|---|---|
| Native record kind and original metric meaning | Product operation and resource mapping |
| Original role, including imported claims | Lexical resource IDs with explicit mapping limitations |
| Supported recorded formats | Existing versioned semantic provider reference |
| Evidence requirements and unsupported capabilities | Product evidence requirements and unsupported capabilities |

The core owns event IDs, run IDs, source artifact/line references, scope, ingestion status and raw payload. A tool gateway cannot overwrite those fields. The product gateway cannot assign a native result. No gateway requires a paired gateway ID. No adapter is selected merely from a tool/product display label.

## Declaration and negotiation

Each implementation supplies `id`, `contract: GatewayContract` and its interface method. `GatewayContract` includes:

- `dimension`: tool or product; enforced when selecting a registered gateway.
- `capabilities`: explicitly supported capabilities, not inferred from a product/tool name.
- `required_artifacts`: missing labels make run ingestion incomplete, even when the manifest omitted them.
- `optional_artifacts`: understood optional inputs; not an assertion that evidence exists.
- `evidence_requirements`: documented requirements for meaningful use.
- `limitations`: unsupported conclusions and evidence constraints.

Required artifacts are the union of both contracts. Unknown labels remain hashed artifacts. Undeclared/unknown gateways fail before reading the archive. The contract describes ability; artifact references and per-event availability describe actual evidence. A declared capability never guarantees that the run exercised it.

Run output includes `gateway_contracts.tool` and `.product`. Inspect the catalog independently:

```text
python tools/natchan-v002/gateways.py
```

## Record outputs and errors

`ToolGateway.normalize(label, record)` returns an allowed event kind, a string role, its own gateway ID, and explicit native interpretation. Optional native metric/value preserve original units. Unsupported envelope keys are rejected. The fixed Java adapter recognizes a verdict only when `native_pass` is boolean and a case ID is supplied; unknown/malformed native records stay uninterpreted.

`ProductGateway.describe(record)` returns its gateway ID, mapping status (`mapped`, `unmapped`, `not_http`), operation or null, entities array and rules array. The Library implementation maps its public resource paths and references the preserved Ledger. Its describe method performs path mapping only. Its optional evaluate method now delegates to the preserved case-local checker; ingestion remains separate.

Core validates outputs on every record. A plugin exception or invalid output adds `gateway_record_error`, marks ingestion incomplete, and preserves the original payload/source with fallback unknown mapping. No exception is interpreted as a bug. Missing HTTP fields are listed under `evidence_availability`; a null response is recorded presence, not proof of a complete readback. Partial evidence is not discarded, and availability is not correctness.

## Supported today

| Gateway | Required inputs | Implemented capability | Explicit limit |
|---|---|---|---|
| recorded-json-v1 | None | Common recorded JSON, HTTP/execution envelopes | No native format interpretation |
| provengo-fixed-java-v011 | native_jsonl | Recorded fixed-Java pass Boolean and case | Failed tests do not establish unique bugs |
| opaque-product-v1 | None | Preserve evidence without product interpretation | No product semantics |
| library-issta-v006 | trace | Resource/operation mapping, semantic provider reference | Unverified path ID; semantic evaluation available separately through preserved checker |

RESTler/EvoMaster native implementations and additional product mappings remain planned work. Their existing v001 analysis code remains available. Stage 1 completes the extensible contract and its enforcement, not every future gateway implementation.

## Acceptance demonstrated

All four combinations of currently registered tool/product gateways select without pair-specific logic. A custom tool and a custom product can be registered independently. Invalid dimension, undeclared contract, missing required input and invalid plugin output are tested. Source preservation and unknown states are retained. Full test suite: 18 passed. Real Library work ZIP: 3 arms, 542 native records each, 30,678 events, zero ingestion issues. No new SUT execution or bug-detection claim.

Future requirements can add versioned gateways/capabilities. Incompatible envelope/API changes require a new version and migration adapter; do not silently reinterpret historical payloads.

## Semantic provider connection

A product declaring `semantic_evaluation` must supply `evaluate(events, artifact)`. Selection enforces that method. The Library implementation returns the preserved case-local report via `library_bridge.py`; core `analyze.py` supplies only that run's declared trace events. Source line numbers are preserved, representation hashes are distinct, and imported verdicts are recomputed. This optional method adds no tool/product pair dependency. See README for analysis commands and full legacy parity evidence. Current suite: 26 tests passed.
