# Native lifecycle evidence: known-bug matching

Offline raw-evidence analysis; no new SUT requests; no producer verdicts imported.
A catalog signature match does not prove identical root cause.

Known bug IDs: GIT-C2
Known-bug occurrences: 1

## event-d1094434e20c5eea5d5e2118d14e

Known bugs: GIT-C2
Group: LIFE_4_serial_AB
Tags: SERVER_5XX, FIELD_PERSISTED_DESPITE_ERROR
Deleted-reference context verified: True
Primary source: {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 406}

Witnesses:
- {"kind": "error_log", "source": {"file": "sut.log", "sha256": "3f5bedb21c0097434b66c3c1e6e013f64aaa7de5b204809c3acc934b3137287b", "record": 162}, "message": "2026/10/22 18:13:09 .../api/v1/repo/issue.go:817:EditIssue() [E] InternalServerError: milestone does not exist [id: 8, repo_id: 19]"}
- {"kind": "router_completion", "source": {"file": "sut.log", "sha256": "3f5bedb21c0097434b66c3c1e6e013f64aaa7de5b204809c3acc934b3137287b", "record": 163}}
- {"kind": "root_identity", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 384}, "value": 19}
- {"kind": "item_root_identity", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 399}, "value": 19}
- {"kind": "before", "field": "body", "value": "initial-body", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 399}}
- {"kind": "persisted_readback", "field": "body", "value": "life-B-LIFE_4", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 409}}
- {"kind": "persisted_readback", "field": "body", "value": "life-B-LIFE_4", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 411}}
- {"kind": "persisted_readback", "field": "body", "value": "life-B-LIFE_4", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 413}}
- {"kind": "persisted_readback", "field": "body", "value": "life-B-LIFE_4", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 415}}
- {"kind": "deleted_reference", "source": {"file": "native.log", "sha256": "9bc23721c413d49969335b7c3bda65b85d6f55b2ab21719220b1a7496ffa076c", "record": 403}, "value": 8}
