# Raw HTTP input and server-log interface

The analyzer consumes already retained traffic; it does not run tools or a gateway, replay traffic, configure SUTs, or inject business hints into test generation. Capture at the producer/tool boundary. Do not claim a native tool option exists merely because this input format can express it.

## Canonical capture

`http-evidence.json` uses `natchan-http-evidence/1`; see `schemas/http-evidence.schema.json` and the example. Root metadata: `sut`, `tool`, optional actually observed `sut_version`, `contract_sha256`, `api_base_path`, seed. Each ordered exchange has:

| Field | Meaning |
|---|---|
| `method`, `path` | Actual HTTP method and path/URL, not a templated endpoint |
| `input`, `response`, `status` | Full parsed JSON or retained text bodies and real status; null/0 means no response |
| `actor` or `session` | Stable opaque authentication principal/session within the run |
| `epoch` | Reset boundary; never group independent clean SUT states together |
| `case_id` | Optional test/sequence boundary; absent means one ordered stream |
| `request_id` | Actual correlation identifier, when captured |
| `t_utc` | Actual timezone-aware timestamp, when captured |

Producer facts, bug IDs and pass flags are ignored by this raw adapter. A nested `request: {method,url/path,headers,body}` and `response: {status,body}` representation is also accepted. Body strings containing JSON are parsed. Canonical JSONL is accepted as `traffic.jsonl` with companion metadata. Record provenance is zero-based; RESTler raw provenance points to the original Sending line. The original file/member SHA256 is retained.

Without actor identity, same-actor semantic controls cannot be established. A recorded `default_actor` is permitted for a capture known to have one principal, but is explicitly marked as capture-declared metadata. Do not apply it to mixed credentials. Request Authorization can be hashed into an opaque actor if not redacted; already-redacted credentials cannot establish identity. Do not expose tokens for the sake of the analyzer; prefer opaque actor IDs recorded before redaction.

Keep/reset `epoch` on SUT reset and separate interleaved tests using `case_id`. The analyzer cannot recover unrecorded concurrency or reset boundaries. A URL prefix is removed only on an exact `api_base_path` boundary; `captured_path` remains available for original-path/log provenance. Routes in the semantic profile must use the resulting canonical path.

## Metadata and packaging

A ZIP can contain one or more `http-evidence.json`, `traffic.har`, `traffic.jsonl` or RESTler network logs, optional `traffic-meta.json`, `story-semantics.json`, `sut.log` or `server-log.jsonl`. Standalone raw files use `configuration.traffic_metadata` for external metadata. Do not provide both embedded and external metadata. Inline and companion values must agree where both specify sut/tool/version/contract. Run versions absent from evidence remain unknown, even if a request names an expected version.

Each capture file is an isolated sequence. No HTTP identities are borrowed across files/epochs. If a tool splits one logical sequence across files, the producer must export a single properly ordered capture with original source mapping instead of assuming the analyzer will reconstruct order. Retain the original native logs separately.

HAR uses `log.entries`, request/response bodies, optional `_actor`, `_case_id`, `_epoch`, `_request_id`. Base64 response content is decoded when declared. Server-clock and capture-clock assumptions must be documented before enabling time joins.

The metadata example contains a `<SHA256 ...>` placeholder: replace it with the exact contract hash, not that literal string. Missing or mismatched contract binding disables configured semantic comparisons with an explicit gap. Generic HTTP error analysis still remains available.

## Native RESTler

Adapter `restler-network` reads timestamped `Sending: <Python repr string>` / `Received: <Python repr string>` network log records. `ast.literal_eval` reads data only; messages must be strings/bytes. HTTP/1.x method/path/status/headers/body are parsed. Unpaired or interleaved sequences are not arbitrarily associated. Once a stream is ambiguous, subsequent pairing is conservatively withheld. Multiple network files remain separate streams.

Official format sources checked 2026-10-27: [messaging.py](https://github.com/microsoft/restler-fuzzer/blob/main/restler/engine/transport_layer/messaging.py), observed Git blob `9fd4d532c2986805f7848dabbc738dd4af5b1a41`, emits `Sending: {message!r}` and `Received: {response.to_str!r}`; [logger.py](https://github.com/microsoft/restler-fuzzer/blob/main/restler/utils/logger.py) supplies timestamps and per-thread network logs. This is format verification, not execution of a user campaign.

Fuzzing summaries/console/generated test code do not contain equivalent exchange evidence and are explicitly unsupported by this reader. Chunked or compressed native bodies are currently withheld with `RESTLER_HTTP_BODY_ENCODING_UNSUPPORTED`; their real status remains visible. Export decoded JSON/HAR bodies to enable semantics for such responses. HTTP/2 or other native logger grammars need a new explicit adapter/version; no heuristic fabrication is used.

## Server correlation

Optional `sut.log` / `server-log.jsonl` records use:

```json
{"request_id":"r17","method":"PATCH","path":"/api/v1/items/17","status":500,"timestamp":"2026-10-27T10:00:00Z","message":"database is locked"}
```

Configure `log_correlation` in the semantic profile:

```json
{
  "allow_time_join": false,
  "window_seconds": 2,
  "signatures": {"database_lock": "database is locked"}
}
```

A text format can instead use `structured_regex` with named groups `request_id`, `method`, `path`, `status`, `timestamp`, `message`. There are no implicit product-specific text patterns. A unique request-ID match wins only when supplied method/path/status do not contradict the HTTP row. Optional time joins require all three fields, aware timestamps, and uniqueness in both directions within the configured window. Normalized and captured paths are both accepted for joining.

Unparsed or ambiguous lines never become causal matches. Attached signatures are server-reported context; `root_cause_proven` remains false. A 5xx with a uniquely associated configured signature receives `HTTP-LOG-ERROR-CORRELATION`. The log statement may still describe a symptom rather than the actual cause.

## Comparing tools

Report native faults/native failed tests and common raw-HTTP candidates in separate columns. Missing raw captures produce **unavailable**, not zero common findings. Matching captures, semantic metadata, actor/reset policy and oracle controls are required for a defensible common-judge comparison. Re-labeling identical fixtures checks origin neutrality; it does not establish that real tools reached identical states or validate a live capture mechanism.
