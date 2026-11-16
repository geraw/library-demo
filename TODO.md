# Open items

Status as of 2026-11-16, branch `single-event-actions`. The earlier "RTV virtual-id handoff"
list that lived here is done: live runs through `library/ess-experiment/campaign-v013` confirm
that create callbacks set the `USERn`/`BOOKn`/`HOLDn` run-time variables, that `@{...}`
references are substituted in bodies, paths and query strings, and that never-created ids are
sent as plain values (the `missing` flag in `interfaces.library.js`).

## Model

- Logical ids travel in REST `parameters`, which Provengo also sends as the query string. The
  service ignores the extra keys, but `/loans` list reads cannot carry logical ids under
  `userId`/`bookId` (those are real filters), so list-read events carry late-bound SUT ids
  there. A cleaner carrier for logical ids than `parameters` would remove this wart.
- Loan and hold numbers come from counters whose allocation order depends on BPjs scheduling;
  they are labels, not reproducible identities. A scenario's identity is its reader/book pairs.
- The model never attempts a loan or a hold for an entity that was deleted (the user-book row
  disappears with it). `verifyCannotCreate*WithNonexistent*` covers never-created ids only.

## Experiments (campaign-v013)

- E8 bound sensitivity: trigger hit rates with 3/3, 5/5, 8/8 readers and books, and a lower
  sampler weight for deletions (the fourth concurrent loan for one reader is hit in 1 of 50
  unguided samples with the default bounds).
