# Measurements: product/tool gateway contract

Each measurement has `id`, `product`, explicit `product_version`, `run_id`,
`source` (artifact path/hash/position), `family` and the family's actual values.
The machine-readable required fields are in `PROVIDER_CONTRACT.json`; the JSON
schema is an interface guide. The Python evaluator checks required fields and
qualifications and rejects unsupported families. No external schema package is
required. Context flags are collector-produced measurements, not researcher
opinions or old oracle verdicts.

| Family | Required values / policy | Computation |
|---|---|---|
| RESPONSE | Status; optional transport error and documented statuses | HTTP server error, transport failure, status conformance |
| EDGE-1 | Status, submitted value, actual schema constraints | Explicit numeric/string bound accepted or rejected |
| RT-1 | Accepted status, sent fields, readback, readable fields, optional preimage/formats | Changed/dropped, truncation, normalization candidate, time change |
| ATOM-1-2 | Failed status, operation, preimage/postimage, requested changes | Per-field applied/kept/other; partial/committed/rollback; create duplicate; delete commit |
| EDGE-U | Same actual sent value on both paths, statuses, stored values when both succeed | Acceptance or storage divergence |
| KNOWN | Configured status/body/operation/window, observed trigger and request timestamps | Signature match; original failure is never suppressed |
| CASCADE-1 | Successful parent deletion, observable child read, explicit cascade policy | Child remains against policy |
| ADJ | Trigger/request timestamps and configured window | Qualified adjacency; never causal proof by itself |
| IDEM | Two actual requests, second status | Exact repeated write and error |
| VIEW | Expected/actual IDs, explicit membership policy | Required membership missing |
| LINK | Add/add-again/remove, target ID, complete observed IDs | Missing, duplicate or residual relation |

Stateful families require `context.same_run`, `ordered`, and `complete`.
`complete` means complete relevant fields/list pagination and the observation
window required by the experiment. RT/ATOM/IDEM/LINK additionally need
`same_resource`, `same_actor`, `no_intervening_write`. EDGE-U needs `same_pair`
and `compatible_preconditions`. CASCADE needs `relationship_verified`,
`actor_scope_verified`, `no_intervening_write`; ADJ needs `trigger_scope_verified`,
`actor_scope_verified`, `no_intervening_trigger`; VIEW needs `view_scope_verified`,
`actor_scope_verified`, `no_intervening_write`.

Independent readbacks and source-scoped producer readback values are different
evidence levels. Preserve that distinction in the source descriptor. A shortened
response is not a complete snapshot. A 403 is not proof of deletion. Create counts
must cover the same matching-item predicate and all pages. Timestamp comparison
uses explicit time zones and preserves submicrosecond precision.

Known-issue conditions require all their facts. HTTP 500 alone does not identify
a root cause. Known issues with missing witnesses stay insufficient; conflicting
observed facts exclude them. Kernel/provider findings are supplementary views of
the same events and must not be summed with primary findings.
