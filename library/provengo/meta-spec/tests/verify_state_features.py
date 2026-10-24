"""
Independent reconstruction of the 6 state features directly from the raw REST create/delete
event stream, to check whether each one is reliably reconstructable at all (per-feature, not
assumed for all six), and to measure how often the in-model StateFeature marker actually fired
vs how often the condition it's supposed to report was independently true/false - quantifying
both the miss rate (true but unmarked) and the false-positive rate (marked but not true) of the
bp.sync offer/eventPriority marker mechanism.

Mirrors dal.js's own query definitions (Book.CanDelete, User.CanDelete, UserBook.CanCreateLoan,
Hold.WithoutLoan) plus the two relation-based features computed directly in lib_stories.js
(MULTI_USER_BOOK_RELATIONS, USER_WITH_TWO_BOOKS), rather than inventing new semantics. Only
trusts "Create: "/"Delete: " prefixed descriptions as genuine completions (same convention used
elsewhere in this investigation - see ensemble-code.js's loanOrHoldCreateParameters comment).

HOLD_CREATABLE deliberately excluded (2026-10-24): UserBook.CanCreateHold is unconditionally true
for any existing user-book pair, so it can't discriminate between scenarios - see lib_stories.js.
"""
import json
import os
import sys


FEATURES = [
    "BOOK_DELETE_ELIGIBLE", "USER_DELETE_ELIGIBLE", "LOAN_CREATABLE",
    "HOLD_WITHOUT_LOAN", "MULTI_USER_BOOK_RELATIONS", "USER_WITH_TWO_BOOKS",
]


def get_data(ev):
    return ev.get("data", ev) if isinstance(ev, dict) else {}


def is_genuine(d, verb):
    p = d.get("parameters") or {}
    desc = p.get("description") or ""
    return d.get("lib") == "REST" and d.get("method") == verb and desc.startswith(
        "Create: " if verb == "POST" else "Delete: "
    )


class State:
    def __init__(self):
        self.users = set()
        self.books = set()
        self.active_loans = set()  # (userId, bookId)
        self.active_holds = {}     # holdId -> (userId, bookId)

    def relations(self):
        rels = list(self.active_loans)
        rels += list(self.active_holds.values())
        return rels

    def book_can_delete(self, book):
        return not any(b == book for (u, b) in self.active_loans) and \
               not any(b == book for (u, b) in self.active_holds.values())

    def user_can_delete(self, user):
        return not any(u == user for (u, b) in self.active_loans) and \
               not any(u == user for (u, b) in self.active_holds.values())

    def can_create_loan(self, user, book):
        return not any(u == user for (u, b) in self.active_loans) and \
               not any(b == book for (u, b) in self.active_loans)

    def hold_without_loan(self):
        for (u, b) in self.active_holds.values():
            user_has_loan = any(uu == u for (uu, bb) in self.active_loans)
            book_has_loan = any(bb == b for (uu, bb) in self.active_loans)
            if not user_has_loan and not book_has_loan:
                return True
        return False

    def multi_user_book_relations(self):
        rels = self.relations()
        for i in range(len(rels)):
            for j in range(i + 1, len(rels)):
                if rels[i][0] != rels[j][0] and rels[i][1] != rels[j][1]:
                    return True
        return False

    def user_with_two_books(self):
        rels = self.relations()
        for i in range(len(rels)):
            for j in range(i + 1, len(rels)):
                if rels[i][0] == rels[j][0] and rels[i][1] != rels[j][1]:
                    return True
        return False


def replay_trace(events):
    """Returns (observed, marker_fired) dicts over FEATURES - both "ever true over the whole
    trace" (Set-like semantics matching the Set-based scoring), not point-in-time snapshots."""
    st = State()
    observed = {k: False for k in FEATURES}
    marker_fired = {k: False for k in FEATURES}

    for ev in events:
        d = get_data(ev)
        if not isinstance(d, dict):
            continue

        feat = d.get("feature")
        if ev.get("name") == "StateFeature" and feat in marker_fired:
            marker_fired[feat] = True

        url = d.get("url") or ""
        p = d.get("parameters") or {}

        if is_genuine(d, "POST"):
            if "/users" in url and p.get("id") is not None:
                st.users.add(p["id"])
            elif "/books" in url and p.get("id") is not None:
                st.books.add(p["id"])
            elif "/loans" in url and p.get("userId") is not None and p.get("bookId") is not None:
                st.active_loans.add((p["userId"], p["bookId"]))
            elif "/holds" in url and p.get("userId") is not None and p.get("bookId") is not None:
                st.active_holds[p.get("id")] = (p["userId"], p["bookId"])
        elif is_genuine(d, "DELETE"):
            if "/users" in url and p.get("id") is not None:
                st.users.discard(p["id"])
            elif "/books" in url and p.get("id") is not None:
                st.books.discard(p["id"])
            elif "/loans" in url and p.get("userId") is not None and p.get("bookId") is not None:
                st.active_loans.discard((p["userId"], p["bookId"]))
            elif "/holds" in url and p.get("id") is not None:
                st.active_holds.pop(p["id"], None)

        # Re-check every condition after every event (OR across all time, matching the
        # Set-based "did this feature ever occur" semantics used in scoring).
        if any(st.book_can_delete(b) for b in st.books):
            observed["BOOK_DELETE_ELIGIBLE"] = True
        if any(st.user_can_delete(u) for u in st.users):
            observed["USER_DELETE_ELIGIBLE"] = True
        if any(st.can_create_loan(u, b) for u in st.users for b in st.books):
            observed["LOAN_CREATABLE"] = True
        if st.hold_without_loan():
            observed["HOLD_WITHOUT_LOAN"] = True
        if st.multi_user_book_relations():
            observed["MULTI_USER_BOOK_RELATIONS"] = True
        if st.user_with_two_books():
            observed["USER_WITH_TWO_BOOKS"] = True

    return observed, marker_fired


def main(path, run_id=None, arm=None, event_priority=None, log_path=None):
    with open(path, "r", encoding="utf-8") as f:
        tests = json.load(f)

    # Per-feature counts across all traces.
    true_count = {k: 0 for k in FEATURES}       # ground truth true at some point
    false_count = {k: 0 for k in FEATURES}      # ground truth never true
    marker_count = {k: 0 for k in FEATURES}     # marker fired at some point
    miss_count = {k: 0 for k in FEATURES}       # true but marker never fired (false negative)
    fp_count = {k: 0 for k in FEATURES}         # marker fired but never true (false positive)

    for test in tests:
        observed, marker = replay_trace(test)
        for k in FEATURES:
            if observed[k]:
                true_count[k] += 1
                if not marker[k]:
                    miss_count[k] += 1
            else:
                false_count[k] += 1
                if marker[k]:
                    fp_count[k] += 1
            if marker[k]:
                marker_count[k] += 1

    n = len(tests)
    print(f"{n} traces\n")
    header = f"{'feature':<28}{'true':>8}{'marker':>8}{'miss':>8}{'miss rate':>12}{'false+':>8}{'fp rate':>10}"
    print(header)
    for k in FEATURES:
        miss_rate = (miss_count[k] / true_count[k]) if true_count[k] else float('nan')
        fp_rate = (fp_count[k] / false_count[k]) if false_count[k] else float('nan')
        miss_rate_s = f"{miss_rate:.1%}" if true_count[k] else "n/a (0 true)"
        fp_rate_s = f"{fp_rate:.1%}" if false_count[k] else "n/a (always true)"
        print(f"{k:<28}{true_count[k]:>5}/{n:<2}{marker_count[k]:>5}/{n:<2}{miss_count[k]:>5}/{n:<2}"
              f"{miss_rate_s:>12}{fp_count[k]:>5}/{n:<2}{fp_rate_s:>10}")

    if log_path and run_id:
        # Small, durable per-run record (run id/arm/counts) so conclusions can be audited later
        # without keeping the multi-hundred-MB raw samples.json that produced them.
        import csv
        import datetime
        import os
        write_header = not os.path.exists(log_path)
        with open(log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["run_id", "date", "arm", "event_priority", "n_traces", "feature",
                            "true_count", "marker_count", "miss_count", "fp_count"])
            today = datetime.date.today().isoformat()
            for k in FEATURES:
                w.writerow([run_id, today, arm, event_priority, n, k,
                            true_count[k], marker_count[k], miss_count[k], fp_count[k]])
        print(f"\nappended {len(FEATURES)} rows to {log_path}")


def dump_json(path, out_path):
    """Per-trace 'observed' (independently reconstructed) feature sets, for exact cross-checking
    against ensemble-code.js's reconstructStateFeaturesForTrace via compare_state_reconstruction.js."""
    with open(path, "r", encoding="utf-8") as f:
        tests = json.load(f)
    result = []
    for test in tests:
        observed, _marker = replay_trace(test)
        result.append(sorted([k for k, v in observed.items() if v]))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    print(f"wrote {len(result)} traces' worth of per-trace feature sets to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dump-json":
        dump_json(
            sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\layan\library-demo\library\provengo\products\run-source\samples.json",
            sys.argv[3] if len(sys.argv) > 3 else "python_observed.json",
        )
    else:
        # Usage: verify_state_features.py [samples.json] [--log run_id arm event_priority [log_path]]
        # --log appends a small per-run row (counts, not raw traces) to log_path (default:
        # state_feature_runs.csv next to this script) so future runs stay auditable without
        # keeping the multi-hundred-MB samples.json that produced them.
        args = sys.argv[1:]
        path = r"C:\Users\layan\library-demo\library\provengo\products\run-source\samples.json"
        run_id = arm = event_priority = None
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_feature_runs.csv")
        if args and args[0] != "--log":
            path = args[0]
            args = args[1:]
        if args and args[0] == "--log":
            run_id = args[1]
            arm = args[2]
            event_priority = args[3]
            if len(args) > 4:
                log_path = args[4]
        main(path, run_id=run_id, arm=arm, event_priority=event_priority, log_path=log_path)
