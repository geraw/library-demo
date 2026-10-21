# Natchan v005 — coverage completion

This increment reuses v004, adds older original Vikunja archives, activates the
remaining known-issue predicates, and supplies executable providers for all 11
trap families. It does not relabel absent evidence as a successful check.

## Run the expanded historical analysis

From the updated `geraw/library-demo` checkout:

```powershell
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\tools\natchan-v005\Invoke-Natchan-Coverage-v005.ps1 `
    -StudyRepoPath 'C:\work\temp\vikunja_study'
```

Use the actual local study repository path. Python and Git are sufficient; no
server, Docker, Java or tool execution is required. Inputs are exported from
study commit `a46ae1b4773e59727c37e9cd5f321bb1f1877a83` using exact Git blob IDs
and SHA256. The working tree is not changed. Existing outputs are not overwritten.

Portable equivalents:

```text
python tools/natchan-v005/prepare_evidence_v005.py --repo STUDY_CHECKOUT --destination NEW_EVIDENCE_DIR
python tools/natchan-v005/analyze_coverage.py --evidence-root NEW_EVIDENCE_DIR --output NEW_ANALYSIS.json
python tools/natchan-v005/validate_coverage.py --report NEW_ANALYSIS.json --output NEW_VALIDATION.json
```

The expanded analysis processes 11,854 retained HTTP records. All six Vikunja
finding IDs F01–F06 have original-evidence matches. F01 has eight uniquely scoped
method/path/status lock joins, including both v185 versions; F03 has six original
2.6.0 overlength-and-readback witnesses. This does not establish F03 on 2.7.0.

## Gitea C4–C7: complete rules, partial retained evidence

The known definitions now have executable conditions rather than draft
placeholders. Full original bodies and correlated errors can match C4/C5/C6;
C7 can match a qualified same-value email pair. Unit tests cover positive and
missing/conflicting evidence cases.

The pinned cloud folder retains HTTP-error summaries and paired oracle records,
but not full original bodies or server logs. Twenty compatible symptoms are
therefore reported separately: C4=10, C5=2, C6=3, C7=5. They are **not** counted as
fully matched known bugs. The logical-name grammar supplies producer context;
it never substitutes for the absent request value or traceback.

If complete run folders still exist on the local machine, analyze them directly:

```powershell
python .\tools\natchan-v005\analyze_local_gitea.py `
    --root 'C:\work\temp\vikunja_study\runs' `
    --output '.\gitea-local-analysis-v005.json'
```

Point `--root` at the actual Gitea run folder or its runs parent. The reader searches
only that supplied subtree, skips environment/dependency folders, enforces limits,
and reads `gateway-journal.jsonl`, its `generated/contract-ir.json`, `sut.log` and
available original result metadata. If version metadata is absent, supply
`--product-version 28.1.0`. Missing bodies/logs stay visible. The local reader was
smoke-tested against an actual g009 work archive and recovered C1, C2 and C8.
Native-tool attribution is preserved conservatively; it is not guessed from a
folder name.

## Generic provider interface

See `PROVIDER_CONTRACT.json`, `measurements.schema.json`, and
[MEASUREMENTS.md](MEASUREMENTS.md). The supported families are RESPONSE, EDGE-1,
RT-1, ATOM-1/2, EDGE-U, KNOWN, CASCADE-1, ADJ, IDEM, VIEW and LINK.

```text
python tools/natchan-v005/classify_measurements.py --input MEASUREMENTS.json --output NEW_CLASSIFICATION.json
```

The same CLI also accepts existing `natchan-observations/1` cross-tool inputs and
Library `natchan-analysis/1` inputs. Library evidence is re-evaluated through the
preserved bridge in an isolated process; its 22 bug-5 observations were retained.
The same interface serves any product/tool gateway. The supplied example is
explicitly synthetic. It is not part of the historical evaluation. Source and
context assertions must originate from a measurement gateway; setting a flag by
hand does not establish evidence. Providers recompute from values and do not
consume a prior `verdict` as truth. Missing snapshots, pair values or relationship
scope produce `not_evaluable`, never an invented pass.

Original Gitea ATOM outcomes remain separate. Full snapshot checks are implemented
but cannot run backwards from only `applied`/`kept` labels. Provider diagnostics
show which required fields are missing in the existing artifacts.

## Definitions and limitations

`catalogs/tse-known.json` contains the complete known-issue conditions, including
F01/F03 and C4–C7. Generic subtype entries are executable; normalization remains a
human-review candidate. The original editable bug format is documented in
`../natchan-v004/BUG_FORMAT.md`.

An explicit conflicting fact now excludes a possible known issue; only missing
facts produce `insufficient_evidence`. Overlapping primary findings, provider
findings and original oracle results must not be summed as independent bugs.
No live replay or automatic follow-up experiments are performed.

The Python pipeline and local reader were executed. PowerShell wrapper execution
was unavailable on the Linux host; its source was reviewed.
