import json
import re
import sys
from collections import defaultdict


def load_events(path):
    events = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = re.search(r"MODEL_EVENT\s+(\{.*\})", line)
            if not match:
                continue
            try:
                event = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def successful(event, method=None, path=None):
    if method is not None and event.get("method") != method:
        return False
    if path is not None and event.get("path") != path:
        return False
    status = event.get("status")
    return isinstance(status, int) and status < 400


def body_dict(event):
    value = event.get("body")
    return value if isinstance(value, dict) else {}


def response_dict(event):
    value = event.get("response")
    return value if isinstance(value, dict) else {}


def response_text(event):
    value = event.get("response")
    try:
        return json.dumps(value, sort_keys=True)
    except Exception:
        return str(value)


def canonical_id(value):
    return None if value is None else str(value)


def evaluate_p1(events):
    """Confirm refill underflow only after a legal, same-Rx prefix.

    Required sequence, all within this preserved HTTP trace:
      1. POST /prescriptions succeeds and exposes an integer refillsLeft >= 0.
      2. For that same prescription, exactly that many preceding POST /dispense
         calls succeed (status < 400), preserving the legal refill prefix.
      3. The next POST /dispense for the same prescription returns the P1
         class-specific semantic marker.

    This deliberately does not count a generic 500 or a P1 marker for an Rx
    whose legal creation/refill prefix is absent from the same trace.
    """
    rx_state = {}
    witness = None

    for index, event in enumerate(events):
        method = event.get("method")
        path = event.get("path", "")
        status = event.get("status")
        body = body_dict(event)
        response = response_dict(event)

        if method == "POST" and path == "/prescriptions" and isinstance(status, int) and status < 400:
            rx_id = canonical_id(response.get("id", body.get("id")))
            raw_refills = response.get("refillsLeft", body.get("refillsLeft"))
            if rx_id is None:
                continue
            try:
                refills = int(raw_refills)
            except (TypeError, ValueError):
                # The SUT publishes refillsLeft in a successful creation
                # response; without it the evaluator cannot establish the
                # refill-boundary precondition from external evidence.
                continue
            if refills < 0:
                continue
            rx_state[rx_id] = {
                "created_at": index,
                "initial_refills": refills,
                "successful_dispenses": 0,
            }
            continue

        if method == "POST" and path == "/dispense":
            rx_id = canonical_id(body.get("rxId"))
            if rx_id is None or rx_id not in rx_state:
                continue
            state = rx_state[rx_id]

            if isinstance(status, int) and status < 400:
                # A successful dispense belongs to the legal prefix. We allow
                # no more successful calls than the externally observed
                # refill allowance before the violating call.
                if state["successful_dispenses"] < state["initial_refills"]:
                    state["successful_dispenses"] += 1
                else:
                    # This would already be a semantic violation without the
                    # class marker; do not reinterpret it as the seeded P1.
                    state["successful_dispenses"] += 1
                continue

            if "SEMANTIC INVARIANT P1" in response_text(event):
                if state["successful_dispenses"] == state["initial_refills"]:
                    witness = {
                        "rx_id": rx_id,
                        "created_event_index": state["created_at"],
                        "initial_refills": state["initial_refills"],
                        "successful_dispenses_before_violation": state["successful_dispenses"],
                        "violation_event_index": index,
                        "violation_status": status,
                    }
                    return True, witness

    return False, witness


def evaluate_p2(events):
    """Confirm store-ownership transfer only after a legal, same-Rx prefix.

    Required sequence, all within this preserved HTTP trace:
      1. A prescription is successfully created.
      2. Two distinct stores are successfully created.
      3. /process-rx succeeds for the prescription at the first created store.
      4. A later /process-rx for the same prescription at the second created
         store returns the P2 class-specific semantic marker.

    Requiring both stores to have been created prevents arbitrary store IDs
    from satisfying the semantic oracle merely because the buggy SUT does not
    itself validate store existence in /process-rx.
    """
    prescriptions = set()
    stores = set()
    first_process = defaultdict(list)

    for index, event in enumerate(events):
        method = event.get("method")
        path = event.get("path", "")
        status = event.get("status")
        body = body_dict(event)
        response = response_dict(event)

        if method == "POST" and path == "/prescriptions" and isinstance(status, int) and status < 400:
            rx_id = canonical_id(response.get("id", body.get("id")))
            if rx_id is not None:
                prescriptions.add(rx_id)
            continue

        if method == "POST" and path == "/stores" and isinstance(status, int) and status < 400:
            store_id = canonical_id(response.get("storeId", body.get("storeId")))
            if store_id is not None:
                stores.add(store_id)
            continue

        if method == "POST" and path == "/process-rx":
            rx_id = canonical_id(body.get("rxId"))
            store_id = canonical_id(body.get("storeId"))
            if rx_id is None or store_id is None:
                continue
            if rx_id not in prescriptions or store_id not in stores:
                continue

            if isinstance(status, int) and status < 400:
                first_process[rx_id].append((store_id, index, status))
                continue

            if "SEMANTIC INVARIANT P2" in response_text(event):
                for first_store, first_index, first_status in first_process.get(rx_id, []):
                    if first_store != store_id and first_store in stores:
                        return True, {
                            "rx_id": rx_id,
                            "first_store_id": first_store,
                            "second_store_id": store_id,
                            "first_process_event_index": first_index,
                            "first_process_status": first_status,
                            "violation_event_index": index,
                            "violation_status": status,
                        }

    return False, None


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: evaluate_pharmacy_trace.py <http_trace.jsonl>")

    events = load_events(sys.argv[1])
    p1_confirmed, p1_witness = evaluate_p1(events)
    p2_confirmed, p2_witness = evaluate_p2(events)

    confirmed = []
    if p1_confirmed:
        confirmed.append("P1_REFILL_UNDERFLOW")
    if p2_confirmed:
        confirmed.append("P2_DOUBLE_PROCESS")

    result = {
        "schema_version": 2,
        "rule_basis": (
            "Sequence-local external HTTP evidence: a class is confirmed only "
            "when the preserved trace establishes its legal semantic prefix and "
            "the class-specific invariant-violation witness. Generic 500s and "
            "markers without the required prefix do not count."
        ),
        "refill_overrun_confirmed": p1_confirmed,
        "store_ownership_transfer_confirmed": p2_confirmed,
        "confirmed_classes": confirmed,
        "semantic_class_count": len(confirmed),
        "all_P1_P2_confirmed": p1_confirmed and p2_confirmed,
        "p1_witness": p1_witness,
        "p2_witness": p2_witness,
        "event_count": len(events),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
