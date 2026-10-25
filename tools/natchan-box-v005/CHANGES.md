# v005 changes

Parent analyzer: v004 at `f1d26cf65b5ee596a2297802ed2973daf4da0c15`. Only the new v005 directory is added; no experimental source, archive, catalog source or prior analyzer release is edited.

- Remove hidden `tse_products` import-order dependency from generic toolkit parsing; test in a fresh process.
- Recognize login outer packages, UTF-16 text, v1-login statuses and actual ENV version / run_seed / recorded_http_requests metadata.
- Bind filtered outer SUT logs by seed with byte provenance; count the configured lock regex without presenting filtered counts as full server coverage.
- Keep retry attempts separate from research-response counts and reported known IDs separate from verified catalog matches.
- Compare explicit roundtrip measurements and retained recovery-prefix bodies with conservative source bindings and explicit evidence tiers.
- Qualify database-lock joins by unique bidirectional method/path/status/time correspondence; preserve uncertainty and no-causality limits.
- Audit lossless `v`-prefix version aliases for existing catalog scopes while retaining literal observed metadata and original/effective catalog hashes.
- Propagate only explicitly recognized unsupported-format diagnostics as exit 3; preserve actual internal engine errors as exit 4.
- Inventory auxiliary login files; keep producer pass/findings/restore assertions descriptive unless independently checked.

Remaining: actual work ZIP acceptance, complete server logs, hidden full RT readback bodies, independent storage restoration proof and full business-semantic coverage of every login/recovery oracle. Input/output schemas and the adapter name remain unchanged.
