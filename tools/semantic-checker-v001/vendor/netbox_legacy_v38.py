#!/usr/bin/env python3
"""External semantic evaluator for the *attached* NetBox buggy benchmark.

Ground truth is intentionally derived from
resources/development_kit/validation_only/suts/netbox/netbox_benchmark.py.
That source contains exactly two injected fault mechanisms in NB-DELETE-01
    DELETE of an existing item records a tombstone but returns 404 and leaves
    the item in ``db``.  Confirmation requires a created item, the faulty
    delete response, and a later successful GET of the same item.

NB-CIRCUIT-STATUS-02
    PUT/PATCH of ``status`` for api/circuits/circuits silently drops the
    requested status.  Confirmation requires a 2xx update whose returned
    status differs from the requested value (or is absent).

Generic 404/500 responses do not count.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _event_from_line(line: str) -> Optional[Dict[str, Any]]:
    text = line.strip()
    if not text:
        return None
    marker = "MODEL_EVENT "
    if marker in text:
        text = text.split(marker, 1)[1].strip()
    try:
        value = json.loads(text)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def load_events(path: Path) -> List[Dict[str, Any]]:
    return [e for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if (e := _event_from_line(line)) is not None]


def _response_id(event: Dict[str, Any]) -> Optional[str]:
    response = event.get("response")
    if isinstance(response, dict) and response.get("id") is not None:
        return str(response["id"])
    return None


def _norm(path: Any) -> str:
    return "/" + str(path or "").strip("/")


def evaluate(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    evs = list(events)
    created: Dict[Tuple[str, str], int] = {}
    faulty_deletes: Dict[Tuple[str, str], int] = {}
    delete_confirmations: List[Dict[str, Any]] = []
    circuit_confirmations: List[Dict[str, Any]] = []

    for idx, e in enumerate(evs):
        method = str(e.get("method", "")).upper()
        path = _norm(e.get("path"))
        try:
            status = int(e.get("status"))
        except Exception:
            continue
        response = e.get("response")
        body = e.get("body")

        if method == "POST" and 200 <= status < 300:
            rid = _response_id(e)
            if rid:
                created[(path.rstrip("/"), rid)] = idx
            continue

        # Source-derived fault 1: only the exact faulty branch response is a
        # candidate; a generic 404 is never sufficient.
        if method == "DELETE" and status == 404 and isinstance(response, dict) \
                and response.get("detail") == "Deletion recorded.":
            bits = path.rstrip("/").rsplit("/", 1)
            if len(bits) == 2:
                collection, rid = bits
                key = (collection, rid)
                if key in created and created[key] < idx:
                    faulty_deletes[key] = idx
            continue

        if method == "GET" and 200 <= status < 300:
            bits = path.rstrip("/").rsplit("/", 1)
            if len(bits) == 2:
                key = (bits[0], bits[1])
                if key in faulty_deletes and faulty_deletes[key] < idx:
                    delete_confirmations.append({
                        "collection": key[0], "id": key[1],
                        "create_event": created.get(key),
                        "delete_event": faulty_deletes[key], "get_event": idx,
                    })

        # Source-derived fault 2: the SUT only discards status on this exact
        # collection.  A successful response that does not reflect the requested
        # status confirms the lost update immediately.
        if method in {"PUT", "PATCH"} and path.startswith("/api/circuits/circuits/") \
                and 200 <= status < 300 and isinstance(body, dict) and "status" in body:
            wanted = body.get("status")
            got = response.get("status") if isinstance(response, dict) else None
            if got != wanted:
                circuit_confirmations.append({
                    "path": path, "event": idx,
                    "requested_status": wanted, "returned_status": got,
                })

    delete_ok = bool(delete_confirmations)
    circuit_ok = bool(circuit_confirmations)
    return {
        "schema_version": 2,
        "rule_basis": "External evaluation of preserved HTTP trace against the two fault mechanisms present in netbox_benchmark.py",
        "fault_inventory_count": 2,
        "faults": {
            "NB-DELETE-01": {
                "confirmed": delete_ok,
                "class": "lifecycle deletion not applied",
                "evidence": delete_confirmations,
            },
            "NB-CIRCUIT-STATUS-02": {
                "confirmed": circuit_ok,
                "class": "circuit status update silently lost",
                "evidence": circuit_confirmations,
            },
        },
        "delete_recorded_but_item_survives_confirmed": delete_ok,
        "circuit_status_update_lost_confirmed": circuit_ok,
        "confirmed_fault_count": int(delete_ok) + int(circuit_ok),
        "expected_seeded_fault_count": 2,
        "all_seeded_faults_confirmed": delete_ok and circuit_ok,
        "event_count": len(evs),
        "note": "Provengo FAIL, generic HTTP errors, or a bare 404 are not counted without the class-specific semantic precondition and outcome.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    args = ap.parse_args()
    result = evaluate(load_events(Path(args.trace)))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
