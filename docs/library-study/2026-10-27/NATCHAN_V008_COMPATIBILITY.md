# Library compatibility check with Natchan Box v008 — 27 October 2026

**Result: the existing components analyze all four Library configurations without an engine change.** This is a two-stage configured route, not automatic recognition of Library ZIPs by the toolkit-v1 adapter.

Analyzer code checked: `geraw/library-demo@9d8abd67c4d6147821e1c4339cff30cd74a3514f`. The preserved entry point `tools/natchan-v014/library_study_audit.py`, its original Library provider and the v008 classifier were executed. No tests against a live SUT were launched.

## Original evidence

Three complete original ZIPs were retrieved, not compact summaries. All SHA256 values match the previously retained run-evidence manifest:

| Archive | SHA256 |
|---|---|
| java-fixed-split-v011-20261021-094721-5216-review.zip | `7abd54bd10a41ac0491594ca679112140d92fbe0fb5553cccc04264d5e0d0895` |
| provengo-sample10-split-v009-20261020-143852-69796-review.zip | `45230f88bb63076795ff876c10b233f78e50249e8c93cd7ccf7e41fb75c4b182` |
| mutants-neutral-v008-20261020-131134-37312-review.zip | `41d2e1b8369d1d552a0e1e5b55181b9f1a3c38dd0ebd2d5bd4a719cf57c90b86` |

The selected inputs contain eight retained runs: three Java arms, three sample arms and the two baseline tool traces. The campaign-v008 name in the last archive is the Library experiment version; it is distinct from analyzer Box v008.

## Results

| Configuration | Source-recomputed occurrences matched to seeded behavior signatures |
|---|---|
| Provengo sample of 10, split 4+1 | Bug 1: 1; bug 3: 4; bug 4: 10; bug 5: 5 — total 20 |
| Provengo fixed Java catalog, work run via campaign-v012 | Bug 5: 22 |
| RESTler, all five faults enabled | Bug 4 context: 1 |
| EvoMaster, all five faults enabled | Bug 4 context: 1 |

The Library archive stage returned `complete` for all three datasets and `EVALUATED_RECORDED_CASES` for all eight traces. It re-evaluated retained requests and oracle readbacks with the preserved case-local Ledger. It did not accept old verdicts or manually reported bug labels as the answer.

Its 44 recomputed observations were exported unchanged to the existing `natchan-observations/1` interface and passed to `tools/natchan-box-v008/natchan.py` using `normalized-observations`. v008 returned exit 0 / COMPLETE, with 44 occurrences and seeded IDs 1, 3, 4 and 5. Matching was compared by **original trace SHA256 + record + catalog ID**, not just totals; every source-level classification agreed. No new inference flags were added in the export.

These are 44 occurrences, not 44 distinct bugs. Bug 2 is not demonstrated by this selected evidence. Missing exposure to its conditions is not proof that its existing rule is unsupported.

## Native results remain separate

The fixed Java reader preserved native failed cases: control 2, business-four 7, book-read-one 2. Five business-four failures occurred in cases passing the healthy control; the 22 contextual hold-loss observations are a different measure. They must not be substituted for seven native failed tests or five additional failed tests.

The chosen sample and baseline trace manifests use `recorded-json-v1`: their native-report status is unknown in this route, **not zero native failures**. In particular, the two baseline bug-4 observations are campaign-global observer witnesses. They do not show that RESTler or EvoMaster reported the semantic bug, or that a generated test was independently replayed to confirm it.

The v008 raw-HTTP shared-judge metrics are unavailable (`common_evidence_available=false`, common counts null) in the normalized-observations stage. The Library-specific provider already recomputed the domain semantics upstream; do not claim that the newer raw-traffic engine independently re-ran those Library business rules.

## Reproduce without changing the analyzer

1. Use the full v008 checkout, including the preserved older analyzer/provider directories.
2. Copy `docs/library-study/2026-10-22/analysis-manifest.json`, keeping datasets `java-work-v012`, `sample-v009` and `mutants-v008`. Replace each `archive` value with its **absolute local path**. Keep the recorded member mappings and product gateway `library-issta-v006`; the Java layout selects its native gateway explicitly.
3. Verify each archive hash against the table above, then invoke the existing raw-evidence entry point with fresh output:

```powershell
python .\tools\natchan-v014\library_study_audit.py --manifest C:\experiment\library-manifest.json --output C:\experiment\library-recomputed
```

4. Export only the recomputed observation records into the existing interface. This is a representation change; it does not add facts or classify from stored findings:

```python
from pathlib import Path
import json
root = Path('C:/experiment')
analysis = json.loads((root / 'library-recomputed/analysis.json').read_text(encoding='utf-8'))
(root / 'library-observations.json').write_text(json.dumps({
    'schema_version': 'natchan-observations/1',
    'observations': analysis['observations']
}, indent=2), encoding='utf-8')
```

5. Create a request beside that observations file, then invoke v008:

```json
{
  "schema_version": "natchan-request/1",
  "run": {"id": "library-four-variants", "product": "library", "product_version": "issta-v006", "tool": "mixed"},
  "evidence": {"adapter": "normalized-observations", "observations": "library-observations.json"}
}
```

```powershell
python .\tools\natchan-box-v008\natchan.py --request C:\experiment\library-request.json --output C:\experiment\library-v008
$analysisExit = $LASTEXITCODE
```

Archive paths in the legacy Library manifest are interpreted by its CLI relative to the working directory, so absolute paths avoid ambiguity. Preserve the upstream archive analysis alongside v008 outputs: the normalized interface does not replace its ingestion/native/control report. This is an already-supported two-stage route; a future one-request Library ZIP wrapper would be an orchestration enhancement, not a necessary change to the rules validated here.

The machine-readable verification is `natchan-v008-compatibility.json`. Raw traces, native logs, local paths and credential-bearing files are not included in this documentation update. No analyzer engine, catalog, earlier release or frozen experiment was modified.
