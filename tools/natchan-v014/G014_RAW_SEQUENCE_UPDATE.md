# g014 raw sequence update

The review-bundle gateway now recomputes partial application from consecutive
original `research` HTTP records. Producer verdicts and g014-sequence duplicate
records do not supply the verdict. Before and after GETs must succeed, refer to
the identical path, return the same non-null identity, use the same nonempty
session, and have strictly ordered monotonic timestamps. An intervening HTTP
operation prevents this immediate-sequence join. External concurrent clients
are not excluded by these records and severity still requires context.

Assignee login and milestone ID projections compare references rather than
objects with IDs. Metadata is excluded. At least one requested change applied
and one kept, with no unknown field outcome, is required for `partial`.

G014 pair bindings come from the retained plan, but actual field values,
responses and controls come from original research records. Successful control
readbacks must retain the requested value and identity. Cross-actor, reordered
or unequal-value pairs are not qualified. Pair findings mean observed outcome
differences, not by themselves a business-rule violation.

GIT-C2-PR is a separate version-qualified signature related to GIT-C2, preserving
the existing Issue signature. GIT-C11 requires a correlated poster-as-reviewer
server error, an earlier same-session /user result, matching user ID in the
error, and the actor login actually present in the reviewers payload. Both new
signatures are qualified only for tested Gitea 28.1.0.

Stored absent-branch references are observation patterns only. A prior same-repo
404 branch check and no intervening branch mutation are required. Release edit
acceptance is not promoted to full C8. Label ID measurements retain their prior
evidence tier. Background error messages do not create extra HTTP observations.

The original summary adapters can still report scalar-projection or raw-pair
limitations. These refer to those adapters, not absence of raw response bodies:
the raw sequence classifications above are independent. Missing raw context is
not filled from NOTE.md or manual review.

Validation: twelve standard-library tests plus the frozen 433-step g014 run.
Expected raw observations: seven 500s, six partial updates (four Issue/two PR),
eight create/update differences, C1=2, Issue C2=2, PR C2=2, C11=1, and six
accepted absent-branch reference observations. Generic and product-specific
labels overlap; do not add rows to count distinct bugs.

Run using the existing gitea-review-bundle adapter in worker.py or run.py.
No live service or saved test execution is needed for this analysis.
