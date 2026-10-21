# g012 findings — 21 October 2026

## Evidence and run outcome

Archive: `g012-gitea-variants-20261021-203735.zip`, SHA256 `93bbd055a88a57b4bb0d612ab8c2c37b2e454c6e46a751c112eb940640dab1fa`.

Sixteen actual Provengo runs: two variants × two models × four seeds. **7,501 original HTTP requests; 83 HTTP 500 responses; all 83 uniquely correlated to their server error.** Original inner/outer summaries agree with independently counted raw HTTP.

| Variant | Model | Requests | HTTP 500 | Actual native outcome |
|---|---|---:|---:|---|
| 29.0.0+dev-175-g33610142c3 nightly | g003 | 1,848 | 9 | Four completed/SUCCESS |
| nightly | g009 | 1,947 | 17 | Four stopped at first native failure |
| 28.1.0 + PostgreSQL 16 | g003 | 1,848 | 43 | Four completed/SUCCESS |
| PostgreSQL | g009 | 1,858 | 14 | Four stopped at first native failure |

`G012_COMPLETE` and wrapper exit=0 mean the variant runner completed its work and packaging. They do **not** mean all native tests passed. All eight g009 native results have exit=1 and `actual 500, expected: [200]`. g003 traps permit 500 and therefore complete successfully despite observed server defects.

## Known behavior and what changed

| Signature | Nightly semantic analogs, outside current catalog versions | PostgreSQL 28.1.0 strict matches |
|---|---:|---:|
| C1 missing assignee | 10 | 9 |
| C2 missing/deleted/foreign milestone, including C2+ | 12 | 9 |
| C3 silently truncated issue title | 2 | 2 |
| C7 organization email create/update validation gap | 5 | 4 |
| C8 stored release target followed by failed rename | 4 | 4 |
| O1 milestone due-time end-of-day normalization | 2 | 2 |
| O2 familiar normalization | 3 | 3 |

The strict catalog remains pinned to 28.1.0. Nightly counts above recompute the same executable semantic predicates while explicitly withholding the version-qualified known-bug assertion. Predicates involving the contract retain the frozen-contract limitation.

**C8 persists in this development build and on PostgreSQL.** All eight g009 native stops are release-rename errors with an accepted earlier target write, a readback of that target, and a correlated missing-object error. This strengthens the earlier result: the retained observations are not limited to the original SQLite deployment or release build. It does not establish universal behavior across all configurations.

**C7 now has actual Provengo evidence on 28.1.0:** four g003 PostgreSQL matches, one in each seed, with actual same-value email bodies, compatible recorded preimage and email-related rejection. This closes the earlier report's missing native-run provenance for C7 in this batch. The analyzer identifies the semantic gap; Provengo did not fail natively on these permissive traps.

**C4–C6 remain untested here:** no release tag_name/target_commitish EDGE create/update probes were sent in any retained run. The g009 runs stopped before that coverage. Absence of matches is not evidence of a fix. g003 does not supply those Release probes.

## Additional PostgreSQL failure families

These are additional evidence-supported failure classes relative to the earlier SQLite cohort, not 35 independent new bugs and not yet assigned permanent C identifiers.

### PostgreSQL NUL rejection — 27 occurrences

The original payload contains NUL; the request returns 500 and the correlated handler error reports `pq: invalid byte sequence for encoding "UTF8": 0x00 (22021)`.

Affected entities: organization=7, team=2, label=4, issue=8, milestone=4, comment=2. Both create and update paths occur. The database rejecting NUL is expected backend behavior; the product issue candidate is API input handling exposing it as an internal error. No security exploit, data loss or crash of the server process is established.

This is distinct from C5: C5 is NUL in a Release tag reaching a Git subprocess; these events concern text storage and PostgreSQL encoding errors.

### PostgreSQL varchar limit — eight occurrences

The payload contains a 10,000-character value; the handler returns 500 and logs `pq: value too long for type character varying(255) (22001)`.

Four field/operation pairs: label.name (create/update), milestone.title (create/update), label.description (create/update), issue.ref (create/update). These eight failures demonstrate an API/backend boundary mismatch and inadequate error handling. They do not establish the exact accepted boundary at 255/256; no binary or adjacent-value boundary experiment was performed.

### Same-request SQLite comparison

All 35 PostgreSQL-family events have a unique prior SQLite 28.1.0 g003 counterpart with the same seed, session, action, logical ID, method and request body. SQLite returned 200/201 for 33, 422 for one and 500 for one (the latter has a different missing-assignee cause). Thus the additional classes are strongly supported by original request/log evidence; one old 500 changed failure class rather than adding a new error count.

The g003 overall change is 9 → 43 HTTP 500 responses, a net +34, not +35. This comparison is not a randomized database-only intervention: deployments differ in other recorded details. Backend-specific `pq` messages support the database association, not every causal inference about configuration.

Severity remains `requires_context`. These candidates deserve explicit validation/error-mapping review. No automatic high/security severity is assigned.

## Retained oracle measurements

| Measurement | Nightly g009 | PostgreSQL g009 |
|---|---:|---:|
| Atomicity partial field-state measurements | 13 | 10 |
| Atomicity rolled_back measurements | 4 | 4 |
| REF silently_dropped summaries | 24 | 23 |
| REF crash summaries | 9 | 6 |
| LINK-2 silently_dropped summaries | 53 | 51 |
| DIV response-class differences | 13 | 10 |

These rows overlap the HTTP failures and one another. They must not be summed as unique bugs. Applied/kept field states were recomputed to check the recorded atomicity verdict; full before/after bodies remain absent, so these are producer measurement evidence, not independent full-state reconstruction. C8 has the four rollback measurements in each variant, whereas partial measurements concern earlier issue/reference updates.

## Validation and next research step

Seven original-evidence checks passed: raw counts, native outcomes, strict version separation, PostgreSQL payload+log witnesses, actual C7 run provenance, atomicity evidence tiers and unique SQLite request matches. Source hashes remain in the compact JSON report.

A continuation or separately scoped execution of existing Release EDGE probes is needed for C4–C6. Preserve the original g009 first-failure result as its own experiment. A continuation must record failures rather than report them as clean passes. Additional targeted 255/256 and NUL validation controls can qualify the new PostgreSQL classes; they should be separate confirmation experiments, not silently replace these results.
