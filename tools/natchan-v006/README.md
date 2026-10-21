# Natchan v006 — complete g009 cloud evidence

Re-analysis of the original files added in study commit
`e8314ed30534b0e24581f8c84700eada02b51253`. All four runs are **route-harness**
actuation, not native Provengo. No new SUT calls or live experiments occur.

From the updated library-demo repository:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\tools\natchan-v006\Invoke-Natchan-Cloud-v006.ps1 `
    -StudyRepoPath 'C:\work\temp\vikunja_study'
```

Use the actual local study checkout path. The checkout must contain the pinned
commit; fetch `origin main` in that checkout if necessary. The exporter reads
immutable Git blobs and verifies their SHA256 and blob IDs. Existing output
folders are not overwritten.

Portable commands:

```text
python tools/natchan-v006/prepare_cloud_v006.py --repo STUDY_CHECKOUT --destination NEW_EVIDENCE_DIR
python tools/natchan-v006/analyze_cloud_v006.py --evidence-root NEW_EVIDENCE_DIR --output NEW_ANALYSIS.json
```

## Results

1,732 actual retained HTTP records, 36 HTTP 500s, 36 request/error joins.
C4=10, C5=2, C6=3, C7=5. These replace the earlier 20 symptom-only candidates.
They are occurrences of known signatures, not 20 newly discovered bugs.

C4 contains two observed error branches: eight invalid-tag validation errors,
and two Git-ref creation errors for 10,000-character tags. The latter logs are
truncated; a precise filesystem root cause is not inferred. The C4 rule includes
that explicitly documented very-long-tag branch and preserves its distinct
`git_ref_failure` subtype.

The journal and server clock differ by 10,800 seconds. This is measured using
684 unique non-error method/path/status anchors, not assumed from a timezone
name or selected to make failures match. Repeated failure keys use a unique
order-preserving mapping only because the manifest explicitly declares the
complete sequential route harness. Counts, order and time bounds must agree.
Server-handler identity excludes adjacent background-notification errors.

The g009 frozen 28.1.0 IR from the original work archive is used only for route
and field projection. Original cloud result metadata independently verifies the
SUT version and HTTP request count. The four cloud native.log files are runner
outputs, not Provengo verdicts.

## Remaining evidence gaps

Original hidden oracle readback bodies were never saved. Independent ATOM
snapshot reconstruction and other checks requiring those internal observations
remain not evaluable. Their producer verdicts are retained separately. A richer
parser cannot recover a body that was never recorded.

C4–C7 still have no native Provengo confirmation on the tested buggy version.
The existing work g009 runs stopped at C8 before reaching those traps. This
analysis does not execute or change g012. A nightly run reaching later traps
would be evidence for that nightly, not automatically for the buggy release.

The Python CLI was executed on the complete original data. PowerShell wrapper
source reviewed; not executable on this Linux host.
