import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "vendor" / "library_v38.py"
SPEC = importlib.util.spec_from_file_location("library_sequence_evaluator", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def event(method, path, body=None, status=201, response=None):
    return {
        "kind": "api_success" if status < 400 else "api_result",
        "method": method,
        "path": path,
        "body": body,
        "status": status,
        "response": response,
    }


def user(uid):
    return event("POST", "/users", {"id": uid, "name": f"u{uid}"}, response={"id": uid, "name": f"u{uid}"})


def book(bid):
    return event("POST", "/books", {"id": bid, "title": f"b{bid}"}, response={"id": bid, "title": f"b{bid}"})


def loan(uid, bid, status=201):
    return event("POST", "/loans", {"userId": uid, "bookId": bid}, status=status, response={"userId": uid, "bookId": bid})


def hold(hid, uid, bid):
    return event("POST", "/holds", {"id": hid, "userId": uid, "bookId": bid}, response={"id": hid, "userId": uid, "bookId": bid})


def test_both_classes_in_one_sequence_and_flat_class_array():
    sequence = [user(1), user(2), book(1), book(2), book(3), hold(7, 1, 1), loan(2, 1), loan(2, 2), loan(2, 3)]
    result = MOD.evaluate_sequence(sequence)
    assert result["confirmed_classes"] == ["HOLD_OWNERSHIP", "LOAN_LIMIT"]
    assert result["semantic_class_count"] == 2
    assert result["semantic_score"] == "2/2"


def test_loan_limit_does_not_stitch_across_sequences():
    first = MOD.evaluate_sequence([user(1), book(1), book(2), loan(1, 1), loan(1, 2)])
    second = MOD.evaluate_sequence([user(1), book(3), loan(1, 3)])
    campaign = MOD.evaluate_sequence([user(1), book(1), book(2), book(3), loan(1, 1), loan(1, 2), loan(1, 3)])
    assert first["confirmed_classes"] == []
    assert second["confirmed_classes"] == []
    assert campaign["confirmed_classes"] == ["LOAN_LIMIT"]


def test_hold_ownership_does_not_stitch_across_sequences():
    first = MOD.evaluate_sequence([user(1), book(1), hold(1, 1, 1)])
    second = MOD.evaluate_sequence([user(2), book(1), loan(2, 1)])
    campaign = MOD.evaluate_sequence([user(1), user(2), book(1), hold(1, 1, 1), loan(2, 1)])
    assert first["confirmed_classes"] == []
    assert second["confirmed_classes"] == []
    assert campaign["confirmed_classes"] == ["HOLD_OWNERSHIP"]


def test_deleted_hold_and_returned_loan_do_not_count():
    sequence = [
        user(1), user(2), book(1), book(2), book(3),
        hold(9, 1, 1), event("DELETE", "/holds/9", status=200), loan(2, 1),
        loan(2, 2), event("DELETE", "/loans/2/1", status=200), loan(2, 3),
    ]
    assert MOD.evaluate_sequence(sequence)["confirmed_classes"] == []


def test_failed_requests_do_not_change_semantic_state():
    sequence = [user(1), book(1), book(2), book(3), loan(1, 1), loan(1, 2), loan(1, 3, status=422)]
    assert MOD.evaluate_sequence(sequence)["confirmed_classes"] == []


def test_three_distinct_books_are_required():
    sequence = [user(1), book(1), book(2), loan(1, 1), loan(1, 1), loan(1, 2)]
    assert MOD.evaluate_sequence(sequence)["confirmed_classes"] == []


def test_ids_are_normalized_between_request_and_path():
    sequence = [user(1), book(1), book(2), book(3), loan("1", "1"), loan(1, 2), loan("1", 3)]
    assert MOD.evaluate_sequence(sequence)["confirmed_classes"] == ["LOAN_LIMIT"]


def test_campaign_preexisting_entities_are_not_a_local_prefix():
    assert MOD.evaluate_sequence([loan(1, 1), loan(1, 2), loan(1, 3)])["confirmed_classes"] == []


def test_manifest_incomplete_means_no_exact_official_score(tmp_path, monkeypatch, capsys):
    sequence_dir = tmp_path / "sequences"
    sequence_dir.mkdir()
    (sequence_dir / "sequence_manifest.json").write_text(json.dumps({
        "official_evaluation_complete": False,
        "official_status": "undetermined_missing_boundaries",
        "sequences": [],
    }), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["evaluate_library_sequences.py", "--sequence-dir", str(sequence_dir)])
    assert MOD.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["official_status"] == "undetermined_missing_boundaries"
    assert output["sequence_confirmed_score"] is None
    assert output["sequence_confirmed_lower_bound"] == "0/2"
