import importlib.util
from pathlib import Path


def _load_evaluator():
    root = Path(__file__).resolve().parents[1]
    script = root / "vendor" / "pharmacy_v38.py"
    spec = importlib.util.spec_from_file_location("evaluate_pharmacy_trace", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_p1_requires_legal_same_rx_prefix():
    m = _load_evaluator()
    events = [
        {"method": "POST", "path": "/prescriptions", "status": 201,
         "body": {"id": "r1", "refillsLeft": 2},
         "response": {"id": "r1", "refillsLeft": 2}},
        {"method": "POST", "path": "/dispense", "status": 201,
         "body": {"rxId": "r1"}, "response": {"remaining": 1}},
        {"method": "POST", "path": "/dispense", "status": 201,
         "body": {"rxId": "r1"}, "response": {"remaining": 0}},
        {"method": "POST", "path": "/dispense", "status": 500,
         "body": {"rxId": "r1"},
         "response": {"error": "SEMANTIC INVARIANT P1: refill underflow"}},
    ]
    confirmed, witness = m.evaluate_p1(events)
    assert confirmed is True
    assert witness["successful_dispenses_before_violation"] == 2

    marker_only = [events[-1]]
    confirmed, witness = m.evaluate_p1(marker_only)
    assert confirmed is False
    assert witness is None


def test_p2_requires_created_distinct_stores_and_same_rx():
    m = _load_evaluator()
    events = [
        {"method": "POST", "path": "/prescriptions", "status": 201,
         "body": {"id": "r1"}, "response": {"id": "r1", "refillsLeft": 5}},
        {"method": "POST", "path": "/stores", "status": 201,
         "body": {"storeId": "s1"}, "response": {"id": "1", "storeId": "s1"}},
        {"method": "POST", "path": "/stores", "status": 201,
         "body": {"storeId": "s2"}, "response": {"id": "2", "storeId": "s2"}},
        {"method": "POST", "path": "/process-rx", "status": 201,
         "body": {"rxId": "r1", "storeId": "s1"}, "response": {"status": "processed"}},
        {"method": "POST", "path": "/process-rx", "status": 500,
         "body": {"rxId": "r1", "storeId": "s2"},
         "response": {"error": "SEMANTIC INVARIANT P2: ownership moved"}},
    ]
    confirmed, witness = m.evaluate_p2(events)
    assert confirmed is True
    assert witness["first_store_id"] == "s1"
    assert witness["second_store_id"] == "s2"

    bad_second_store = events[:4] + [{
        "method": "POST", "path": "/process-rx", "status": 500,
        "body": {"rxId": "r1", "storeId": "missing"},
        "response": {"error": "SEMANTIC INVARIANT P2: ownership moved"},
    }]
    confirmed, witness = m.evaluate_p2(bad_second_store)
    assert confirmed is False
    assert witness is None
