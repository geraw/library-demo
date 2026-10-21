# Natchan v004 — retained TSE evidence

Offline result analysis for Library (existing v002/v003 bridges), Gitea and Vikunja.
The tool gateways and product semantics are separate modules. This release adds TSE
HTTP transcripts and research-gateway ZIPs; it reuses the existing classifier and
catalog predicate language rather than replacing the previous analyzers.

## Run on Windows

Update the `geraw/library-demo` checkout containing this tool. The separate local
`weissye/vikunja_study` checkout must contain commit
`a46ae1b4773e59727c37e9cd5f321bb1f1877a83`. Its working-tree contents may differ;
the exporter reads immutable Git blobs, not the working tree.

```powershell
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\tools\natchan-v004\Invoke-Natchan-TSE-v004.ps1 `
    -StudyRepoPath 'C:\work\temp\vikunja_study'
```

Use the actual study checkout path if different. Run from the library-demo root.
Python 3.9+ and Git are required. There are no Python package dependencies. If
needed, pass `-Python '.\.venv\Scripts\python.exe'`.

The runner exports the 22 pinned evidence files and one contract to a new output
directory, checks exact SHA256 and Git blob IDs, analyzes them, and checks the
manual expectations. No SUT, Docker, Java, Provengo installation, replay, or new
HTTP requests are involved. Existing output directories are never overwritten.

If Git says the pinned commit is missing, update the **study** checkout first:

```powershell
git -C 'C:\work\temp\vikunja_study' fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Study fetch failed.' }
```

## Portable commands

```text
python tools/natchan-v004/prepare_evidence.py --repo STUDY_CHECKOUT --destination NEW_EVIDENCE_DIR
python tools/natchan-v004/analyze.py --manifest tools/natchan-v004/manifest-tse-v004.json --evidence-root NEW_EVIDENCE_DIR --output NEW_ANALYSIS.json
python tools/natchan-v004/validate_parity.py --report NEW_ANALYSIS.json --output NEW_PARITY.json
```

Existing cross-tool normalized observations can use the same classifier:

```text
python tools/natchan-v004/analyze.py --input EXISTING_NORMALIZED.json --output NEW_CLASSIFICATION.json
```

Accepted existing schemas are `natchan-observations/1` and the Library-only
`natchan-analysis/1`. RESTler and EvoMaster continue through their existing tool
gateways; this release does not claim to have their TSE runs in the selected data.
Unsupported raw formats require an explicit gateway, not heuristic interpretation.

## Output

- `analysis.json`: source-linked observations, predicate checks, known signature
  matches, original oracle records, grouping, per-run native status, missing data.
- `analysis.md`: compact result summary.
- `parity.json`: checks of separately recorded historical expectations, with
  unresolved coverage explicitly listed.
- `evidence/export-receipt.json`: immutable source provenance.

A match to a known signature is not a new bug. Several signatures can describe one
root cause, and several occurrences can describe the same issue. We do not sum
signature groups as unique defects. Frequency alone does not establish determinism.

Gitea native gateway verdicts are retained separately from recomputed facts.
`applied`/`kept` supports recomputing the **aggregation** into `partial`, but without
full snapshots it is not an independent state recheck. RT-1 records retain concrete
sent/stored values; comparisons are recomputed from those values, with the
measurement source recorded.

Vikunja v177/v180/v185 are direct reproducers, **not native Provengo runs**.
The 2.7.0 contract is used only for writable-field projection in the 2.6.0 receipts;
we make no 2.6.0 contract-conformance claim from that borrowed contract. Label
POST receipts use the documented item PUT schema only for field projection.

## Extend the catalog

See [BUG_FORMAT.md](BUG_FORMAT.md), [COVERAGE.md](COVERAGE.md), the editable JSON
catalogs and `bug-template-v004.json`. Known issues and generic trap families are
separate. Draft entries never match. All active known issues require product,
explicit versions and sufficient witnesses. Imported labels are never evidence by
themselves. There is no LLM classification or `eval`.

```text
python -m unittest discover -s tools/natchan-v004/tests -q
```

The Python pipeline was exercised on the actual retained files. The PowerShell
wrapper was source-reviewed but could not be executed in this Linux environment.
