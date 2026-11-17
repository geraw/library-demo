# Library test model (Provengo)

A Provengo behavioral model of the library REST service in `../sut/sut.py` (readers, books,
loans, holds). The business rules it encodes and the stories it generates are described in
[Lib_Rule.MD](Lib_Rule.MD).

## Layout

| Path | Role |
|---|---|
| `lib/utils.js` | Generic helpers: description builders, event accessors, list reads. Loaded first. |
| `data/` | Project data; a campaign may drop an endpoint override here. Loaded second. |
| `spec/js/interfaces.library.js` | The REST boundary: one request per action, EventSets, `extractEventData`, SUT-id mapping (RTV). |
| `spec/js/dal.js` | The Context model: entities, effects of successful events, queries. |
| `spec/js/lib_stories.js` | The stories: creates, deletes, reads and business-rule rejection checks. |
| `meta-spec/` | Scenario metadata and the ensemble ranking goals. |
| `config/provengo.yml` | Provengo configuration. |

## Run

With `provengo` on the PATH and the service running on `localhost:23242` (`python ../sut/sut.py`):

```bash
provengo run .                 # one live scenario against the service
provengo run --dry .           # model only; stops at the first late-bound SUT id
provengo sample --size 10 .    # sample scenarios (no service needed)
provengo analyze -f pdf .      # draw the specification
provengo ensemble --size 5 .   # pick a suite that covers the goals in meta-spec/ensemble-code.js
```

The experiment harness that runs this model guided through a scenario catalog, behind an
observer and against mutated services lives in `../ess-experiment/campaign-v013/`.
