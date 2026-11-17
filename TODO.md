# Open items

Status as of 2026-11-17, branch `single-event-actions`. The earlier "RTV virtual-id handoff"
list that lived here is done: live runs through `library/ess-experiment/campaign-v013` confirm
that create callbacks set the `USERn`/`BOOKn`/`HOLDn` run-time variables, that `@{...}`
references are substituted in bodies, paths and query strings, and that never-created ids are
sent as plain values (the `missing` flag in `interfaces.library.js`).

## Model

- Logical ids travel in REST `parameters`, which Provengo also sends as the query string. The
  service ignores the extra keys, but `/loans` list reads cannot carry logical ids under
  `userId`/`bookId` (those are real filters), so list-read events carry late-bound SUT ids
  there. A cleaner carrier for logical ids than `parameters` would remove this wart.
- A late-bound `@{...}` reference must sit inside a JSON string: the sampler ends a scenario at
  an event whose body is not valid JSON before substitution (found the hard way, see
  `pairBody`). Ids in bodies are therefore numeric strings, which the service accepts.
- A deleted entity's loan/hold rejection is paired with whichever counterpart exists first; a
  scenario that needs a specific counterpart for it is not guaranteed reachable.
- Provengo's `on()` drops events selected while its handler is syncing; the model uses its own
  `forEachEvent` (one b-thread per event). Reported upstream.

## Experiments (campaign-v013)

- E8 bound sensitivity: trigger hit rates with 3/3, 5/5, 8/8 readers and books, and a lower
  sampler weight for deletions. The fourth concurrent loan for one reader (ISSTA-1) is hit in
  0-1 of 50 unguided samples with the default bounds and is the only trigger that depends on
  the sampler's choices rather than on the model; the guided catalog reaches it directly.
