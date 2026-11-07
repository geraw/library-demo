# Known bug and generic pattern format

The existing versioned format is `natchan-catalog/1`; the predicate implementation
is reused from `../natchan-v003/classifier.py`. Each JSON document has an `entries`
array. Each entry requires:

| Field | Meaning |
|---|---|
| `id` | Stable identifier: known issue ID or generic pattern ID |
| `kind` | `known_bug` or `pattern` (observations such as O04 retain their historical IDs; kind means known signature, not severity) |
| `product` | Exact product, or `*` only for generic patterns |
| `versions` | Explicit tested versions for active known signatures |
| `status` | `active` or `draft`; drafts cannot classify |
| `all` | All required fact predicates; no unconditional rules |
| `exclusions` | Any matching predicate disqualifies the match |
| `evidence_requirements` | Required request, readback, context or log witnesses |
| `provenance` | Historical definition and source revision |
| `severity` | Suggested severity or `requires_context`; never inferred from HTTP alone |
| `human_review` | Whether contextual judgment is still needed |

Predicates have `fact`, `op`, `value`. Supported operators: `eq`, `in`, `gte`,
`present`. Dotted paths inspect nested facts. Adding a predicate does not create
its evidence: a gateway must supply the required measurement and the analyzer
must compute the fact. Missing facts fail the predicate; they do not mean false
or a passed test.

Examples: `VIK-F05` needs an accepted write plus same-resource readback showing
loss of the seventh non-prefix color character. `GIT-C8` needs an accepted stored
release target, the same target carried into a later rename, and an unambiguous
matching missing-object server error. A generic 500 matches neither by itself.

For a new product, implement product identity/schema semantics in `tse_products.py`
and supply explicit version metadata in the manifest. For a new producing tool,
add a gateway in `tse_gateways.py` that preserves its original artifacts. Neither
adapter should infer a bug ID from a scenario name. Preserve old oracle outputs
separately; do not re-label them as independent confirmation.

The source position `record` is zero-based. ZIP member SHA256 and archive SHA256
are distinct; run source hashes identify exact input files. Server log line
numbers are one-based. Log correlation is method/path/status/time based, with a
unique join in both directions and one adjacent error, never a guessed request ID.

Normalization and acceptance of control characters are observations that may be
intentional. A `known_bug` catalog entry with an O-prefixed historical ID is a
known **observation signature**, not a decision to promote it to a defect.
