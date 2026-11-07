# Semantic checker v001: recovered multi-system evaluators + current Library observer

This is the first integration, not a claim of automatic business-rule discovery for arbitrary products. One command and report envelope now reuse historical multi-system rules and the current Library ledger. It does not change existing campaigns, generate scenarios, or give identifiers or findings to a generator.

## Provenance and what was found

Recovered artifacts:

- `openapi_to_sbt_provengo_four_systems_v38.zip` (Library id `libfile_8b364938ba248191bcd93c22af86b694`). Includes the OpenAPI-to-JS generator, common HTTP recorder, multi-system runners and per-system semantic evaluators.
- `library_v38_sequence_local_delta.zip` (`libfile_64d815dfd9488191b79977faf5622e4d`). Repairs historical Library scoring to require a legal prefix and violation within one retained/replayed test. Flat campaign stitching is diagnostic only.
- Current `library/ess-experiment/campaign-v006/observed_server_v006.py`, already used by RESTler, EvoMaster, sampled Provengo and the fixed Java suite.

The historical artifact had a shared framework with several domain evaluators, not a single automatically inferred universal oracle. It also contained separate generator validators (`openapi_to_sbt/validate/static_validate.py`, `scripts/run_validation_suite.py`, `validate_artifact.py`), which check generated-code/artifact quality rather than product business bugs. `Invoke-All-Four-Provengo.ps1` loops across systems; it is not evidence of simultaneous/concurrent execution.

Historical semantic sources are retained byte-for-byte under `vendor/`, with original and LF-normalized SHA256 in `provenance.json`. The two historical test files only change their module-loader paths. The overly permissive older `evaluate_library_trace.py` is deliberately not selected; use the recovered sequence-local replacement. No generator code has been merged into the semantic checker.

## Profiles

| Profile | System / rules | Evidence basis |
|---|---|---|
| `library-issta-v006` | Current five-fault Library fixture | v006 Ledger; independent readbacks needed after writes; first-clean candidate labels |
| `library-v38` | Historical Library HOLD_OWNERSHIP + LOAN_LIMIT | Complete same-case prefix; three successful active loans is its historical violation |
| `garage-v38` | Active repair-order count; one car in multiple garages | Historical successful-response state rules |
| `pharmacy-v38` | P1 refill underflow; P2 cross-store processing | Legal same-case prefix AND the historical class-specific response marker |
| `netbox-legacy-v38` | Original two-fault fixture | Faulty deletion/readback and dropped circuit status |
| `netbox-a2a-v38` | A_LOGIC through E_REFERENTIAL_INTEGRITY | Recovered five-class, prefix-aware A2A evaluator |
| `todoist-runtime-v38` | Runtime/ID propagation smoke | Diagnostics only; never reported as semantic bug detection |

Never substitute one Library or NetBox profile for another. Their benchmark semantics differ. For example, `library-v38` accepts three loans then reports the historical limit violation; `library-issta-v006` diagnoses rejection of a valid fourth loan. Markers in a legacy fixture's HTTP response are different from hidden SUT activation markers. Hidden activation logs do not contribute to this checker.

## Run: current Library archive, no new server requests

From repository root on the work machine:

```powershell
& .\tools\semantic-checker-v001\Invoke-Semantic-Check-v001.ps1 `
  -ArchivePath '.\library\ess-experiment\runs\java-fixed-split-v011-20261021-094721-5216-review.zip'
```

This independently recomputes observer findings from tool + readback rows in each arm and checks parity with the old summary. Previously stored `verdict` rows are ignored as inputs. The result includes native failure flags separately, read from the native JSONL. It does not treat five failed tests as five distinct bugs. Nothing is re-run against the SUT.

To evaluate any one current Library arm:

```powershell
& .\tools\semantic-checker-v001\Invoke-Semantic-Check-v001.ps1 `
  -Profile library-issta-v006 `
  -TracePath '.\library\ess-experiment\runs\java-fixed-split-v011-20261021-094721-5216\business-four\http.jsonl'
```

The wrapper prints the path to a new report. It never overwrites a previous report. No Provengo/RESTler/EvoMaster installation or Flask is needed for offline checking; it uses Python standard-library modules. Existing repository `.venv` is used by PowerShell. The Python CLI can also run with any Python 3.10+.

## Inputs and output

`checker.py evaluate --profile PROFILE --trace PATH --output NEW_PATH` supports recorded v006 JSONL, canonical HTTP JSONL and historical `MODEL_EVENT {json}` lines. Canonical events have `method`, `path`, `status`, `body` and `response`. Current observer events use `request` instead of `body`; adaptation is automatic. Oracle readbacks are not generator requests and are not fed into legacy adapters as generator actions.

Preferred boundary event:

```json
{"role":"boundary","case":"case-001","empty_verified":true}
```

Every boundary starts fresh oracle state, even when a case label is reused. Evidence with a conflicting case label, malformed JSON, no boundary, missing required readback, or source observer error cannot become a confidently negative score. Empty-state verification comes from the recorder; this offline tool cannot independently verify that a recorder told the truth.

For a historical file that is actually ONE self-contained sequence, `--single-sequence --initial-empty` explicitly declares its scope and start state. This declaration is retained as `boundary_evidence: user-declared`; it is not presented as recorded empty-state verification. Never use it on a whole multi-test fuzzing campaign. Without the empty declaration/boundary, results are diagnostic and `status` is `NOT_FULLY_EVALUABLE`. Unknown/incomplete is not zero bugs. No code here reconstructs RESTler/EvoMaster test boundaries from a campaign-flat proxy trace; that requires retained sequences/replay and is a later adapter step.

Output keeps `external_evaluator` separate from `native_tool_faults`, includes per-case evidence, source line numbers and trace SHA256. Native faults are NOT inferred from common-oracle results. Optional `--native-report JSON_PATH` preserves an independently collected native JSON report unchanged; it does not parse generated EvoMaster code or RESTler buckets. The Library archive helper separately reads v011 native JSONL flags.

The current Library adapter recomputes its existing diagnostics. A `STATE_MISMATCH` on hold deletion is labelled `bug-5-candidate`, not automatically promoted to final confirmed seeded-bug score. Review healthy-control and native evidence separately. Historical profiles retain their original result labels and limitations; they are not newly inferred domain semantics.

## Collection / live entry points

`checker.py capture -- --target-port PORT --trace PATH [--listen-port PORT]` exposes the recovered generic localhost HTTP recorder. It forwards to an existing HTTP service and writes the historical MODEL_EVENT format. It does not reset that service or add semantic probes. The historical recorder assumes Content-Length request bodies, supports localhost HTTP targets, and does not preserve native test boundaries. Its threaded collection is not a concurrency/linearizability oracle. Do not treat a campaign file it records as one official test.

`checker.py serve-library -- --sut PATH --bugs none --log NEW_PATH` exposes the exact current v006 Flask fixture/observer. Set `ISSTA_SERVICE_TOKEN`, then initialize `/__campaign__/case` as documented in `library/ess-experiment/observer-v001/README_observer_v001.md`. This path alone requires Flask. It remains Library-specific. The generic offline core is shared; existing live runners are not replaced in this first integration.

## Validation and next development boundary

Run `python -m pytest tools/semantic-checker-v001/tests -q` (pytest is a development dependency). The suite retains 11 historical Library/Pharmacy tests and adds integration guards for case isolation, missing evidence, forged verdicts, generic 500s, each profile, and historical Garage/NetBox positive examples.

`validate_library_archive.py` checks complete captured campaigns without running generators or the SUT. See `VALIDATION_20261021.json` for current work-machine parity and `HISTORY_AND_NEXT.md` for the next boundary: a declarative resource/relationship/rule model, common evidence requirements, pluggable external readback transport and tool-native sequence adapters. Initial reuse of legacy profiles is not yet a universal product oracle, and it does not automatically cover real deployed Mealie/Vikunja/Gitea.
