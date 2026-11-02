# Steps 1–2: raw evidence acceptance and state semantics (009-dev.6)

This milestone implements the first two execution steps: freeze acceptance cases;
connect legacy measurements to independent raw evidence; improve transport,
contract binding, lifecycle and failed-write analysis. It does not implement S4
relationships, S6 views, aggregates, scaling, or copy semantics.

## Changes and interpretation

- `journal-jsonl` maps the original session to actor, parses JSON bodies, ignores
  internal `/__sbt/` exchanges and producer summaries. It does not invent an epoch
  or declare isolated/complete capture. All four Library producers retain their
  existing common HTTP adapter; the producer name selects no semantic rules.
- The frozen v005 `providers.py` is copied verbatim as `historical_providers.py`
  (hash in `historical-provider-provenance.json`). RT-1 and ATOM-1-2 comparisons
  are reused, without product catalogs or producer verdicts. A small documented
  adapter extends failed-update comparison to 4xx without pretending it was 500.
- Create/read and delete/read use exact concrete URIs, including parent paths,
  typed response identities and same-origin Location. Unknown writes, reset,
  actor/case changes, async outcomes and intervening mutations invalidate state.
- Failed creation requires adjacent complete collection GET / rejected POST /
  collection GET. The before snapshot must remain present; a newly visible
  object must match every sent field. No query, wrapped list or pagination
  interpretation is attempted. Missing preimages/readbacks are reported.
- A request scalar can be compared to a response object's unique compatible
  `id`/`uuid`/`key` field. This is explicitly a structural candidate, with schema
  pointers, not a proof of a foreign-key relationship. Integer/string alternatives
  are retained for exact failed-create field matching; general oneOf validation
  remains unsupported.
- Recognized **whole affirmative contract sentences**, not arbitrary NLP:
  `Creation is synchronously visible`; `Completed deletion removes the exposed
  resource`; `Rejected creations preserve business state`; `Failed writes
  preserve business state`. Every recognized guarantee links to
  `#/info/description`. Other wording stays unknown. A complete collection is
  recognized only from an operation description starting `Return all`.
- With controlled capture, explicit matching guarantees distinguish a contract
  violation from a semantic candidate. Old captures can additionally produce
  **adjacent raw-sequence observations**, even without proven isolation. They
  remain `policy_observation`, never confirmed violations. Partial/applied means
  the compared requested fields, not a complete-resource commit or root cause.

## Acceptance inputs and gates

| Input | Gate |
|---|---|
| Actual Library SUT, B1 | Created book followed by missing read is detected |
| Actual Library SUT, B2 | Completed delete followed by successful read is detected |
| Actual Library SUT, B3 | Rejected creation adds a matching loan, with a retained preimage |
| Same three sequences, baseline | No semantic violation |
| Existing full RESTler baseline, 2,499 exchanges | Zero semantic/policy findings; retain the 5 actual server errors |
| Frozen G014 raw archive | Find the six 500/write/state-effect witnesses at journal lines 40,86,180,208,646,676 |
| G014 counterfactual rollback controls | Replacing each postimage with its preimage produces no state-effect observation |
| Generic controls | Reject cross-actor correlation, contradicted serial capture, intervening writes and wrongly typed identity |

Frozen raw Library witnesses and controls, with SHA256s and SUT source hashes,
are in `tests/fixtures/step2`. These are post-hoc development regression cases,
not a preregistered or held-out experiment.

Library acceptance invokes the existing SUT in-process on Linux with Flask. It
adds a preimage read for B3; this does NOT mean older traces without a preimage
have sufficient evidence. It neither reruns nor resamples the ten saved scenarios.

G014 provenance: `weissye/vikunja_study` at
`d378389226c1af05e767ddb0db895fcc41bd368d`, archive
`results/gitea-g014-work-20261022/review_g014_s1.zip`, Git blob
`75ac336228bd5929bf438d98694ea41982393b09`. The runner verifies exact archive and
contract bytes. Original private journals are not republished here. The actual
source contract is `toolkit/v2.7/configs/gitea/contract.json` (SHA256 checked).
Counterfactual controls are test transformations, not additional live SUT runs.

## Commands (existing checkouts)

```powershell
python -m unittest discover -s .\tools\natchan-box-v009\tests -q
.\library\benchmark-v001\.venv-benchmark-v001\Scripts\python.exe -m unittest discover -s .\library\benchmark-v001\tests -p test_semantic_acceptance_v001.py -v
python .\tools\natchan-box-v009\acceptance_real.py --study-root D:\Yeshayahu\Temp\vikunja_study --output .\g014-dev6-acceptance
```

The output directory must not exist. Use the actual study checkout path if it
is different. No clone, container restart or sampling is required.

For an old journal, create fresh analysis without changing the original run:

```powershell
python .\tools\natchan-box-v009\replay.py --contract PATH_TO_CONTRACT.json --traffic PATH_TO_JOURNAL.jsonl --format journal-jsonl --output NEW_ANALYSIS_DIRECTORY
```

Supply `--capture recorder-capture.json` only when the recorder actually provides
those guarantees. Without it, strict checks explicitly abstain and supported
local state effects remain observations. A newly generated freeze is a replay
integrity record, not proof of preregistration before the original experiment.

## Remaining limits

B4/B5 and the real-system view/reference/aggregation gaps remain for subsequent
steps. No claim is made that the new analyzer replaces v008 generally or recovers
all historical bugs. Windows commands are provided but were not executed in this
Linux environment. Tests of the shared HTTP recorder path do not mean all four
native tools were launched again.
