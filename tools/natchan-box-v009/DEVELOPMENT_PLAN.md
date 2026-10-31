# v009 implementation plan and acceptance gates

Base: operational v008 at `6310af7baecc25fc46692d1127c80dbc1da4247d`. Never mutate that release.
Current build `009-dev.3` is a development checkpoint, not the final semantic-judge release.

## Gate 1 — independent context and bounded S7 (implemented)

- New contract-only input/knowledge/freeze boundary, independent from all producer profiles/catalogs.
- OAS 3.0/3.1 and Swagger 2 JSON, pointer-addressed field/operation facts, conservative ambiguity.
- HTTP JSONL, research journal, bounded HAR; same status judge for every tool label.
- S7 status-only candidates and symptom grouping, unique structured log-ID joins, explicit limits.
- Determinism, malformed evidence, input mutation, freeze drift, no-producer-verdict and 90,000-record controls.
- Legacy v008 regression unchanged. No legacy product-finding recall is claimed by this milestone.

## Gate 2 — entity bindings and S1/S2/S3/S5 (partially implemented)

- Dev.2 implements same-item-URI PUT/PATCH/GET scalar bindings, S1, bounded S3 and S5 observations.
  Capture assumptions, mutation invalidation, missing evidence and budget limits are explicit.
  S2, creation bindings, arrays/nested values, full schema validation and product atomicity guarantees remain open.
- Independently derive same-resource read/write bindings and identifier extraction; evaluate only bindings
  justified by public contract declarations. Candidate relations cannot silently become facts.
- Establish object identity, actor/authorization scope, start/reset epoch and observation ordering from raw capture.
- Distinguish request-start order from response-completion order. Overlapping intervals are not a serial history.
- For S1 require suitable synchronous write and later read, declared field semantics, no intervening applicable write,
  no reset, and no unaccounted actor/visibility change. Async/eventual behavior needs declared semantics or abstention.
- For S2 compare equivalent fields, constraints and request preconditions, not merely equal values or same field names.
- For S3 validate applicable schema semantics; unsupported compositions/formats abstain. Distinguish acceptance,
  rejection and demonstrated storage of the invalid value.
- For S5 reconstruct before/after state; distinguish changed/kept/other and omitted snapshots. An error response alone
  does not prove rollback. Without an applicable atomicity requirement, report observed commit as policy observation
  or candidate with the missing semantic assumption, not as a proven contract violation.
- Add paired valid/invalid/missing/interleaved examples for every rule; tool-name invariance and exact witnesses.
- Refine input classes beyond coarse body shapes, without producer test names or known defect signatures.

## Gate 3 — S4/S6 and producer packaging (not implemented)

- Contract-derived reference/placement bindings with declared semantics and evidence-established prerequisites.
- Handle tombstones/historical references, identifier reuse, pagination and permission changes explicitly.
- Bounded toolkit outer/inner ZIP extraction to the independent raw capture route; refuse unsupported shapes with 3.
- Register original and tool-normalized contracts and validate their normalization provenance.
- Support larger HAR by streaming or preserve the explicit documented refusal; benchmark real retained packages.
- Continue to refuse labels/oracle answers as truth. Auxiliary snapshots may be parsed as raw observations only
  if their identity, order and provenance can be established independently of an oracle's verdict.

## Gate 4 — validation and promotion (not performed)

- Development evidence from Gitea, Vikunja and Library is retrospective, never headline held-out evidence.
- Run the reference-set recall, independently adjudicated precision, negative controls, abstention rates and agreement.
- Keep known-bug matching a separate optional post-judgement layer, excluded from the blind semantic decision.
- Freeze/register before a new evaluation cycle; promote only after producer end-to-end acceptance and held-out protocol.
- Never infer zero bugs from missing captures or an unsupported class. Count occurrences, symptom groups and confirmed
  bugs separately. A shared signature is not a proven shared root cause.

## Requirements clarifications recorded for research review

The original [requirements](RESEARCH_REQUIREMENTS.md) were copied unchanged. The following are conservative
implementation interpretations, not silent edits to the study protocol:

- P3 freezes static derivation/rules; facts about a resource created in the current traffic are dynamic evidence.
- P6 applies to canonical output artifacts; current route excludes timestamps and local paths entirely.
- K5 schema `$ref`, naming and URL nesting are candidate cues, not proof of foreign-key integrity.
- S1/S2/S4/S5 need explicit preconditions described above to avoid false positives.
- O2 first groups symptoms; root-cause/bug identity remains unproven without further evidence.
- V4 producer “pass” is not a negative-control truth label: independently establish the correct observed behavior.
- Coverage denominators for future classes count defined opportunities, not every HTTP exchange seven times.

Do not tune the next cycle on held-out evidence. New rules prompted by evaluated evidence belong to a subsequent freeze.

## Dev.3 producer review checkpoint

R1/R2/R3/R4/R6 are addressed in REVIEW_RESPONSE_20261101.md; six original contracts derive/freeze.
R5 (independent S2 create/update comparison) is the next semantic priority and remains null in this version.
No product-specific exception was added for a known false positive, and no run result was used as a judge answer.
