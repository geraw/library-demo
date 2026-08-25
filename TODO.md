# RTV Virtual-ID Handoff

## Goal

Keep scenario and DAL identities stable and readable while allowing the SUT to own all real IDs.
Stories pass virtual IDs to `createUser`, `createBook`, `createLoan`, and `createHold`. Successful
REST callbacks store the real IDs as Provengo run-time variables, and later wire-level requests
refer to those values with `@{...}` expressions.

## Implemented in this checkpoint

- Added the Provengo `rtv` library to `interfaces.library.js`.
- Standardized RTV keys as `USER<n>`, `BOOK<n>`, `LOAN<n>`, and `HOLD<n>`.
- Added `rememberCreatedId(...)`; successful create callbacks parse `response.body.id` and call
  `pvg.rtv.set(key, id)`.
- Added late-bound helpers `realUserId`, `realBookId`, `realLoanId`, and `realHoldId`.
- Changed ID-bearing REST bodies, paths, and query parameters to use late-bound expressions.
- Kept virtual IDs in REST-event `parameters` so event matching and the DAL see model identities,
  not SUT identities.
- Changed virtual ID generators to simple per-entity sequences.
- Changed the demo SUT so users, books, loans, and holds receive sequential server-owned IDs;
  all create responses now contain `id`.
- Updated the OpenAPI create/response schemas for server-owned IDs.
- Removed duplicate-client-ID stories for server-owned user/book/hold IDs.

## Validation already performed

- `python -m py_compile Library/sut/sut.py` passed.
- `Library/reference/library_openapi.json` passed `python -m json.tool`.
- Flask test-client smoke testing created one user, book, loan, and hold; every response was `201`
  and contained a generated `id`.
- `provengo analyze` built the model and began state exploration without a syntax/build error.
  It was stopped after more than 1,000 iterations because exploration was long-running; this is
  not a complete Provengo validation.
- `git diff --check` passed (apart from Windows line-ending notices).

## Highest-priority verification work

1. Run a real sampled scenario against a live SUT and inspect the emitted requests. Confirm that:
   - create callbacks execute and set the intended RTV key;
   - `@{USERn}` and `@{BOOKn}` are substituted inside JSON bodies for loan/hold creation;
   - path and query substitutions are numeric and correctly URL encoded;
   - loan and hold callbacks populate `LOANn` and `HOLDn`.
2. Confirm that callbacks created with `new Function(...)` survive Provengo sampling/serialization.
   If Provengo rejects dynamic callback functions, replace this factory with callback functions
   whose RTV key is carried through a supported runtime parameter mechanism.
3. Design and test missing-ID behavior. Negative stories currently create virtual IDs that have
   no RTV entry. A raw `@{USERn}`/`@{BOOKn}` lookup may fail before the HTTP request is sent. Add a
   supported fallback expression or explicitly seed missing-ID RTVs before negative operations.
4. Audit all verification helpers. Some response predicates still compare SUT response IDs with
   generation-time virtual IDs. Move those comparisons to runtime callbacks/assertions and compare
   against the relevant RTV value.
5. Verify event matching for create/delete operations in sampled traces. Event metadata should
   retain virtual IDs even though URLs and bodies contain runtime expressions/real IDs.
6. Run a bounded reproducible suite first, then a longer analysis/sample/ensemble run. Record the
   command, seed, Provengo version, and any failing trace.

## Suggested end-to-end procedure

1. Start the SUT:

   ```powershell
   cd Library\sut
   python sut.py
   ```

2. In another terminal, run a small generated suite from `Library\provengo`. Prefer a fixed seed
   if supported by the installed Provengo version.
3. Inspect Provengo output and `Library/sut/sut.log` for the sequence:
   create user/book -> create loan/hold with real foreign keys -> reads/deletes with real keys.
4. Add a focused RTV smoke story if failures are hard to isolate: create one user and one book,
   create one loan, read it, delete it, then delete the book and user.
5. Only after the focused flow passes, restore broad fuzzing/state exploration and investigate
   concurrency/relevance failures separately from RTV substitution failures.

## Files central to the work

- `Library/provengo/spec/js/interfaces.library.js` — RTV callbacks and REST-boundary substitution.
- `Library/provengo/spec/js/lib_stories.js` — virtual ID generation and behavioral stories.
- `Library/provengo/spec/js/dal.js` — model state; should continue to use virtual IDs only.
- `Library/sut/sut.py` — sequential server-generated IDs and create responses.
- `Library/reference/library_openapi.json` — server-owned create/response schema.

## Workspace note

`Library/sut/sut.log` is generated/runtime output and was intentionally not included in this
checkpoint commit.
