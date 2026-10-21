#!/usr/bin/env python3
"""V35 NetBox semantic evaluator.

Official scoring remains sequence-local and uses external HTTP evidence only.
Hidden SUT activation markers are diagnostic ground truth: they validate the
oracle and distinguish reachability from externally observable confirmation,
but they never contribute to the official score and are not visible to tools.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CLASSES = [
    "A_LOGIC",
    "B_LIFECYCLE",
    "C_UNIQUENESS",
    "D_INTEGRITY",
    "E_REFERENTIAL_INTEGRITY",
]
MIN_HTTP_STEPS = {
    "A_LOGIC": 5,
    "B_LIFECYCLE": 5,
    "C_UNIQUENESS": 2,
    "D_INTEGRITY": 4,
    "E_REFERENTIAL_INTEGRITY": 4,
}


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
        e
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if (e := _event_from_line(line)) is not None
    ]


def load_ground_truth(path: Path | None) -> List[Dict[str, Any]]:
    if path is None or not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("kind") == "fault_ground_truth" and item.get("class") in CLASSES:
            out.append(item)
    return out


def summarize_ground_truth(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    evs = list(events)
    by_class = {c: [] for c in CLASSES}
    for e in evs:
        cls = e.get("class")
        if cls in by_class:
            by_class[cls].append(e)
    triggered = [c for c in CLASSES if by_class[c]]
    return {
        "triggered_classes": triggered,
        "triggered_class_count": len(triggered),
        "triggered_score": f"{len(triggered)}/5",
        "marker_count": len(evs),
        "markers_by_class": by_class,
    }


def _path(e):
    return "/" + str(e.get("path") or "").split("?", 1)[0].strip("/")


def _status(e):
    try:
        return int(e.get("status"))
    except Exception:
        return None


def _body(e):
    return e.get("body") if isinstance(e.get("body"), dict) else {}


def _response(e):
    return e.get("response") if isinstance(e.get("response"), dict) else {}


def _rid(v):
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("id")
    return None if v is None else str(v)


def _is_2xx(e):
    s = _status(e)
    return s is not None and 200 <= s < 300


def _id_from_detail(path: str, prefix: str):
    p = path.rstrip("/")
    base = prefix.rstrip("/") + "/"
    if not p.startswith(base):
        return None
    rest = p[len(base):]
    return rest if rest and "/" not in rest else None


def _confirm_a(evs):
    sites = set()
    devices = {}
    for i, e in enumerate(evs):
        m = str(e.get("method") or "").upper()
        p = _path(e).rstrip("/") or "/"
        req, resp = _body(e), _response(e)
        if m == "POST" and p == "/api/dcim/sites" and _is_2xx(e):
            sid = _rid(resp.get("id")) or _rid(req.get("id"))
            if sid:
                sites.add(sid)
        elif m == "POST" and p == "/api/dcim/devices" and _is_2xx(e):
            did = _rid(resp.get("id")) or _rid(req.get("id"))
            sid = _rid(resp.get("site")) or _rid(req.get("site"))
            if did and sid in sites:
                devices[did] = {"parent": sid, "pending": None}
        elif m == "PATCH" and p.startswith("/api/dcim/devices/") and _is_2xx(e):
            did = _id_from_detail(p, "/api/dcim/devices")
            d = devices.get(did)
            requested = _rid(req.get("site")) if "site" in req else None
            if d and requested and requested in sites and requested != d["parent"]:
                d["pending"] = {
                    "old_parent": d["parent"],
                    "requested_parent": requested,
                    "patch_event": i,
                }
                # Do not confirm from the PATCH body.  The V35 official witness
                # requires a subsequent external retrieval.
        elif m == "GET" and p.startswith("/api/dcim/devices/") and _is_2xx(e):
            did = _id_from_detail(p, "/api/dcim/devices")
            d = devices.get(did)
            got = _rid(resp.get("site"))
            if not d or got is None:
                continue
            pending = d.get("pending")
            if pending and i > pending["patch_event"]:
                if got == pending["old_parent"] and got != pending["requested_parent"] and i + 1 >= MIN_HTTP_STEPS["A_LOGIC"]:
                    return {
                        "device_id": did,
                        "old_parent": pending["old_parent"],
                        "requested_parent": pending["requested_parent"],
                        "patch_event": pending["patch_event"],
                        "verify_event": i,
                        "sequence_steps_to_witness": i + 1,
                    }
                if got == pending["requested_parent"]:
                    d["parent"] = got
                    d["pending"] = None
    return None


def _confirm_b(evs):
    sites = set()
    children = {}
    deleted = {}
    for i, e in enumerate(evs):
        m = str(e.get("method") or "").upper()
        p = _path(e).rstrip("/") or "/"
        req, resp = _body(e), _response(e)
        if m == "POST" and p == "/api/dcim/sites" and _is_2xx(e):
            sid = _rid(resp.get("id")) or _rid(req.get("id"))
            if sid:
                sites.add(sid)
        elif m == "POST" and p == "/api/dcim/devices" and _is_2xx(e):
            did = _rid(resp.get("id")) or _rid(req.get("id"))
            sid = _rid(resp.get("site")) or _rid(req.get("site"))
            if did and sid in sites:
                children[did] = sid
        elif m == "DELETE" and p.startswith("/api/dcim/sites/") and _is_2xx(e):
            sid = _id_from_detail(p, "/api/dcim/sites")
            child_ids = [d for d, parent in children.items() if parent == sid]
            if sid in sites and len(child_ids) >= 2:
                deleted[sid] = {"event": i, "children": set(child_ids)}
        elif m == "GET" and p.startswith("/api/dcim/devices/") and _is_2xx(e):
            did = _id_from_detail(p, "/api/dcim/devices")
            got_parent = _rid(resp.get("site"))
            for sid, info in deleted.items():
                if did in info["children"] and got_parent == sid and i > info["event"] and i + 1 >= MIN_HTTP_STEPS["B_LIFECYCLE"]:
                    return {
                        "parent_id": sid,
                        "delete_event": info["event"],
                        "surviving_child": did,
                        "verification_event": i,
                        "sequence_steps_to_witness": i + 1,
                    }
    return None


def _confirm_c(evs):
    owner = {}
    for i, e in enumerate(evs):
        if str(e.get("method") or "").upper() != "POST" or _path(e).rstrip("/") != "/api/dcim/sites" or not _is_2xx(e):
            continue
        req, resp = _body(e), _response(e)
        value = resp.get("slug") if resp.get("slug") not in (None, "") else req.get("slug")
        sid = _rid(resp.get("id")) or _rid(req.get("id"))
        if value in (None, "") or not sid:
            continue
        value = str(value)
        if value in owner and owner[value][0] != sid and i + 1 >= MIN_HTTP_STEPS["C_UNIQUENESS"]:
            return {
                "value": value,
                "first_id": owner[value][0],
                "second_id": sid,
                "first_create_event": owner[value][1],
                "second_create_event": i,
                "sequence_steps_to_witness": i + 1,
            }
        owner[value] = (sid, i)
    return None


def _confirm_d(evs):
    items = {}
    for i, e in enumerate(evs):
        m = str(e.get("method") or "").upper()
        p = _path(e).rstrip("/") or "/"
        if not _is_2xx(e):
            continue
        req, resp = _body(e), _response(e)
        if m == "POST" and p == "/api/circuits/circuits":
            cid = _rid(resp.get("id")) or _rid(req.get("id"))
            if cid:
                items[cid] = {
                    "initial": resp.get("description", req.get("description")),
                    "first_target": None,
                    "first_patch": None,
                    "first_verified": None,
                    "second_target": None,
                    "second_patch": None,
                }
        elif m == "PATCH" and p.startswith("/api/circuits/circuits/"):
            cid = _id_from_detail(p, "/api/circuits/circuits")
            d = items.get(cid)
            if not d or "description" not in req:
                continue
            requested = req.get("description")
            got = resp.get("description")
            if d["first_target"] is None:
                if requested == d["initial"]:
                    continue
                d["first_target"] = requested
                d["first_patch"] = i
            elif d["first_verified"] is not None and requested not in {d["initial"], d["first_target"]}:
                d["second_target"] = requested
                d["second_patch"] = i
                if got == d["first_target"] and got != requested and i + 1 >= MIN_HTTP_STEPS["D_INTEGRITY"]:
                    return {
                        "item_id": cid,
                        "initial_value": d["initial"],
                        "first_requested_value": d["first_target"],
                        "second_requested_value": requested,
                        "first_patch_event": d["first_patch"],
                        "first_verify_event": d["first_verified"],
                        "second_patch_event": i,
                        "witness_source": "stale_successful_patch_response",
                        "sequence_steps_to_witness": i + 1,
                    }
        elif m == "GET" and p.startswith("/api/circuits/circuits/"):
            cid = _id_from_detail(p, "/api/circuits/circuits")
            d = items.get(cid)
            if not d:
                continue
            got = resp.get("description")
            if d["first_target"] is not None and d["first_verified"] is None and i > d["first_patch"] and got == d["first_target"]:
                d["first_verified"] = i
            elif d.get("second_target") is not None and i > d["second_patch"]:
                if got == d["first_target"] and got != d["second_target"] and i + 1 >= MIN_HTTP_STEPS["D_INTEGRITY"]:
                    return {
                        "item_id": cid,
                        "initial_value": d["initial"],
                        "first_requested_value": d["first_target"],
                        "second_requested_value": d["second_target"],
                        "first_patch_event": d["first_patch"],
                        "first_verify_event": d["first_verified"],
                        "second_patch_event": d["second_patch"],
                        "second_verify_event": i,
                        "witness_source": "subsequent_get",
                        "sequence_steps_to_witness": i + 1,
                    }
    return None


def _confirm_e(evs):
    sites = set()
    valid_children = {}
    deleted = {}
    for i, e in enumerate(evs):
        m = str(e.get("method") or "").upper()
        p = _path(e).rstrip("/") or "/"
        req, resp = _body(e), _response(e)
        if m == "POST" and p == "/api/dcim/sites" and _is_2xx(e):
            sid = _rid(resp.get("id")) or _rid(req.get("id"))
            if sid:
                sites.add(sid)
        elif m == "POST" and p == "/api/dcim/devices" and _is_2xx(e):
            did = _rid(resp.get("id")) or _rid(req.get("id"))
            sid = _rid(resp.get("site")) or _rid(req.get("site"))
            if not did or not sid:
                continue
            if sid in sites and sid not in deleted:
                valid_children.setdefault(sid, []).append((did, i))
            elif sid in deleted and valid_children.get(sid):
                observed_parent = _rid(resp.get("site")) or sid
                if observed_parent == sid and i + 1 >= MIN_HTTP_STEPS["E_REFERENTIAL_INTEGRITY"]:
                    return {
                        "reused_child_id": did,
                        "deleted_parent_id": sid,
                        "delete_event": deleted[sid],
                        "reuse_create_event": i,
                        "witness_source": "successful_create_response",
                        "sequence_steps_to_witness": i + 1,
                    }
        elif m == "DELETE" and p.startswith("/api/dcim/sites/") and _is_2xx(e):
            sid = _id_from_detail(p, "/api/dcim/sites")
            if sid in sites and valid_children.get(sid):
                deleted[sid] = i
    return None


FINDERS = {
    "A_LOGIC": _confirm_a,
    "B_LIFECYCLE": _confirm_b,
    "C_UNIQUENESS": _confirm_c,
    "D_INTEGRITY": _confirm_d,
    "E_REFERENTIAL_INTEGRITY": _confirm_e,
}


def evaluate_sequence(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    evs = list(events)
    witnesses = {}
    for cls in CLASSES:
        w = FINDERS[cls](evs)
        if w:
            witnesses[cls] = w
    confirmed = [c for c in CLASSES if c in witnesses]
    return {
        "confirmed_classes": confirmed,
        "semantic_class_count": len(confirmed),
        "score": f"{len(confirmed)}/5",
        "event_count": len(evs),
        "witnesses": witnesses,
    }


def evaluate(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    return evaluate_sequence(events)


def load_sequence_dir(path: Path):
    sequences = []
    if not path.exists():
        return sequences
    manifest = path / "sequence_manifest.json"
    if manifest.exists():
        try:
            m = json.loads(manifest.read_text(encoding="utf-8-sig"))
            names = [x.get("file") for x in m.get("sequences", []) if x.get("file")]
        except Exception:
            names = []
    else:
        names = []
    files = [path / n for n in names if (path / n).is_file()] if names else sorted(path.glob("*.jsonl"))
    for p in files:
        sequences.append((p.name, load_events(p)))
    return sequences


def parse_native(tool: str, native_log: Path | None, run_dir: Path | None):
    t = tool.lower()
    result = {"tool": tool, "count": None, "source": None}
    text = ""
    if native_log and native_log.exists():
        text = native_log.read_text(encoding="utf-8", errors="replace")
        result["source"] = str(native_log)
    if t == "evomaster":
        for pat in [r"Potential\s+faults\s*[:=]\s*(\d+)", r"potentialFaults\s*[:=]\s*(\d+)"]:
            hits = re.findall(pat, text, flags=re.I)
            if hits:
                result["count"] = int(hits[-1])
                result["metric"] = "potential_faults"
                return result
    if t == "restler" and run_dir and run_dir.exists():
        buckets = [p for p in run_dir.rglob("*") if p.is_file() and "bug_buckets" in str(p.parent).lower()]
        if buckets:
            result["count"] = len(buckets)
            result["metric"] = "bug_bucket_files"
            result["source"] = "RESTler bug_buckets files"
            return result
    if t == "provengo" and text:
        fails = len(re.findall(r"\bFAIL(?:ED)?\b", text, flags=re.I))
        result["count"] = fails
        result["metric"] = "native_fail_log_mentions"
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", nargs="?", help="Compatibility: one sequence trace")
    ap.add_argument("--sequence-dir")
    ap.add_argument("--campaign-trace")
    ap.add_argument("--ground-truth-log")
    ap.add_argument("--tool", default="unknown")
    ap.add_argument("--native-log")
    ap.add_argument("--run-dir")
    ap.add_argument("--output")
    a = ap.parse_args()

    per_sequence = []
    if a.sequence_dir:
        for name, events in load_sequence_dir(Path(a.sequence_dir)):
            per_sequence.append({"sequence": name, **evaluate_sequence(events)})
    elif a.trace:
        per_sequence.append({"sequence": Path(a.trace).name, **evaluate_sequence(load_events(Path(a.trace)))})

    official_witnesses = {c: [] for c in CLASSES}
    for r in per_sequence:
        for c in r["confirmed_classes"]:
            official_witnesses[c].append({"sequence": r["sequence"], **r["witnesses"][c]})
    official_classes = [c for c in CLASSES if official_witnesses[c]]

    campaign = None
    if a.campaign_trace:
        campaign = evaluate_sequence(load_events(Path(a.campaign_trace)))
        campaign["diagnostic_only"] = True
        campaign["warning"] = "Flat campaign evaluation may stitch events across tests and is never used for the official score."

    gt = summarize_ground_truth(load_ground_truth(Path(a.ground_truth_log) if a.ground_truth_log else None))
    campaign_classes = campaign["confirmed_classes"] if campaign else []
    campaign_false_positive = [c for c in campaign_classes if c not in gt["triggered_classes"]]
    triggered_not_observed = [c for c in gt["triggered_classes"] if c not in campaign_classes]
    gt_consistency = {
        "campaign_confirmed_without_hidden_activation": campaign_false_positive,
        "hidden_activation_without_campaign_http_witness": triggered_not_observed,
        "campaign_evaluator_subset_of_hidden_ground_truth": len(campaign_false_positive) == 0,
        "interpretation": (
            "Hidden activation is diagnostic only. Triggered-but-not-observed means the SUT fault branch was reached "
            "without an external HTTP witness satisfying the official evaluator; confirmed-without-trigger is a validator defect signal."
        ),
    }

    native = parse_native(
        a.tool,
        Path(a.native_log) if a.native_log else None,
        Path(a.run_dir) if a.run_dir else None,
    )
    out = {
        "schema_version": 5,
        "artifact_version": "v36",
        "oracle": "external_http_evidence_sequence_local",
        "minimum_http_steps": MIN_HTTP_STEPS,
        "native_tool_faults": native,
        "sequence_confirmed_semantic_classes": official_classes,
        "sequence_confirmed_semantic_class_count": len(official_classes),
        "sequence_confirmed_score": f"{len(official_classes)}/5",
        "all_A_to_E_sequence_confirmed": len(official_classes) == 5,
        "sequence_witnesses": official_witnesses,
        "evaluated_sequence_count": len(per_sequence),
        "per_sequence": per_sequence,
        "campaign_reachability_classes": campaign_classes,
        "campaign_reachability_class_count": campaign["semantic_class_count"] if campaign else 0,
        "campaign_global_diagnostic": campaign,
        "hidden_ground_truth": gt,
        "ground_truth_consistency": gt_consistency,
        "ground_truth_used_for_official_score": False,
        "ground_truth_exposed_to_tool": False,
        "note": (
            "V35 official semantic scoring never stitches across tool-generated sequences and never uses hidden SUT markers. "
            "Campaign-global reachability and hidden activation are diagnostics; native tool faults are reported separately."
        ),
    }
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
