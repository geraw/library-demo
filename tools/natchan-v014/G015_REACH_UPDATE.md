# g015 reach and request-context update

The gateway and `report.md` now include repository-scoped route coverage from
every server access record, grouped by HTTP method, route family and response
class. Source-linked witnesses are retained in JSON. Nested `/repos/{owner}/{repo}/...`
is distinguished from repository detail and `/user/repos`. Issue PATCH counts
exclude comment edits and include every physical attempt in the access log,
including repeats and authentication/negative-test attempts. They are not a
count of distinct logical scenarios or valid authenticated edits.

A zero 2xx count establishes that no successful nested repository response was
observed. It does not establish the cause of each rejection. The gateway does
not infer nonexistent repositories from a 4xx status alone.

Schemathesis tables display both operation template and actual path examples.
Every witness retains its original Content-Type and source record. A 500 with
`multipart/form-data` lacking a nonempty boundary receives an explicit malformed
multipart context, computed from request headers, independent of operation name
or the native check's prose. Such a response does not establish execution of the
business resource operation. Generic server-error classification is preserved.

The report explicitly lists B-OWNERS as unevaluable without a separate raw
confirmation artifact. Baseline owner-team error lines remain separately counted.
Cloud confirmation must retain the successful Owners-team rename, initial owner
role and same-actor identity, and subsequent edit/delete responses in order.
An analyst's narrative is not imported as a confirmed finding and is not
retroactively attributed to a baseline run. This update does not implement a new
live confirmation runner or assert that confirmation evidence was supplied.

Re-run using the unchanged command in G015_NATIVE.md. Nine standard-library
unit tests cover prior parser behavior plus route selection, zero/success
controls and multipart header controls. The full six-run integration checks
metadata parity, unchanged 126 server errors, zero successful nested repository
responses, 2306 issue PATCH rejections, and 24 malformed multipart 500 exchanges.
