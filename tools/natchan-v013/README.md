# Natchan v013: raw evidence to automatic findings and report

This version runs the existing raw gateways together, deduplicates observations by source byte hash and record, applies one catalog classifier, and generates the report from `analysis.json`. No NOTE, FINDINGS_INDEX, old PDF, or analyst narrative is used as evidence. It reuses v003–v006, v008 and v011 parsers and rules rather than replacing their evidence logic.

## Run

From the repository root, with the original artifacts restored to the paths in the corpus manifest:

```powershell
python .\tools\natchan-v013\run.py --root . --output .\natchan-output-v013 --pdf
```

The output directory must not already exist. Python 3.10+ is required. JSON, HTML and Markdown use the standard library; optional PDF requires `python -m pip install weasyprint` and a working WeasyPrint installation. The report uses DejaVu Sans fonts; install those fonts or adapt the renderer's font paths for other operating systems.

`--manifest path.json` selects another corpus. Each dataset declares an adapter and its original evidence location; `locked_sources` pins source bytes. Supported adapters are declared in `worker.execute`. Adding another product or artifact format requires a gateway, not a manually written finding. The checked-in corpus refers to privately held original artifacts; a checkout alone does not contain those artifacts. Missing or changed inputs fail the run.

## Outputs and audit

- `analysis.json`: observations, assessments, unique rule/observation findings, unknown evidence, actual source hashes, code/catalog/profile hashes.
- `report-view.json`: rule counts and observation IDs rendered in the report.
- `report.html`, `report.md`, optional `Natchan_Automated_Findings_v013.pdf`: generated from the analysis only.

The renderer checks catalog hashes and finding/count parity. Counts are rule occurrences, not a number of independent bugs. Known signatures are version-qualified. Native tool findings, HTTP evidence, producer field measurements and ID projections remain distinct. Producer verdict labels are not accepted as proof: field measurements are recomputed, but absent full before/after snapshots remain unknown.

`profiles.json` declares metadata exclusions. It excludes server timestamps and identity metadata from roundtrip comparisons; it deliberately does not exclude `background_blur_hash`. F04 requires the invalid cover response context. O05 requires an earlier raw creation/readback witness. PostgreSQL classifications require both original payload properties and correlated server errors. O3/O4 are executable raw-sequence/schema rules. Severity remains `requires_context` where impact cannot be inferred.

## Verify

```powershell
python -m pytest -q .\tools\natchan-v013\tests
python .\tools\natchan-v013\verify.py .\natchan-output-v013\analysis.json --root .
```

Tests cover positive and negative controls, deduplication/conflicts, unknown versions, metadata exclusions, producer-label independence, source mutation rejection, native/HTTP separation and report count parity. Historical parser suites must be run in separate pytest processes because several frozen versions use identical module names. The compact review summary records the full original-artifact integration run. Raw private journals are not published.

## v013 updates

C1/C2 (including the existing C2+ error family)/C8 now include the exact tested nightly build `29.0.0+dev-175-g33610142c3`, with unchanged payload/log/sequence predicates. Other nightly versions remain unqualified. PostgreSQL payload/log patterns also map to version-qualified known signatures C9/C10; generic and known signature counts overlap.

O07 recognizes only successful DELETE of share identifier zero. Large positive identifiers without an independent absence observation do not meet this signature. O09 requires an actual nonempty, unredacted request password echoed in the 412 response; a manual finding index or a summary cannot supply the fact. The report includes missing registration-request coverage explicitly.

`source-resolution.json` records exact Git blob matches in the rewritten study snapshot, pinned to its full commit. Unmatched local containers remain SHA256 pinned. Old catalog provenance commits are named historical and are not used as retrieval locations; current source snapshots are separate references. The report never treats a current HEAD reference as proof that old raw bytes were preserved.
