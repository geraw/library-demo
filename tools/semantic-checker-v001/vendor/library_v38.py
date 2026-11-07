#!/usr/bin/env python3
"""Sequence-local semantic evaluator for the frozen Library V38 benchmark.

Official scoring is intentionally fail-closed: HOLD_OWNERSHIP and LOAN_LIMIT
are counted only when a single retained/replayed tool test starts from an empty
SUT and contains the complete legal prefix plus the violating successful HTTP
operation.  A flat campaign trace is evaluated only as a diagnostic because it
may stitch state across independent tests.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CLASSES = ["HOLD_OWNERSHIP", "LOAN_LIMIT"]


def _event_from_line(line: str) -> Optional[Dict[str, Any]]:
    text = line.strip()
    if not text:
        return None
    if "MODEL_EVENT " in text:
        text = text.split("MODEL_EVENT ", 1)[1].strip()
    try:
        value = json.loads(text)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def load_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [
        event
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if (event := _event_from_line(line)) is not None
    ]


def _path(event: Dict[str, Any]) -> str:
    value = "/" + str(event.get("path") or "").split("?", 1)[0].strip("/")
    return value.rstrip("/") or "/"


def _method(event: Dict[str, Any]) -> str:
    return str(event.get("method") or "").upper()


def _status(event: Dict[str, Any]) -> Optional[int]:
    try:
        return int(event.get("status"))
    except Exception:
        return None


def _success(event: Dict[str, Any]) -> bool:
    status = _status(event)
    return status is not None and 200 <= status < 300


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _id(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        value = value.get("id")
    if value is None or isinstance(value, bool):
        return None
    return str(value)


def _detail_id(path: str, prefix: str) -> Optional[str]:
    base = prefix.rstrip("/") + "/"
    if not path.startswith(base):
        return None
    rest = path[len(base) :]
    return rest if rest and "/" not in rest else None


def _loan_detail(path: str) -> Tuple[Optional[str], Optional[str]]:
    base = "/loans/"
    if not path.startswith(base):
        return None, None
    parts = path[len(base) :].split("/")
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else (None, None)


def _brief(event: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "event_index": index,
        "method": _method(event),
        "path": _path(event),
        "status": _status(event),
        "request_body": _dict(event.get("body")),
        "response_body": _dict(event.get("response")),
    }


def evaluate_sequence(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluate exactly one tool-generated sequence from an initially empty SUT."""
    sequence = list(events)
    users: set[str] = set()
    books: set[str] = set()
    # hold id -> owner/book/create witness
    holds: Dict[str, Dict[str, Any]] = {}
    # user -> book -> create witness
    active_loans: Dict[str, Dict[str, Dict[str, Any]]] = {}
    witnesses: Dict[str, Dict[str, Any]] = {}

    for index, event in enumerate(sequence, 1):
        if not _success(event):
            continue
        method, path = _method(event), _path(event)
        request, response = _dict(event.get("body")), _dict(event.get("response"))

        if method == "POST" and path == "/users":
            uid = _id(response.get("id")) or _id(request.get("id"))
            if uid:
                users.add(uid)
            continue

        if method == "DELETE" and path.startswith("/users/"):
            uid = _detail_id(path, "/users")
            if uid:
                users.discard(uid)
                active_loans.pop(uid, None)
                holds = {hid: h for hid, h in holds.items() if h["user"] != uid}
            continue

        if method == "POST" and path == "/books":
            bid = _id(response.get("id")) or _id(request.get("id"))
            if bid:
                books.add(bid)
            continue

        if method == "DELETE" and path.startswith("/books/"):
            bid = _detail_id(path, "/books")
            if bid:
                books.discard(bid)
                holds = {hid: h for hid, h in holds.items() if h["book"] != bid}
                for loans in active_loans.values():
                    loans.pop(bid, None)
            continue

        if method == "POST" and path == "/holds":
            hid = _id(response.get("id")) or _id(request.get("id"))
            uid = _id(response.get("userId")) or _id(request.get("userId"))
            bid = _id(response.get("bookId")) or _id(request.get("bookId"))
            # Same-sequence binding is part of the legal prefix.
            if hid and uid in users and bid in books:
                holds[hid] = {
                    "user": uid,
                    "book": bid,
                    "create": _brief(event, index),
                }
            continue

        if method == "DELETE" and path.startswith("/holds/"):
            hid = _detail_id(path, "/holds")
            if hid:
                holds.pop(hid, None)
            continue

        if method == "POST" and path == "/loans":
            uid = _id(response.get("userId")) or _id(request.get("userId"))
            bid = _id(response.get("bookId")) or _id(request.get("bookId"))
            if uid not in users or bid not in books:
                # A success that relies on campaign-preexisting state is not a
                # self-contained sequence-local witness.
                continue

            if "HOLD_OWNERSHIP" not in witnesses:
                foreign = next(
                    (
                        (hid, hold)
                        for hid, hold in holds.items()
                        if hold["book"] == bid and hold["user"] != uid
                    ),
                    None,
                )
                if foreign:
                    hid, hold = foreign
                    witnesses["HOLD_OWNERSHIP"] = {
                        "book_id": bid,
                        "hold_id": hid,
                        "hold_owner_user_id": hold["user"],
                        "borrowing_user_id": uid,
                        "hold_create": hold["create"],
                        "violating_loan": _brief(event, index),
                        "sequence_steps_to_witness": index,
                    }

            loans = active_loans.setdefault(uid, {})
            loans.setdefault(bid, _brief(event, index))
            if "LOAN_LIMIT" not in witnesses and len(loans) >= 3:
                ordered = sorted(loans.items(), key=lambda pair: pair[1]["event_index"])
                witnesses["LOAN_LIMIT"] = {
                    "user_id": uid,
                    "distinct_active_book_ids": [book for book, _ in ordered],
                    "successful_loan_events": [details for _, details in ordered],
                    "third_active_loan": _brief(event, index),
                    "sequence_steps_to_witness": index,
                }
            continue

        if method == "DELETE" and path.startswith("/loans/"):
            uid, bid = _loan_detail(path)
            if uid and bid:
                active_loans.get(uid, {}).pop(bid, None)

    confirmed = [name for name in CLASSES if name in witnesses]
    return {
        "confirmed_classes": confirmed,
        "semantic_class_count": len(confirmed),
        "semantic_score": f"{len(confirmed)}/2",
        "event_count": len(sequence),
        "witnesses": witnesses,
    }


def _load_sequence_dir(path: Path) -> Tuple[List[Tuple[str, List[Dict[str, Any]]]], Dict[str, Any]]:
    manifest_path = path / "sequence_manifest.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    names = [
        item.get("file")
        for item in manifest.get("sequences", [])
        if isinstance(item, dict) and item.get("file")
    ]
    files = [path / name for name in names if (path / name).is_file()]
    if not names:
        files = sorted(path.glob("sequence_*.jsonl"))
    return [(file.name, load_events(file)) for file in files], manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", nargs="?", help="Compatibility: one self-contained sequence")
    parser.add_argument("--sequence-dir")
    parser.add_argument("--campaign-trace")
    parser.add_argument("--tool", default="unknown")
    parser.add_argument("--output")
    args = parser.parse_args()

    manifest: Dict[str, Any] = {}
    sequences: List[Tuple[str, List[Dict[str, Any]]]] = []
    if args.sequence_dir:
        sequences, manifest = _load_sequence_dir(Path(args.sequence_dir))
    elif args.trace:
        path = Path(args.trace)
        sequences = [(path.name, load_events(path))]
        manifest = {"official_evaluation_complete": True, "source": "single_trace_argument"}

    per_sequence = []
    official_witnesses = {name: [] for name in CLASSES}
    for name, events in sequences:
        result = evaluate_sequence(events)
        per_sequence.append({"sequence": name, **result})
        for class_name in result["confirmed_classes"]:
            official_witnesses[class_name].append(
                {"sequence": name, **result["witnesses"][class_name]}
            )

    official_classes = [name for name in CLASSES if official_witnesses[name]]
    complete = bool(manifest.get("official_evaluation_complete", bool(args.trace)))
    status = "complete" if complete else str(manifest.get("official_status") or "undetermined")

    campaign = None
    if args.campaign_trace:
        campaign_path = Path(args.campaign_trace)
        if campaign_path.exists():
            campaign = evaluate_sequence(load_events(campaign_path))
            campaign["diagnostic_only"] = True
            campaign["warning"] = (
                "Flat campaign evaluation may stitch events across tests and is never used for official scoring."
            )

    official_score = f"{len(official_classes)}/2" if complete else None
    output = {
        "schema_version": 1,
        "artifact_version": "v38",
        "system": "library",
        "tool": args.tool,
        "oracle": "external_http_evidence_sequence_local_fresh_sut",
        "official_status": status,
        "official_evaluation_complete": complete,
        "sequence_confirmed_semantic_classes": official_classes,
        "sequence_confirmed_semantic_class_count": len(official_classes),
        "sequence_confirmed_score": official_score,
        "sequence_confirmed_lower_bound": f"{len(official_classes)}/2",
        "sequence_witnesses": official_witnesses,
        "evaluated_sequence_count": len(per_sequence),
        "per_sequence": per_sequence,
        "campaign_reachability_classes": campaign["confirmed_classes"] if campaign else [],
        "campaign_reachability_class_count": campaign["semantic_class_count"] if campaign else 0,
        "campaign_global_diagnostic": campaign,
        "native_tool_faults_used_for_official_score": False,
        "sequence_manifest_summary": {
            key: manifest.get(key)
            for key in (
                "tool",
                "boundary_source",
                "boundary_verified",
                "candidate_sequence_count",
                "replayed_sequence_count",
                "replay_error_count",
                "official_status",
            )
            if key in manifest
        },
        "note": (
            "Official scoring never stitches across tool-generated tests. Campaign-global reachability is diagnostic only. "
            "A null sequence_confirmed_score means the retained evidence cannot determine an exact official score."
        ),
    }
    text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
