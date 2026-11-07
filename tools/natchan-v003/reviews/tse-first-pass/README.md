# Historical TSE reanalysis checkpoint

GitHub connection recovered on 2026-10-21; v003 published at eb225cd3faa87695c2f74673ced2de83c4c6d8e6. No user reconnection was required.

## Actual execution performed here

The original historical Mealie receipts in Mealie_Supervisor_Artifact_v003.zip were reanalyzed. Eight runs contain 392 recorded responses. Sixteen responses are 5xx; four household-control actions have qualified same-resource/same-owner ordered readbacks changing from two to three items after a 500. The generic classifier reports both server error and state change after error. Known-bug IDs remain empty because named Mealie definitions have not yet been qualified.

Existing historical comparison logic is reused unchanged from Mealie_Local_Observation_Tools.zip tools/audit.py. The caller improves temporal scope by selecting the nearest owner readback and checking unresolved intervening writes under the declared household-controls protocol. No HTTP, generator execution, retries, SUT restart or new experiment occurred. The JSON report retains source hashes/member names and normalized summaries; credential-bearing original receipt objects are not copied into it.

## Broader historical source readiness

| System | Accessible recovered material | Current readiness |
|---|---|---|
| Library | Original work v011 traces/native/control outputs | Full selected-run classifier validation already performed |
| Mealie | Original eight-run receipts and historical identity audit | First original-data classifier reanalysis performed here |
| Vikunja | v103 acceptance archive, control/snapshot/handoff packages and evaluator source | Identify and bind original execution/state evidence to each rule; summary/snapshot assertions are not fresh trace evaluation |
| Gitea | Stage6 evaluator fixes/triage source and recent trap package | Recover corresponding original run receipts and validate mapping; code/configuration alone cannot establish findings |
| Keycloak | v56 evidence coverage audit, v57 source and binding/readback modules | Separate sampled/static evidence from actual HTTP evidence before classification |
| Immich | Generic evaluator deltas and frozen replay-result artifact | Recover replay input trace/control manifests to recompute; do not treat an old evaluation JSON as a new verdict |

This table describes the selected sources already recovered in this workspace. It does not mean older runs elsewhere cannot be retrieved. Next work is progressive source recovery and adapter qualification for those cells, using historical evaluators instead of inventing new semantics. Multiple old runs can be analyzed offline without rerunning the products.
