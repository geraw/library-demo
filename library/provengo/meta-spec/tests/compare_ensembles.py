"""
Independent coverage-measurement script, used to compare the GOALS-selected ensemble against the
state+param-selected ensemble on the SAME samples.json - deliberately reimplemented here rather
than reusing goalsRankingFunction/stateParamRankingFunction, so the comparison isn't circular
(each method shouldn't just "win" on its own internal metric).

State-feature coverage is measured via verify_state_features.py's replay_trace() (the reliable,
cross-validated-against-JS reconstruction from the raw event stream - see
compare_state_reconstruction.js, 10/10 exact per-trace match, 2026-10-15), NOT via the StateFeature
marker events, which were found to miss 45-78% of genuinely-true occurrences.
"""
import json
import re
import sys

from verify_state_features import replay_trace

STATE_FEATURES = ["BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE",
                   "HOLD_CREATABLE", "HOLD_WITHOUT_LOAN", "MULTI_USER_BOOK_RELATIONS"]

GOAL_PATTERNS = [
    ("loan create completion (valid)", "loan_completion", re.compile(r"^Create: Loan")),
    ("loan create completion (invalid)", "loan_completion_invalid", re.compile(r"^createLoan \(invalid")),
    ("createHold (valid)", "name", re.compile(r"createHold \(valid")),
    ("createHold (invalid)", "name", re.compile(r"createHold \(invalid")),
    ("deleteUser (valid)", "name", re.compile(r"deleteUser \(valid")),
    ("deleteUser (invalid)", "name", re.compile(r"deleteUser \(invalid")),
    ("deleteBook (valid)", "name", re.compile(r"deleteBook \(valid")),
    ("deleteBook (invalid)", "name", re.compile(r"deleteBook \(invalid")),
]


def get_data(ev):
    return ev.get("data", ev) if isinstance(ev, dict) else {}


def event_display_name(ev, d):
    if d.get("model") and d["model"].get("name"):
        return d["model"]["name"]
    return ev.get("name")


def measure(path):
    with open(path, "r", encoding="utf-8") as f:
        tests = json.load(f)

    state_hit = set()
    param_hit = set()
    goals_hit = set()
    trace_signatures = []

    for test in tests:
        sig = tuple((ev.get("name"), json.dumps(get_data(ev), sort_keys=True)) for ev in test)
        trace_signatures.append(sig)

        observed, _marker = replay_trace(test)
        for feat, was_true in observed.items():
            if was_true:
                state_hit.add(feat)

        for ev in test:
            d = get_data(ev)
            name = event_display_name(ev, d)
            for label, kind, pattern in GOAL_PATTERNS:
                if kind == "name" and name and pattern.search(name):
                    goals_hit.add(label)
                elif kind in ("loan_completion", "loan_completion_invalid"):
                    if d.get("method") == "POST" and "/loans" in (d.get("url") or ""):
                        desc = (d.get("parameters") or {}).get("description")
                        if desc and pattern.search(desc):
                            goals_hit.add(label)
                        elif name and kind == "loan_completion_invalid" and pattern.search(name):
                            goals_hit.add(label)

            if d.get("lib") == "REST" and d.get("method") == "POST":
                url = d.get("url") or ""
                op = "loan" if "/loans" in url else ("hold" if "/holds" in url else None)
                p = d.get("parameters") or {}
                desc = p.get("description")
                if op and desc and desc.startswith("Create: ") and p.get("userId") is not None and p.get("bookId") is not None:
                    uid, bid = p["userId"], p["bookId"]
                    param_hit.add("user:" + str(uid))
                    param_hit.add("book:" + str(bid))
                    param_hit.add("op:" + op)
                    param_hit.add("pair:" + str(uid) + "/" + str(bid))

    duplicate_count = len(trace_signatures) - len(set(trace_signatures))

    return {
        "num_traces": len(tests),
        "state_features_covered": sorted(state_hit),
        "state_features_count": len(state_hit),
        "goals_covered": sorted(goals_hit),
        "goals_count": len(goals_hit),
        "param_tags_count": len(param_hit),
        "param_tags": sorted(param_hit),
        "duplicate_traces": duplicate_count,
    }


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print("=== " + path + " ===")
        result = measure(path)
        for k, v in result.items():
            if k in ("param_tags",):
                continue
            print(" ", k, "=", v)
        print()
