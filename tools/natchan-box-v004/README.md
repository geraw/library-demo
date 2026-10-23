# Natchan Box v004 — toolkit evidence verification

Offline Python 3.10+ analyzer. Full `geraw/library-demo` checkout required, branch `natchan-box-v004`; earlier box releases are unchanged. No third-party Python dependency and no SUT calls. The request and output schemas remain `/1`.

```powershell
python -m unittest discover -s .\tools\natchan-box-v004\tests -v
python .\tools\natchan-box-v004\natchan.py --request 'D:\experiment\analysis-request.json' --output 'D:\experiment\analysis-v004-001'
if ($LASTEXITCODE -ne 0) { throw 'Analysis failed; inspect diagnostics.json.' }
```

Use a fresh output directory. `Invoke-Natchan-Box-v004.ps1` is an optional convenience wrapper. See [the complete box interface](../natchan-box-v002/README.md) for all adapters, configuration and output contracts. Existing toolkit requests can be reused unchanged. Results remain separate from experimental run status. COMPLETE/PARTIAL exit 0; invalid input 2, unsupported interface 3, engine error 4. PARTIAL is useful evidence with unresolved gaps, not zero findings.

## New evidence support

The producer specification is `weissye/vikunja_study@d990657a2470d4dbf368d4d5eb592749a292f6ff:toolkit/v1/EVIDENCE_FORMATS_v1.md`. Producer code was read, not edited. The adapter supports both bare and nested review ZIPs and uses the existing source/hash/configuration checks.

### atom-snapshots/1

For updates, the verifier uniquely binds logical ID/method/path to the journal request, checks actor, request body, failure status and retained first response. It reexecutes the producer's documented field and collateral comparison from request, before and after objects and compares all results and verdict. Successful checks resolve only that exact oracle record and add generic atomicity facts through the existing classifier. Existing field-measurement labels are retained. The producer algorithm skips requested fields absent from the after object; this scope is recorded in the audit, not represented as verification of those fields.

A cached `last_2xx_representation` is explicitly distinguished from producer-declared `trap_read_before_write`. Snapshot verification is a comparison over recorded values, not a proof of freshness, an absence of concurrent writers, or a race. The before object lacks its own request/index/actor witness; the audit makes that limitation explicit. Create/delete snapshot variants remain unsupported by this update verifier; list counts are not full creation snapshots.

Missing/unreadable state, ambiguous binding and unknown versions remain record-specific gaps. Measurement or verdict conflicts are `PRODUCER_EVIDENCE_CONTRADICTION`, with computed and reported results; contradictory producer labels are not promoted into findings by the new verifier.

### div-evidence/1

Both write copies must match unique indexed original research rows, including method/path/input/status/response and logical ID. Index is the producer's index, whereas a source `record` is its zero-based physical journal position. A tested field is derived from IR routes and trap definitions plus equal request values; logical-ID spelling does not identify its semantics. Parent bindings and actor must agree, and a unique successful update fixture GET is required. Different reference IDs or parent scopes cannot be assumed equivalent merely because the producer labels both `missing`, `deleted` or `own`.

Response classes are computed from original statuses. When both writes succeed, their exact readback pointers must bind to matching oracle measurements and cover the tested field. Full hidden readback bodies are still not present for these oracles: such stored-outcome comparisons are `PRODUCER_MEASUREMENT_COMPARED`, **not** independently verified raw state. A pair with the same outcome is a verified comparison, not a defect. New divergence facts annotate the existing update HTTP observation, never another HTTP request.

### Backward compatibility and outputs

Records without these opt-in fields pass through v003 unchanged, including their gaps. Unknown versions do not fall back to legacy verification. v003 scalar reference handling, campaign pairing, product coverage scope and other adapter behavior are preserved.

`coverage.json.coverage_audit.resolved_measurements` identifies each verified comparison, computed outcome, evidence tier and original witnesses. `unknown_evidence` retains exact unresolved reasons. `analysis.json` includes observations, all source-linked audit details and aligned `producer_measurements`. `findings.json` is classifier output; `report.md` is its mechanical rendering. The other fixed outputs are `provenance.json`, `diagnostics.json`, and `result.json`, written last. Original legacy engine reports are secondary to box outputs.

## Validation and acceptance

See [VALIDATION.json](VALIDATION.json), [comparison](reviews/COMPARISON.md) and [per-record audit](reviews/SAMPLE_AUDIT.json). The checked archives are the exact before/after **cloud route-harness development samples**, not evidence of a native Provengo schedule. They have 609 journal records and 431 research exchanges each. On the old sample, v004's entire analysis JSON equals v003's analysis JSON. On the new sample, eight atomicity checks and 35 DIV comparisons resolve; four REF comparisons remain unresolved. All previous rule occurrence counts are preserved; new verified labels are additional classifications, not new independent bugs.

The release has not been accepted against a new home run with the frozen Provengo JAR. That is the next integration check. Generic typed extraction of these two evidence formats works without a product-name branch (unit tests use an example product); full business-policy understanding of arbitrary products is outside this change.

Read [HANDOFF_PROMPT_HE.md](HANDOFF_PROMPT_HE.md) for the research operator handoff. Do not change frozen experiment tags or manufacture expected findings in requests.
