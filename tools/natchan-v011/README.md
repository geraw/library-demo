# Report correction audit v011

This release corrects the findings PDF and supplies a reproducible supplemental evidence audit. It does not silently change frozen v009 known-bug catalog predicates or expand their supported versions.

Source study commit: `b82353f2f5dba22eec5a15ec9ad2e473132e7ebf`. This commit corrects the Gitea g009 cloud NOTE: long tags produce a Git ref-lock error, not the invalid-name error. Earlier analyzer C4 subtypes were already correct (eight invalid-name and two long-ref errors).

## Findings clarified

- VIK-F04: the accepted cover points to an attachment absent from the task or nonexistent (selected witnesses: 999999, -1, 2147483647). The stored own representation then fails a no-op update with code 4020, making ordinary whole-object edits fail. A legitimate cover reference alone is not the finding.
- VIK-O05: a value identified as server-managed in the historical analysis can be set by the client on Project create; update ignores the supplied value. Original selected v180 traces show accepted create values plus ignored updates. Wider arbitrary-value claims are attributed to FINDINGS_INDEX_v185, not silently counted as extra recomputed examples.
- GIT-O3: twelve g005 pairs show a no-op on body/ref/state/title, content_version 6→7, then 409 for the identical request carrying version 6. Recorded field values, request equality, path and intervening writes are checked. This is an optimistic-concurrency observation, not automatically an idempotency bug.
- GIT-O4: twelve g005 MaxSize rejections have no corresponding maxLength in the request schema. These are occurrences, not twelve unique limits. The historical user's 40-character organization-name limit is not independently verified by a 40/41 boundary experiment in this batch.
- Release versus Issue: C8's four g009 work measurements are rolled_back; earlier failed Issue updates have mixed applied/kept fields. These are saved oracle field measurements, not reconstructed full-state snapshots.

## ADJ attribution

All six ADJ 500s from the 18-journal audit are Vikunja v164 comment-create journals (seed 1: one, seed 2: five). Five are uniquely matched by method/path/status in the paired lock log. For the sixth path there are two client 500 attempts (one known-failure, one ADJ), and two matching `database is locked` server lines. Thus the error class is supported for the matching group; the script does not assert a unique line attribution or causality. These are not Gitea errors and not six newly confirmed F01 bugs.

Gitea g007 work raw journals contain 503 ADJ probes, all without 5xx (437 2xx, 66 HTTP 409). The earlier 518-pair audit contains these 503 Gitea work pairs plus 15 Vikunja pairs. Gitea home 497/0 is retained as NOTE-level historical evidence until the complete home raw set is adapted; it is not presented as a new recount.

## Other tools

Six v153 native baseline reports were retrieved: EvoMaster three reps, Schemathesis three reps; 20-minute budget each, scoped spec 16 paths/37 operations, archived baseline clone per run. Original native reports and log snippets were checked, not all 1.58 million recorded-request totals re-ingested.

- EvoMaster 6.2.0: three lock-class server 500s in retained SUT context logs. Final reports have category codes {109,201,310}, no code 100; console minimization got 401 instead of the original 500 in all three. v155's retained temporal analysis identifies one task-create F01 and two broader task-event triggers. This analysis is configuration-specific, not a universal inability claim.
- EvoMaster native counters differ internally: `totalNumber=40`, while `foundFaults` has 134/134/136 entries. Both fields are preserved, neither is treated as a unique business-bug count. Zero F01 reports does not mean zero native reports overall.
- Schemathesis: all three JUnit files show the exact PUT /labels case returning 201 with a concrete empty title and a minLength 1 schema violation. This is native evidence for F02's response-level symptom, with no independent follow-up GET claimed. Each JUnit reports 38 failed testcase groups, not 38 distinct bugs.
- RESTler was not part of this v153 baseline comparison. F04/F05/F06 are not automatically scored against this earlier four-finding comparison matrix.

## Run

```powershell
python .\tools\natchan-v011\audit_report.py `
  --g005 'C:\evidence\gitea-g005-home-20261020' `
  --v164 'C:\evidence\v164-triggers-20261018-153232-redacted.zip' `
  --baselines 'C:\evidence\compare-v153-20261017' `
  --output '.\report-audit-new.json'
python -m pytest .\tools\natchan-v011\tests -q
```

Analysis is standard-library Python 3.10+ and makes no server requests. Tests require pytest and original private evidence. Five original-evidence checks passed; skips on missing inputs must not be counted as successful validation. Public output excludes raw credentials and tool consoles; member/file hashes support traceability. Native-baseline request totals remain prior-collector summaries, separate from fully parsed evidence counts.

The revised PDF additionally labels g012 as a later batch: C7 now has Provengo evidence on PostgreSQL 28.1.0; C8 persists in the recorded nightly build and PostgreSQL; C4–C6 were not reached. The original baseline tables remain frozen and are not silently replaced with later-run counts.
