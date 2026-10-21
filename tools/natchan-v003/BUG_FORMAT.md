# Describing a pattern or known bug

Start with examples/bug-template.json. Keep drafts outside the active catalog directory until ready, or leave status draft. Catalog files contain schema_version `natchan-catalog/1` and an entries array. The complete schema is catalog.schema.json; runtime also validates essential safety/identity rules.

| Field | Required meaning |
|---|---|
| id | Stable unique ID; do not reuse after changing the bug's identity |
| kind | pattern for a general/product-scoped phenomenon; known_bug for a specific known defect |
| title | Human-readable precise behavior |
| status | draft or active; drafts never match |
| product | Canonical product name, or * for generic patterns; explicit product required for active known bugs |
| versions | Exact applicable product/profile versions; empty means unrestricted for patterns; forbidden for active known bugs |
| all | Nonempty predicates that must all match evidence facts |
| exclusions | Predicates that individually veto a match |
| evidence_requirements | Human-readable prerequisites and evidence-source expectations |
| provenance | Source reference and verification statement; distinguish user specification from inspected code/live evidence |
| severity | Suggested severity or requires_context; not inferred real-world impact |
| human_review | Whether human review is requested; current catalogs always true |

Predicate example: `{"fact":"same_owner_non_target_removed","op":"eq","value":true}`. Dotted fact paths are supported. `present` tests availability, not truth. Missing facts never satisfy eq/in/gte. Exclusions and exact version scoping are important for false-positive control.

## Completed example: Library hold deletion

LIB-ISSTA-BUG-5 requires all of:

- product library, profile version issta-v006;
- resource holds;
- requested target demonstrably existed before cancellation;
- a non-target hold disappeared;
- the unintentionally removed hold belongs to the same reader as the target.

Its classification does not require a later 404 or a native failure. Those are separately retained consequences. A generic collateral-deletion observation can still be reported when owner/version evidence is missing, without assigning the known bug ID.

## Supplying new Vikunja/Gitea definitions

Provide the exact operation, resource, field, affected version, triggering conditions, observed result, expected rule with its source, and positive/negative examples. Specify whether evidence is required from response, independent readback, server log, paired experiment or serial/concurrent controls. Do not substitute a broad Internal Server Error string or a time window for those conditions.

For the pending F01/VIK-F04/C1/C2 records, the current files deliberately do not invent missing operation/field/version bindings. Existing generic/product-scoped patterns can classify symptoms and their combinations; the named-bug association remains disabled until the missing evidence is supplied and regression-tested.

A matching rule is a reproducible association under declared evidence assumptions. It does not independently prove a code-level root cause or that two previously unknown failures share that cause.
