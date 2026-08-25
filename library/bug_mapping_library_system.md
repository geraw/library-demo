# Bug Mutation Map — Library Management System (sut_type.py)

## Latest update

This document has been updated in view of the current system version and has been redefined as a basis for mutation mapping and negative tests for the Library Management System.

## Introduction — the purpose of the document and its structure

This document is intended to be used as a basis for planning negative testing and mutation testing for an example System Under Test — a Flask-based API for library management, which includes four entities: `User`, `Book`, `Loan` (a checked-out book) and `Hold` (a place in a waitlist/future loan).

**The main idea:** Each line in the document must describe a concrete and targeted change in the existing code (a single mutation - not a real fix, but a deliberate planting of a fault) that creates incorrect behavior. The purpose of planting is to check that there is a test package that catches (kills) any such mutation. A line that no existing test catches indicates a real gap in the system's test coverage.

The bugs were divided into four chapters, according to the following definition:

| chapter | definition | A typical example |
| --- | --- | --- |
| **1. Type Bugs** | Errors in checking the type/validity of a **single field** in the input (id, name, title, etc.) — including incorrect acceptance/rejection of data types, numeric endpoints, character encoding and raw JSON format. The test here is at the level of "is the single field itself correct", before even touching the business logic. | receiving `true`/`false` as a proper id because `bool` is a subclass of `int` in Python. |
| **2. Single-API Bugs** | Faults in the behavior of a **single call** to a specific endpoint — incorrect business logic within the route function itself (order of checks, status codes, filtering, duplicates), including infrastructure aspects (routing, HTTP methods, JSON parsing at the entire request level) that are relevant to a specific endpoint or group of endpoints. | Deleting the check "Book is already loaned" in `POST /loans`, so a book can be loaned to two users at the same time. |
| **3. Logical Call Combinations** | Faults that are only detected when you run a **natural and reasonable sequence** of several API calls together (for example: adding a user → adding a book → hold → loan → deleting a loan → deleting a book/user), including reasonable variations such as several users/books at the same time, cancellation and return. Each step on its own may seem fine, but the combination reveals the bug. | Deleting a user that has an active hold (because the corresponding check has been removed), leaving an "orphaned" hold that points to a non-existent user. |
| **4. Low-Probability Input Combinations** | Faults that are revealed only in **unnatural but legal sequences in terms of the API** — extreme repetitiveness (retry storms, rapid repeated creation/deletion), overload, and order of operations that a normal client would almost never perform on purpose (but a wrong client/other bug may cause it). Including race conditions, idempotency issues, and subtle state leaks. | Deleting the keyword `global` by mistake from one of the DELETE functions, causing `UnboundLocalError` Only in a certain code path that is revealed only after many repeated calls. |

**Note:** In each chapter, some of the lines also describe "an opportunity to plant a bug that aggravates" an existing dysfunction in the system (such as the lack of a real logical connection between `Hold` to-`Loan`, or the lack of atomicity/thread-safety) — these are explicitly marked in the text and are not considered an existing bug per se, but a leverage point for planting a mutation.

---

## Chapter 1 — Type Bugs in Input Fields

### 1.1 Generic validation functions
Changes here affect **all** the fields that use the relevant function — affect several endpoints at the same time.

| # | Mutation to Introduce | Description |
| --- | --- | --- |
| 1.1.1 | `is_int`: Remove the test `not isinstance(value, bool)` | `True`/`False` will be accepted as a valid int (bool is a subclass of int in Python) |
| 1.1.2 | `is_int`: Replacement `isinstance(value, int)` to-`isinstance(value, (int, float))` | Decimal numbers (1.5) will be accepted as int |
| 1.1.3 | `is_positive_int`: Replacement `value > 0` to-`value >= 0` | 0 will be accepted as a positive value |
| 1.1.4 | `is_positive_int`: Deleting the condition completely | Negative values/0 will be accepted as valid |
| 1.1.5 | `is_valid_id`: Remove a test `isinstance(value, bool)` In the int branch | `true`/`false` will be accepted as id |
| 1.1.6 | `is_valid_id`: removing the `try/except` around `int(value)` | A non-numeric string will result in 500 (Unhandled Exception) instead of 400 |
| 1.1.7 | `is_valid_id`: Replacement `parsed > 0` to-`parsed >= 0` in the string branch | `"0"` will be accepted as a valid id |
| 1.1.8 | `is_valid_id`: getting a float as a string (`"1.5"`) — change to `float(value)` instead of `int(value)` | A decimal id will be accepted |
| 1.1.9 | `is_valid_id`: Inconsistent handling of whitespace (`" 5 "`) | Inconsistency between JSON input and URL strings |
| 1.1.10 | `is_str`: extension to `isinstance(value, (str, bytes))` | bytes will be accepted as a string |
| 1.1.11 | `is_non_empty_str`: Removal `.strip()` | string with spaces only (`"   "`) will be accepted as a valid name/title |
| 1.1.12 | `is_non_empty_str`: Replacement `!= ""` to-`is not None` only | an empty string `""` you will be accepted |
| 1.1.13 | `parse_positive_int`: removing the `try/except` | Non-numeric input will result in an Unhandled Exception (500) instead of a 400 error message |
| 1.1.14 | `parse_positive_int`: Replacement `parsed <= 0` to-`parsed < 0` | 0 will be accepted as a valid id in URL-based operations (DELETE) |
| 1.1.15 | `parse_positive_int`: receiving `"3.0"` quietly (`int(float(value))` instead of `int(value)`) | Decimal-technical input will be accepted in the URL, as opposed to rejecting the same input in the JSON body |

### 1.2 Advanced endpoints — JSON / encoding / numerical representation
More subtle edge cases, based on real Python and JSON features, are easy to accidentally mutate when "enhancing" the code.

| # | Mutation to Introduce | Description |
| --- | --- | --- |
| 1.2.1 | `is_valid_id`: Adding a branch `elif isinstance(value, float): return value > 0` | `id: Infinity`/`id: NaN`(Python's JSON module accepts by default a path `allow_nan=True`) will undergo validation -`Infinity > 0` is True, then `int(value)` will throw `OverflowError` Untreated (500) |
| 1.2.2 | added `int(value, 0)`(auto base detection) instead `int(value)` the usual | Strings like `"0x5"`, `"0o7"`, `"0b101"` will be accepted as a valid id instead of being rejected |
| 1.2.3 | Added a test that rejects any id with a space (`if " " in value: return False`) before the parse | `" 5"`/`"5 "` will be mistakenly rejected, contrary to the current normal behavior (because `int(" 5 ")` working in Python) |
| 1.2.4 | Planting regex-partials to check digits (ASCII only) | Python's `int()` Actually supports some of the Unicode characters (eg `"٥"` Arabic,`"５"` full-width) — an incomplete regex will change this availability in an undocumented and inconsistent way |
| 1.2.5 | `id` Sent as a JSON number with `.0`(for example `5.0`) — currently completely deprecated (only int/str are supported); Planting "convenience" that accepts a float with a zero decimal part | technical-decimal id (`5.0`) will be accepted contrary to the documented contract "must be a positive integer" |
| 1.2.6 | Planting gall through `float()` In the middle of the id processing chain (like 1.1.8) on very long ids (300+ digits) | Silent precision loss — two "different" ids converge to the same float and accidentally collide |
| 1.2.7 | receiving `id` as a list with a single member (`[5]`) by planting `except (TypeError, ValueError): value = value[0]` inside the try | A non-standard formatted id is silently accepted, contrary to API intent |

### 1.3 Field `User.id`
| # | Bug | Description |
| --- | --- | --- |
| 1.3.1 | skip a call to `is_valid_id`(deletion of the entire condition) | Each value will be accepted as an id (including objects, lists) |
| 1.3.2 | getting float as id (change `is_valid_id`) | `1.5` will appear as user id |
| 1.3.3 | getting bool as id (`true`) | Yozer with `id: true`⇒ will actually be stored as `1` |
| 1.3.4 | Non-normalization `user["id"] = int(...)`— leaving the id as a string when sent as a string | `"5"` and-`5` will be considered as two different contributors in the duplication check |
| 1.3.5 | Changing the order of tests - first duplicate then type | An incorrect error message will be returned when id is both duplicate and invalid |

### 1.4 Field `User.name`
| # | Bug | Description |
| --- | --- | --- |
| 1.4.1 | Removing a test `"name" not in user` | Missing field will go to `is_non_empty_str(None)`— will still be caught, so it is a "transparent" mutant (a good edge case for testing that makes sure that this "double" testing does make a difference) |
| 1.4.2 | receiving a number as `name`(Change `is_non_empty_str` to-`value is not None`) | `name: 123` will be accepted |
| 1.4.3 | Introducing incorrect normalization that removes invisible characters (`\u200b`, `\u200c`) **from the actual stored value**, not just from the test | A name stored in the repository is different from the value originally sent — GET returns a different value than POST |
| 1.4.4 | Planting a uniqueness check for `name` based on a normalized value (strip) | Two users intentionally with the same name with/without trailing whitespace (`"Cohen"` versus `"Cohen "`) will be rejected as "duplicates" by mistake, in contrast to the original behavior which treats names only as non-unique descriptive text |

### 1.5 field `Book.id` / `Book.title`
| # | Bug | Description |
| --- | --- | --- |
| 1.5.1–1.5.5 | Equivalent to 1.3.1–1.3.5 and 1.4.1–1.4.4 for `Book.id`/`Book.title` | All the above variations are also relevant at the same time to `add_book` |
| 1.5.6 | inspection `is_non_empty_str(book.get("title"))` is replaced by an incorrect check that you receive `None` | Missing title will be received as `null` |
| 1.5.7 | Planting incorrect uniqueness validation on `title`(while only the id should be the unique key) | A book with the same title as another existing book (legitimate scenario — several copies/editions) mistakenly rejected as "duplicate" |

### 1.6 Field `Loan.userId` / `Loan.bookId`
| # | Bug | Description |
| --- | --- | --- |
| 1.6.1 | Changing the order: first `user_exists` Then type-check | A non-numeric input will cause the function to crash `user_exists`(which expects an int) ⇒ 500 |
| 1.6.2 | Removing the test `if user_id is not None and not is_valid_id(...)` | Invalid values ​​(like float) will be passed on until crashing in `int()` |
| 1.6.3 | Reverse the logic `if book_id is not None` to-`if book_id is None` | The test will run always/never, so an invalid type for bookId will not be detected when userId is also empty |
| 1.6.4 | Non-normalization `int(user_id)`/`int(book_id)` | String values ​​will be stored in the loan record, breaking late comparisons (`==` between `"3"` to-`3`) |
| 1.6.5 | Planting a wrong test that rejects a loan when `userId == bookId`(random correlation between two completely different namespaces) | True false-positive rejections when a user id and a book happen to coincide — there is no real logical connection between the two namespaces |

### 1.7 Field `Hold.id` / `Hold.userId` / `Hold.bookId`
| # | Bug | Description |
| --- | --- | --- |
| 1.7.1 | Reverse the test order `"id" not in hold` opposite `is_valid_id` | Wrong error message when the key is both missing and (theoretically) incorrect |
| 1.7.2 | Denormalize to int for `hold["userId"]`/`hold["bookId"]` only (left `id` normalized only) | Type inconsistencies between fields of the same entity |
| 1.7.3 | Complete skipping of validation `bookId`(deleting the 3 lines) | You can create a hold with a completely invalid bookId |

### 1.8 ID fields through the URL (Path Params) —`delete_user`, `delete_book`, `delete_hold`, `delete_loan`
| # | Bug | Description |
| --- | --- | --- |
| 1.8.1 | change `parse_positive_int` so that he will also receive `"0"` | A deletion with id=0 will not be blocked |
| 1.8.2 | failure to call `parse_positive_int` at all (direct use of `int(id)` without try) | Non-numeric input in URL will result in 500 |
| 1.8.3 | on-`delete_loan`— use only `parse_positive_int` on `user_id` and not on `book_id`(or vice versa) | Half of the validation disappears, one of the parameters can be received incorrectly |

---

## Chapter 2 — Bugs from individual API calls (Logic bugs, not Type)

### 2.1 System-wide aspects (JSON parsing / HTTP / Routing)
Faults at the infrastructure level that are relevant to several endpoints at once, and not to a single field but to the behavior of the entire request.

| # | Bug | Description |
| --- | --- | --- |
| 2.1.1 | removing the `if request.is_json` on-`/reset`— direct call to `request.get_json()` without inspection | A reset request without a body/with an incorrect Content-Type will throw an unhandled 400/415 instead of silently ignoring |
| 2.1.2 | `add_user`/`add_book`/`add_loan`/`add_hold`— a call to `request.get_json(silent=True)` No None check later | An empty/non-JSON body will pass `None` further,`None.get("id")` will throw AttributeError (500) instead of 400 |
| 2.1.3 | Getting an **array** JSON (`[]` or `[{"id":1}]`) instead of object as body, without `isinstance(data, dict)` | A non-empty list will pass all checks on and crash in `.get()`(The list does not have `get`) |
| 2.1.4 | Mass Assignment — the system does not filter unexpected fields in the body (`{"id":1,"name":"x","isAdmin":true}`) and stores the entire object as it is | Extraneous fields "stick" to the record and are returned in GET, revealing an undocumented structure |
| 2.1.5 | added `methods=["GET","POST"]` Accidentally root DELETE of `/users/<id>` | A GET call will accidentally trigger the delete logic |
| 2.1.6 | removing the `<id>` the implicit type converter (string) and replacing it with `<int:id>` | A request with a non-numeric id (`/users/abc`) will return Flask's generic 404 before the internal code gets a chance to return a consistent 400 like the rest of the system |
| 2.1.7 | Adding a case-sensitive double route (`/Users` to the side `/users`) which points to old logic | Different behavior between `/users` to-`/Users` |
| 2.1.8 | `strict_slashes=False` Added in some Rautes and not all | `/books/` behaves differently from `/books` in some endpoints |
| 2.1.9 | Full traceback exposure (Flask `debug=True`) in any unhandled exception | Leakage of internal information (paths, variable names) to the client - relevant for security/privacy testing |
| 2.1.10 | logs (`logger.error`/`logger.info`) that print the entire raw request body | Leakage of sensitive information to logs if sensitive fields are added in the future |

### 2.2 `/reset` (POST)
| # | Bug | Description |
| --- | --- | --- |
| 2.2.1 | The cleaning order changes so that -`loans`/`holds` Do not reset | partial reset — old data remains |
| 2.2.2 | Change of condition `if "users" in data` to-`if data.get("users")` | reset with `"users": []` will behave differently |
| 2.2.3 | `users.extend(...)` Replaced by a direct assignment inside the if without `global` | `UnboundLocalError` while running |
| 2.2.4 | Failure to reset one of the collections (eg `books`) before loading new data | Old books will be "glued" to the new dataset |
| 2.2.5 | The lack of type validation on the payload — the code "relies" on the fact that `data["users"]` It is a list and does not check | Sending `"users": "abc"` cause to `users.extend("abc")` Run successfully in silence and add 3 "phantom" users (`'a'`, `'b'`, `'c'`) — crashes only later when trying `.get("id")` on a single string |
| 2.2.6 | The absence of a uniqueness check within the seed itself (`"users": [{"id":1},{"id":1}]`) | Planting a "fix" that activates the normal duplication check even on reset will break legitimate test seeds |

### 2.3 `POST /users`
| # | Bug | Description |
| --- | --- | --- |
| 2.3.1 | Duplication check `user.get("id") in [...]` is performed **before** the normalization of the id | `id: "5"` will not be recognized as duplicate mol `id: 5` exists |
| 2.3.2 | Removing the duplicate check completely | You can add two users with the same id |
| 2.3.3 | Changed success status code from 201 to 200 | Incorrect response code successfully |
| 2.3.4 | Changed "missing id" error code from 400 to 404/422 | Incorrect status code on validation failure |
| 2.3.5 | `users.append(user)` turns into `users.insert(0, user)` | The order of the users in the pool changes - affects `GET /users` If there is a dependency, fine |
| 2.3.6 | The object that is returned after POST is the user before normalization (id as a string) | client receives id as `"5"` while the repository stores `5` |
| 2.3.7 | Planting partial "cleaning" of foreign fields (ref. 2.1.4) before returning it to the client, which does not correspond to what is actually kept in the database | The API response exposes an inconsistent internal structure |

### 2.4 `DELETE /users/<id>`
| # | Bug | Description |
| --- | --- | --- |
| 2.4.1 | Reverse condition: `Cannot delete user with active loans` Tested on `bookId` instead of `userId` | Incorrect blocking logic — a user will be deleted even with active loans, or a user without loans will be blocked |
| 2.4.2 | Removing the holds check (only loans are checked) | You can delete a user with an active hold |
| 2.4.3 | Removing the loans check (only holds are checked) | You can delete a user with an active loan - an "orphaned" loan for a non-existent userId will remain |
| 2.4.4 | `users.remove(user)` Replaced by deletion by wrong index (`users.pop(0)`) | The wrong user is deleted |
| 2.4.5 | Changing the success code to 204 without changing documentation/body | Inconsistency |
| 2.4.6 | Not Found is returned even when the user actually exists (`if user:` turns into `if not user:`) | A normal deletion will be reported as a 404 |
| 2.4.7 | **Lack already exists in the code:** Contrary to `delete_book`, there is no "the user exists at all" check here (404) *before* the loans/holds checks - reverse order from `delete_book`. Planting a mutation that makes it worse (removing the `if user:` completely final) | Attempt to delete `userId` which does not exist but "merges" with an old loan/hold record (data corruption) will mistakenly return "Cannot delete user with active loans" (400) instead of "User not found" (404) |

### 2.5 `GET /users` (Search)
| # | Bug | Description |
| --- | --- | --- |
| 2.5.1 | removal `.lower()` from-`query` | Search becomes case-sensitive contrary to intent |
| 2.5.2 | `if query else users` turns into `if query else []` | Search without parameter `q` Returns an empty list instead of all users |
| 2.5.3 | Search `query in str(user)` turns into `query == str(user)` | A partial search (substring) becomes an exact search only |
| 2.5.4 | Filter is not performed at all (`results = users` always) | parameter `q` Ignores and returns all entries |
| 2.5.5 | change `str(user)` to-`json.dumps(user)` | Search sensitive to key format (double versus single quotes) — certain queries that worked before stop catching |

### 2.6 `POST /books`
| # | Bug | Description |
| --- | --- | --- |
| 2.6.1–2.6.6 | Corresponds to 2.3.1–2.3.6 for books | Duplicates before normalization, removing duplicate check, wrong status code, etc. |
| 2.6.7 | the-`else` on-`add_book`(different from `add_user` that doesn't use else) is removed, causing a fallthrough | Code will run twice / return double response or none |

### 2.7 `DELETE /books/<id>`
| # | Bug | Description |
| --- | --- | --- |
| 2.7.1 | The "book does not exist" check (404) is removed - a direct transition to the loans/holds check | Deleting a non-existent book will fail with "Cannot delete book with active loans" (false positive) instead of 404 |
| 2.7.2 | Reversing the conditions of loans inspection (`bookId` replaced by `userId`) | Incorrect block/no block |
| 2.7.3 | Removal of holds check | A book with an active hold will be deleted |
| 2.7.4 | Removal of loans check | A borrowed book will be deleted — the loan will remain a reference to a non-existent bookId |
| 2.7.5 | The filter `books = [b for b in books if b.get("id") != book_id]` turns into `==` | All books except the one requested will be deleted (reverse deletion) |
| 2.7.6 | `booksRemaining` The response is calculated **before** the actual deletion | An incorrect number is returned to the client |

### 2.8 `GET /books`, `GET /books/<id>`
| # | Bug | Description |
| --- | --- | --- |
| 2.8.1 | Same as buggy 2.5.1–2.5.4 for books |  |
| 2.8.2 | `get_book`: the condition `if book:` Reverse → existing book will return 404 |  |
| 2.8.3 | `get_book`: skipping over `parse_positive_int`, direct comparison of URL string to id (int) | It will never find — every request will return a 404 even to an existing book |
| 2.8.4 | Lack of parameter support `q` on-`GET /loans`(different from the other endpoints) — planting partial/buggy support using the buggy filter from 2.5.3/2.5.4 | New API inconsistency against other endpoints |

### 2.9 `POST /loans`
| # | Bug | Description |
| --- | --- | --- |
| 2.9.1 | The order of the tests changes - first `book_exists` And then `user_exists` | False error message when both do not exist |
| 2.9.2 | Removing the "Loan already exists" check | You can create an identical double loan |
| 2.9.3 | Removing the "User already has an active loan" check | One user can borrow several books at the same time (change in business intention - invariant "1 user / 1 loan") |
| 2.9.4 | Removing the "Book is already loaned" test | A book can "be loaned" to several contributors at the same time |
| 2.9.5 | Reversing the order of tests 2.9.2–2.9.4 so that the message displayed does not correspond to the actual situation | Client receives an error message irrelevant to the real situation |
| 2.9.6 | `user_exists`/`book_exists` Tested before type validation (back to bug 1.6.1) | 500 for improper input |
| 2.9.7 | Loan record is saved in a different order of fields/with additional fields | Does not affect functionality but can break strict JSON structure checks |

### 2.10 `DELETE /loans/<user_id>/<book_id>`
| # | Bug | Description |
| --- | --- | --- |
| 2.10.1 | The filter builds a new list with `and` which becomes `or` | Any loan that matches the userId **or** bookId will be deleted (deletion is too broad) |
| 2.10.2 | `before_count == after_count` turns into `!=`(404 condition reversal) | A successful deletion will be reported as a 404 and vice versa |
| 2.10.3 | User_id/book_id parameters are exchanged in the inner call | It will never find a matching loan |

### 2.11 `GET /loans` (Search + Filters)
| # | Bug | Description |
| --- | --- | --- |
| 2.11.1 | the test `if user_id is not None and user_id != ""` turns into `or` | A filter will always run even without a parameter |
| 2.11.2 | filtering `book_id` applied to `results` the original (`loans`) and not on `results` already filtered by `user_id` | AND filter actually becomes OR/ignores the first filter |
| 2.11.3 | id validation in filters (`parse_positive_int`) removed | A non-numeric parameter will result in 500 in the comparison |
| 2.11.4 | Planting a change that allows a parameter `userId` as a list (`?userId=1&userId=2`) and handles it incorrectly (concatenation of strings instead of an error) | A search with multiple values ​​produces an incorrect result |

### 2.12 `POST /holds`
| # | Bug | Description |
| --- | --- | --- |
| 2.12.1 | The order of id/userId/bookId checks alternates | Inconsistent error message when several fields are missing at the same time |
| 2.12.2 | Removing a test `user_exists` | hold will be created for a user that does not exist |
| 2.12.3 | Removing a test `book_exists` | hold will be created for a book that does not exist |
| 2.12.4 | Removing the "Hold already exists" check (by id) | A double hold with the same id will be added (overriding an existing record will actually create a duplicate) |
| 2.12.5 | Normalization to int is performed only on `id`, not on `userId`/`bookId` | Type inconsistency within a hold record |
| 2.12.6 | **A-symmetry with `add_loan`:** `add_loan` Checks 3 business duplication conditions (existing loan, user already has a loan, busy book) while `add_hold` Checks only one condition (double id). Planting a wrong "fix" that adds a "user already has a hold" check (a non-existent and unwanted restriction in the source) | A user who wants to queue for several books at the same time (a legitimate scenario!) will be mistakenly blocked |

### 2.13 `DELETE /holds/<id>`
| # | Bug | Description |
| --- | --- | --- |
| 2.13.1 | The filter `hold.get("id") != hold_id` turns into `==`(reverse deletion) | All holds except the requested one will be deleted |
| 2.13.2 | The 404 condition becomes (`before_count != len(holds)`) | The opposite result than expected |
| 2.13.3 | Planting a new incorrect check ("hold is related to an active loan") that blocks deletion — unlike `delete_book`/`delete_user`, currently there is no such block here in the original implementation | will cause a failure in the normal flow of cancellation/realization of hold |

### 2.14 `GET /holds`
| # | Bug | Description |
| --- | --- | --- |
| 2.14.1–2.14.4 | Same as 2.5.1–2.5.4 search bug for holds |  |

---

## Chapter 3 — Bugs from "logical" call combinations (reasonable flows)

The basic sequence: **Create a user → Create a book → Request a hold → Execute a loan → Delete the hold/execute a return (deleting a loan) → Delete a user/book**. Includes reasonable variations (some contributors/books, cancellation and return, search after action).

| # | scenario (sequence) | Potential planting bug | result |
| --- | --- | --- | --- |
| 3.1 | User→Book→Hold→Loan (on the same book/user) | Removing the connection between hold and loan —`add_loan` Does not check and does not close existing holds | The hold remains "open" even after the book has actually been borrowed, and prevents the deletion of a book/user even when the loan has already ended |
| 3.2 | Hold on a book → Loan for the same book by a **other** user | The absence of a check that a loan cannot be created for a book with an active hold of another user | A book with a hold by user A is actually loaned to user B — bypassing the purpose of the hold |
| 3.3 | Loan → DELETE loan (return) → DELETE book | planting a bug in `delete_loan` that deletes the loan only partially (`and`→`or`, R. 2.10.1) | Deleting a book that is "still borrowed" will fail / an unrelated book will be damaged |
| 3.4 | Loan → DELETE loan → Loan again on the same userId+bookId | Removal/weakening of the test that allows the creation of an identical loan again after deletion (cf. 2.9.2) | An "old" duplicate loan that was not properly deleted will be created on the new side |
| 3.5 | User A makes a Hold on book X, User B tries to Hold on the same book X | Planting a wrong "fix" that blocks multiple holds on the same book (there is no such prevention today, and this is a legitimate queue-waiting scenario) | The queue-wait scenario (multiple holds) is broken |
| 3.6 | Loan failed because the book is already borrowed → Hold attempt on the same book | Wrong mixing between `book_exists`(physical existence) and "availability for loan" | Hold will fail with "Book does not exist" error |
| 3.7 | DELETE user who has hold only (no loan) | Removing the holds check in `delete_user` (2.4.2) | A user with an active hold will be deleted, and the hold will remain "orphaned" pointing to a non-existent userId |
| 3.8 | DELETE a book that has an active loan, then attempt to create a new loan for the same bookId (after the deletion failed as expected) | Planting a partial deletion that is actually carried out even though the response reports "failed" (lack of atomicity) | The API response says "failed" but the operation was actually performed |
| 3.9 | 2 users, 2 books, cross query (User1↔Book1, User2↔Book2), deletion of User1 | Reverse userId/bookId in checking active loans (2.4.1) | User1 will be accidentally deleted despite an active loan, while User2 will be blocked for no reason |
| 3.10 | Hold → Loan → DELETE hold (attempt to "cancel hold" after it has actually been borrowed) | Lack of validation that the hold is still relevant, combined with an incorrect deletion mutation (2.13.1/2.13.2) | Inconsistent state: holds/loans are not synchronized |
| 3.11 | Full sequence is correct: User→Book→Hold→Loan→DeleteLoan→DeleteHold→DeleteBook→DeleteUser | Each of the bugs in 2.4.1–2.4.6, 2.7.1–2.7.6, 2.13.1–2.13.3 will break a different point in the full sequence | The system's most "standard" happy-path sequence is broken at every point—critical for regression testing |
| 3.12 | 3 books, 3 users, each user borrows another book, one user returns and takes another user's book after it has been returned | Removal of the "Book is already loaned" check (2.9.4) in combination with DELETE loan timing | A book is "double-booked" between two users at the same time if the DELETE and POST of a new loan are not atomic |
| 3.13 | `GET /loans?userId=X&bookId=Y` after the loan/return sequence | Bug 2.11.2 (bookId filter does not accumulate on userId) | Incorrect search results are displayed after perfectly normal actions |
| 3.14 | `/reset` in the middle of a sequence (reset between test scenarios) with partial seed data (`users` only, without books/loans/holds) | 2.2.1/2.2.3/2.2.4 bug in partial refresh | "Dirty" state between tests — subsequent tests will fail due to state leakage |
| 3.15 | Loan → DELETE loan (return) → **same** userId+bookId request Loan again immediately | Planting an "old" state that remains in a hidden list (eg if `delete_loan` builder `loans[:]` slice-copy instead of direct assignment) | The new loan was successfully created as far as the API is concerned, but an "old copy" still exists and affects future counts |
| 3.16 | User1 hold on book X → User2 hold on the same book X (waiting queue, currently allowed) → Loan to **User2** (putting User1 ahead of the queue) | Planting a wrong "FIFO enforcement" that blocks User2 from borrowing because "not first in line" — a restriction that does not exist today | A legitimate business scenario (whoever arrives first can borrow) is broken |
| 3.17 | Hold on a book → DELETE hold (cancellation) → DELETE book succeeds → POST new loan for the same bookId (which no longer exists) | Removing a test `book_exists` on-`add_loan`(1.6.2/2.9.6 mutation) combined with this natural sequence | You can create a loan for a book that has been completely deleted from the system - "ghosts" |
| 3.18 | User+Book+Hold+Loan for **two** users in two completely separate requests (completely different bookId) | Planting a mutable default argument in a common helper function (classic anti-pattern in Python: `def helper(cache={})`) | An action on User A/Book A accidentally "contaminates" a result of the unrelated User B/Book B |
| 3.19 | DELETE loan (return) → immediately `GET /loans?bookId=X` for a returned test | Planting a secondary index (secondary cache) for search that is not synchronized with the main list in real time | The deleted loan still temporarily "appears" in search results immediately after the deletion |
| 3.20 | Full sequence (3.11) but with a Book with the same title as the title of another book that has already been deleted (title reuse) | Planting incorrect uniqueness validation on `title`(cf. 1.5.7) | A new book with a title that already existed before (and was deleted) was mistakenly rejected as "duplicate" |

---

## Chapter 4 — Bugs from Illogical / Low-Probability Input Sequences (Stress / Edge Sequences)

These scenarios repeat the same action over and over again, or perform an unnatural (but legal in terms of the API) order that will reveal race / state leak / lack of idempotency situations.

| # | scenario | Potential bug | result |
| --- | --- | --- | --- |
| 4.1 | Creating the same user (`POST /users` with the same id) many times in a row | Removing/Weakening Duplicate Check (2.3.2) | Multiple identical records in `users`— Delete will remove only one record out of several duplicates |
| 4.2 | delete it youzer (`DELETE /users/<id>`) many times in a row | Planting a bug that reverses the test so that the second call will throw a 500 (e.g. access to `user.get(...)` on `None`) | A double call will crash instead of gently returning a 404 |
| 4.3 | Repeated creation and deletion of the same hold id in a fast loop (Create→Delete→Create→Delete... 50 times) | Leakage of "ghost" records in combination 2.12.4 (removal of "Hold already exists" check) | After X iterations,`holds` Contains copies that block delete_book/delete_user |
| 4.4 | Registration → deletion → immediate registration with the same id but `name` different | planting an incorrect lookup in `user_exists` which relies on out-of-date state | The "new" user fails to create because the system thinks the old one still exists |
| 4.5 | Creating N holds for the same bookId by different users (waiting queue), then deleting them all in reverse order (LIFO) | A deletion filter that assumes a FIFO order (for example using a fixed index instead of filtering by id, a variation of 2.13.1) | false hold is deleted when the deletion order is different from the creation order |
| 4.6 | `POST /loans` Failed (book already borrowed) → retry loop of the same request 100 times | A non-idempotent operation that by mistake **yes** adds a record in every attempt despite a reported failure (ref. 3.8) | Multiple "duplicate" loans in practice for the same bookId even though the API claims that only one loan was created |
| 4.7 | Deleting a book/user before it was ever created (`DELETE /books/999`) repeats many times | Incorrect accumulated side-effect (e.g. counter/log without control) | Log flooding / slowing down the system under the load of repeated incorrect requests |
| 4.8 | `POST /reset` is called repeatedly while a chain of other operations is running | Non-thread-safe access to global lists (relevant if threading is added) | Race condition between reset and other operations - non-deterministic behavior |
| 4.9 | Create hold → cancel → recreate with same `id` but `bookId`/`userId` Completely different, repeats itself | Planting a wrong "optimization" that reuses (cache) the hold record by id without actually updating fields | Hold contains an incorrect user/book combination — "ghosts" from the previous iteration |
| 4.10 | Loan, Hold and user deletion for the same userId in a very tight/almost-simultaneous sequence | A general lack of atomicity around `any(...)` + `.append(...)` without lock | Classic race condition (TOCTOU) if the code is changed to be parallel |
| 4.11 | Delete user → Delete same user → Add user with the same id → Delete again, in a loop dozens of times | remove by object value (`users.remove(user)`) and not by id, in combination with "equal" users in terms of content | Removing the wrong user when there are two identical dicts in created-deleted-created content |
| 4.12 | `GET /users?q=...` with a long/special query (regex meta-characters,`%00`, emoji) repeats itself | planting change from `in`(substring) to `re.search` without escaping | Regex Injection / Potential ReDoS in search |
| 4.13 | Adding a user → adding the same book N times with a different id but the same title → search by title | Planting a wrong "fix" that adds a uniqueness check on title (cf. 1.5.7/3.20) | Adding books with identical titles (legitimate scenario — several copies) is blocked by mistake |
| 4.14 | `POST /holds` with the **same** `id` but different `userId`/`bookId` values, 50 times in quick succession | Planting a duplicate check that calls a local snapshot of `holds` which is not updated in real time | Under fast enough running (theoretically, in an async/threading environment) several holds with the same id may be created |
| 4.15 | Repeated attempt (100 times) to create the same User after being blocked by an active hold that has been deleted in the meantime | Planting an "optimization" with a short-circuit cache that assumes the request will fail again like before | False negative — a user cannot re-register even after the actual block has been removed |
| 4.16 | Creating 10,000 books and then `GET /books?q=`(without query) in a repeating loop | Planting filter enforcement even without q (extreme variation of 2.5.2) running `str(book)` on every record in every request | Potential performance/DoS issue under load |
| 4.17 | Long-term fuzzing: intermittent random creation/deletion in thousands of requests | Removing the keyword `global` Accidentally from one of the DELETE functions in a future refactor | `UnboundLocalError` which is revealed only in a certain branch within the function - very difficult to locate |
| 4.18 | Retry storm: same request `DELETE /loans/<u>/<b>` Sent twice in a tight sequence (due to timeout) | Planting a change in the filter `delete_loan` which removes loans according to `userId` only (ignoring `bookId`) on a retry | The second call (which should fail gracefully with a 404) accidentally deletes a completely different loan of the same user with a different book |

---

## Methodological note

- All the above bugs are **problems that can be introduced into the existing code** (mutation), not bugs that already exist in the actual system - except for the cases that are explicitly marked as "a lack that already exists in the code" (for example 2.4.7, 2.9.3, 2.12.6), which indicate a real inconsistency that should be recognized before another mutation is implanted in it.
- Some of the bugs in chapters 3–4 are also based on "existing functional deficiencies" in the system (for example: there is no real logical connection between hold and loan, no atomicity, no thread-safety) — these **do not** count as planting bugs in themselves, but as opportunities to plant a bug that worsens existing behavior (expressly marked in the tables, for example 3.1, 3.2, 4.10).
- It is recommended to use this table as a basis for the Mutation Testing matrix: for each row - plant the bug, run the existing test package, and make sure that at least one test "catches" (kills) the mutation. A line that no test captures indicates a gap in test coverage.
