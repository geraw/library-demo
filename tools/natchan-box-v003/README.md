# Natchan Box v003 — evidence-linked coverage corrections

Use `tools/natchan-box-v003/natchan.py` with the same `natchan-request/1` request and `toolkit-v1` adapter as [v002](../natchan-box-v002/README.md). Python 3.10+, standard library only. Both earlier releases remain frozen.

```powershell
python -m unittest discover -s .\tools\natchan-box-v003\tests -v
python .\tools\natchan-box-v003\natchan.py --request 'D:\experiment\analysis-request.json' --output 'D:\experiment\analysis-v003-001'
if ($LASTEXITCODE -ne 0) { throw 'Analysis failed; inspect diagnostics.json.' }
```

Only a fresh output directory is accepted. The PowerShell convenience launcher is `Invoke-Natchan-Box-v003.ps1`; it was source-reviewed, not executed on Windows here. The full repository is required. Experimental traffic is not replayed; original files are never edited.

## What changed

See [CHANGES.md](CHANGES.md). The composition layer reuses the existing classifiers/gateways and reconciles coverage, rather than treating every stored summary as unknown forever. It never substitutes a producer verdict for raw evidence. Historical-corpus uses the preserved legacy collection workers and renderer with the new composition layer.

### DIV-1

`coverage.json.coverage_audit.resolved_measurements` and `analysis.json.coverage_audit` list exact resolved records. `RAW_VERIFIED` requires a unique existing raw comparison with positive controls, the same journal/run, matching original request values and statuses, and both source witnesses. `response_classes_differ=false` is a verified comparison, not a finding. Findings continue to come from existing predicates. Unmatched, incomplete, ambiguous or contradictory summaries remain unknown.

### Scalar references

An explicit scalar `sent`/`stored` projection with successful status/readback is observable. Comparisons preserve JSON type semantics. A producer projection difference is a measurement; it does not prove a business-policy violation or independently verified state. Missing `stored`, unreadable responses, unsupported types and explicit projection-missing objects remain gaps.

### Product scope

VIK-O09 is excluded from missing-evidence coverage for Gitea-only inputs. It remains visible as NOT_APPLICABLE in the audit and is retained for Vikunja/mixed inputs. This changes coverage, not known-bug predicates or version qualifications.

### Atomicity

Missing full before/after snapshots remain a real gap. Duplicate warnings for the same record are collapsed in the wrapper view. Field measurements and independently observed raw state sequences remain distinct. The release does not claim to add full-snapshot extraction or complete adapters for new systems.

## Output contract

Same fixed files and exit policy as v002: `result.json` is the final marker; COMPLETE/PARTIAL exit 0; invalid wrapper input 2; unsupported interface 3; underlying engine error 4. Finding counts are not independent bug counts. Gaps remain meaningful; an incomplete run must not be relabeled complete just because a summary is reconciled.

The common coverage schema now includes the optional `coverage_audit` object. The new `report.md` displays resolved comparisons separately from unresolved gaps. `analysis.json` retains classification detail and its source-linked audit; applicable coverage is filtered in all box adapters. Original engine reports may preserve legacy presentation and are secondary to the new box report and machine outputs.

## Validation

Tests include positive and negative raw-pair linkage, missing controls/witnesses, conflicting summary statuses, source mismatch, ambiguous matches, scalar/null/missing/boolean projections, product scope and atomicity limitations. See VALIDATION.json. Existing g026/g018 regression counts are preserved.

A separate audit of the published toolkit campaign analyzer output finds 26 qualified comparisons (8 response-class differences) among 34 DIV summaries, leaving 8 unresolved. Its six existing raw partial-write classifications are unchanged. This audit uses retained machine output plus matching result summaries, not a fresh read of the original raw ZIP. Original toolkit packages must still be rerun locally for final release acceptance.

Read [HANDOFF_PROMPT_HE.md](HANDOFF_PROMPT_HE.md) for the operator handoff and remaining data-collection work.
