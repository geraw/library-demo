import argparse
import csv
import io
import json
import re
import zipfile
from collections import Counter
from urllib.parse import urlparse

FIELDS = {
    "users": ("name",),
    "books": ("title",),
    "loans": ("userId", "bookId"),
    "holds": ("userId", "bookId"),
}
ID_RE = re.compile(r"^/(users|books|loans|holds)(?:/(.*))?$")


def parse_csv(zf, name):
    rows = []
    with zf.open(name) as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig")
        rows.extend(csv.DictReader(text))
    return rows


def discover_cells(zf):
    cells = []
    for name in zf.namelist():
        normalized = name.replace("\\", "/")
        if not normalized.endswith("/http.jsonl") or normalized.startswith("smoke/") or "/smoke/" in normalized:
            continue
        parts = name.replace("\\", "/").split("/")
        tool_index = next((i for i, p in enumerate(parts) if p in ("evomaster", "restler")), None)
        if tool_index is None or tool_index + 1 >= len(parts):
            continue
        tool, arm = parts[tool_index], parts[tool_index + 1]
        if arm not in ("baseline", *[f"B{i}" for i in range(1, 7)], *[f"F{i}" for i in range(1, 7)], *[f"C{i}" for i in range(1, 4)]):
            continue
        run = "/".join(parts[:tool_index])
        cells.append({"run": run, "tool": tool, "arm": arm, "trace": name})
    return cells


def audit_trace(zf, name):
    state = {entity: {} for entity in FIELDS}
    anomalies = Counter()
    examples = []
    tool_requests = 0
    with zf.open(name) as raw:
        for line in raw:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("role") == "boundary":
                state = {entity: {} for entity in FIELDS}
                continue
            if event.get("role") != "tool":
                continue
            tool_requests += 1
            method = event.get("method", "")
            parsed = urlparse(event.get("url", ""))
            match = ID_RE.match(parsed.path)
            if not match:
                continue
            entity, suffix = match.groups()
            fields = FIELDS[entity]
            status = event.get("status")
            req = event.get("input") or {}
            response = event.get("response")

            if method == "POST" and status == 201 and isinstance(response, dict) and "id" in response:
                row = {"id": response["id"]}
                for field in fields:
                    if field in req:
                        row[field] = req[field]
                state[entity][str(response["id"])] = row
                response_mismatch = any(response.get(k) != req.get(k) for k in fields if k in req)
                if response_mismatch:
                    anomalies["post_echo_mismatch"] += 1
                    if len(examples) < 12:
                        examples.append({"order": event.get("order"), "kind": "post_echo_mismatch", "method": method, "path": parsed.path, "input": req, "response": response})
                continue

            if method == "DELETE" and status in (200, 204) and suffix:
                bits = suffix.split("/")
                if entity in ("users", "books", "holds") and len(bits) == 1:
                    state[entity].pop(str(bits[0]), None)
                elif entity == "loans" and len(bits) == 2:
                    state[entity] = {k: row for k, row in state[entity].items()
                                     if not (str(row.get("userId")) == bits[0] and str(row.get("bookId")) == bits[1])}
                continue

            if method != "GET" or status != 200:
                continue
            if suffix is None:
                if parsed.query:
                    continue
                if not isinstance(response, list):
                    continue
                expected = list(state[entity].values())
                def norm(rows):
                    return sorted((str(row.get("id")), tuple(str(row.get(f)) for f in fields)) for row in rows if isinstance(row, dict))
                if norm(expected) != norm(response):
                    anomalies["get_collection_mismatch"] += 1
                    if len(examples) < 12:
                        examples.append({"order": event.get("order"), "kind": "get_collection_mismatch", "method": method, "path": parsed.path, "expected_count": len(expected), "actual_count": len(response), "expected_ids": [r.get("id") for r in expected[:8]], "actual_ids": [r.get("id") for r in response[:8]]})
            else:
                expected = state[entity].get(str(suffix))
                if expected is None or not isinstance(response, dict):
                    continue
                if any(str(response.get(f)) != str(expected.get(f)) for f in fields):
                    anomalies["get_by_id_mismatch"] += 1
                    if len(examples) < 12:
                        examples.append({"order": event.get("order"), "kind": "get_by_id_mismatch", "method": method, "path": parsed.path, "expected": expected, "actual": response})
    return {"tool_requests": tool_requests, "anomalies": dict(anomalies), "examples": examples}


def audit_archive(path):
    with zipfile.ZipFile(path) as zf:
        cells = discover_cells(zf)
        results = []
        for cell in sorted(cells, key=lambda x: (x["run"], x["tool"], x["arm"])):
            result = audit_trace(zf, cell["trace"])
            results.append({**cell, **result})
        return {"archive": path, "cells": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", help="Evidence ZIP archives to audit")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = {"method": "Input-projected CRUD replay against unfiltered collection reads, by-ID reads, and POST response echoes; this is an offline consistency oracle, not native tool attribution.",
              "archives": [audit_archive(p) for p in args.archives]}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(args.output)


if __name__ == "__main__":
    main()
