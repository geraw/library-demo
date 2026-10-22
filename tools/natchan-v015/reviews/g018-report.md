# Natchan v015: Gitea native-tool evidence

Generated mechanically from retained artifacts. No manual finding narrative was consumed.

| Run | Requests (all callers) | HTTP 5xx | Tool nested 2xx | Process | Native faults |
|---|---:|---:|---:|---|---:|
|evomaster_rep1|14441|88|601|failed|unknown|
|evomaster_rep2|14725|64|673|failed|unknown|
|evomaster_rep3|15392|38|326|failed|unknown|

## Log-signature candidates

These are descriptive/error signatures, not confirmed unique bugs.

| Signature | Log occurrences |
|---|---:|
|GIT-LOG-MISSING-ISSUE-COMMENTS|133|
|GIT-LOG-INIT-TEMPLATE|28|
|GIT-LOG-LICENSE-TEMPLATE|13|
|GIT-LOG-OWNER-TEAM-MISSING|85|
|GIT-LOG-TEAM-UNIT-UNIQUE|14|
|GIT-C1-SIGNATURE|1|
|GIT-LOG-RELEASE-OBJECT-MISSING|1|

## Common classifier

Rule occurrences: {"GEN-SERVER_ERROR": 190, "GITEA-SERVER_ERROR": 190}

## Evidence and limits

- Signature matches are separate from common exact known-bug matches.
- Error log counts are not additional HTTP failures; do not sum them.
- Adjacent response candidates are not causal correlation or state evidence.
- Unknown native fault count is not zero.

## evomaster_rep1

Issue PATCH statuses: {"404": 282, "422": 27}

Search complete: True. Process exit codes: [1].

Unmatched error lines: 0.

## evomaster_rep2

Issue PATCH statuses: {"404": 273, "422": 38, "409": 3, "500": 1}

Search complete: True. Process exit codes: [1].

Unmatched error lines: 0.

- GIT-C1-SIGNATURE at sut.log:7766; adjacent compatible response candidate: True; exact bug confirmation: false; partial persistence: not evaluable.

## evomaster_rep3

Issue PATCH statuses: {"404": 335, "422": 14}

Search complete: True. Process exit codes: [1].

Unmatched error lines: 0.

- GIT-LOG-RELEASE-OBJECT-MISSING at sut.log:7539; adjacent compatible response candidate: True; exact bug confirmation: false; partial persistence: not evaluable.
