# ISSTA seeded Library SUT — version 1

## Purpose and scope

This is a new controlled mutation fixture for evaluating testing tools. It is not a claim about previously measured FSE results. The original sut.py, OpenAPI and Provengo models are unchanged.

Files:
- sut_buggy_issta.py: standalone Flask API, localhost:23242.
- library_openapi_issta.json: normative experiment contract, in this directory.
- test_sut_buggy_issta.py: deterministic verification of ground truth, not an automated discovery result.

## Contract and baseline changes

The original library/reference/library_openapi.json has only short CRUD summaries. It does not specify a loan quota, repeat-borrowing semantics or detailed deletion effects. In particular GET /books/{book_id} documents BOTH 200 and 404; a 404 alone is not sufficient evidence of a bug.

The companion experiment contract explicitly requires:
1. No active-loan quota per reader for distinct available books.
2. A returned book can be borrowed again by the same reader, without a lifetime pair quota.
3. Returning a loan deletes only the matching user/book pair.
4. Reading an existing, undeleted book returns that book with 200.
5. Deleting a hold removes only the specified hold.

These are declared experiment rules, not rules falsely attributed to the original sparse contract. Descriptions express temporal semantics; ordinary JSON Schema/status validation alone does not enforce them. All compared tools must receive the same companion contract. Do not give tool generators the mutation list or verification tests when measuring autonomous discovery.

The new fixture removes the original one-active-loan-per-reader restriction even with mutations disabled. It retains one-active-loan-per-book and duplicate-pair checks. It retains the existing successful DELETE response 200, documented in the companion contract (the original contract lists 204). This control is validated for the five target behaviors; it is not a claim of complete conformance for every possible malformed input.

## Switches and clean state

ISSTA_BUGS defaults to 1,2,3,4,5. Set it to none for control, or a comma-separated subset such as 2. Unknown numeric IDs fail startup. Restart the process after changing the environment variable. POST /reset with an empty JSON object resets data, issued-ID pools and loan history; restarting also clears memory. Reset is a harness operation, not a test discovery operation.

Every trigger below starts with an empty SUT. Create resources through POST and reuse IDs from the returned JSON. Never assume sequential or small IDs. Other requests must not delete the resources between the listed steps.

## Exact mutation locations and reproduction

Search sut_buggy_issta.py for ISSTA-BUG-1 through ISSTA-BUG-5. The markers are stable code locators.

### ISSTA-BUG-1 — Fourth distinct active loan rejected
Location: add_loan(), guard using sum(... userId ...) >= 3.
Mutation: add an undocumented cap of three active loans per reader.
Steps: create user U; create books A,B,C,D; POST /loans for (U,A), (U,B), (U,C), (U,D).
Control: all four return 201; GET /loans?userId=U shows all four.
Mutant: first three return 201; fourth returns 409; readback shows three.
The book-exclusive check must not be involved: all four books are distinct and initially available.

### ISSTA-BUG-2 — Third borrowing of the same book rejected
Location: add_loan(), loan_history.get((user_id, book_id), 0) >= 2.
Supporting state: loan_history is incremented only on successful creation and cleared on reset, but intentionally survives returns.
Steps: create U and A; borrow (U,A); return via DELETE /loans/U/A; borrow again; return again; attempt third borrowing.
Control: all three creates return 201; both returns return 200.
Mutant: third create returns 409. Immediately before it, GET /loans shows no active loan.
This uses exactly three borrow attempts for the same pair.

### ISSTA-BUG-3 — Return removes an unrelated loan
Location: delete_loan(), mutation branch filters solely on userId.
Steps: create U and distinct books A,B; borrow both; DELETE /loans/U/A; GET /loans?userId=U.
Control: response 200; A absent and B still active.
Mutant: response 200; both loans absent.
The malformed effect is state loss, not an unexpected status.

### ISSTA-BUG-4 — Existing book falsely reported missing
Location: get_book(), lookup_id = book_id if 4 in BUGS else parsed_book_id.
Mutation: compare Flask's raw string path ID with stored integer IDs.
Steps: POST /books with a nonempty title; record returned integer ID A; GET /books/A without deleting A.
Control: 200 and matching ID/title.
Mutant: 404 even on the FIRST read. GET /books still contains A.
This is the original short-prefix variant, not a read-counter variant.
Both 200 and 404 appear in the original OpenAPI: detection needs the successful creation and absence of intervening deletion, not a blanket rule that every 404 is a bug.

### ISSTA-BUG-5 — Hold deletion removes another hold
Location: delete_hold(), owner_id lookup and filter on userId.
Steps: create U and books A,B; create holds H1=(U,A), H2=(U,B); DELETE /holds/H1; GET /holds.
Control: 200; H1 absent and H2 present.
Mutant: 200; both holds absent.

## Windows / VS Code run commands

From repository root, stop the old server first (Ctrl+C) to release port 23242.

PowerShell:
```powershell
$env:ISSTA_BUGS = '1,2,3,4,5'
& .\.venv\Scripts\python.exe .\library\sut\sut_buggy_issta.py
```

For an isolated mutation set ISSTA_BUGS to its number before startup. For control:
```powershell
$env:ISSTA_BUGS = 'none'
& .\.venv\Scripts\python.exe .\library\sut\sut_buggy_issta.py
```

Fixture verification (does not require a running server):
```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s .\library\sut -p test_sut_buggy_issta.py -v
```

Dependencies: Python 3.9+ and Flask. Uses standard-library unittest and Flask's in-process test client.

## Validation and interpretation

Verification covers 15 combinations: each of five target scenarios with no mutations, its isolated mutation, and all mutations enabled. A separate check verifies history cleanup on reset. All pass.

This proves that the planted behaviors and their controls are reproducible. It does not demonstrate that Provengo, RESTler or EvoMaster discover them autonomously. Existing Provengo models were authored for different rules (including the original one-loan restriction); they need alignment with the experiment contract before a fair discovery campaign. Default all-enabled mode can mask later targets when a tool stops at the first failure: use isolated runs for attribution.
