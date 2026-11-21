"""Run the frozen Library API with one optional semantic fault (C1, C2 or C3)."""

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from flask import request

original_path = Path(__file__).resolve().parents[1] / "mutants-v003" / "original.py"
spec = spec_from_file_location("_feature_mutants_original", original_path)
original = module_from_spec(spec)
spec.loader.exec_module(original)
app = original.app

search_loans = app.view_functions["search_loans"]
delete_hold = app.view_functions["delete_hold"]
reset_database = app.view_functions["reset_database"]
generate_unique_id = original.generate_unique_id
book_slots = []


def search_loans_with_fault():
    response = app.make_response(search_loans())
    if response.status_code == 200 and {"userId", "bookId"}.intersection(request.args):
        selected = response.get_json()
        if 0 < len(selected) < len(original.loans):
            # The nonempty filtered result mistakenly compacts the shared backing list.
            original.loans[:] = selected
    return response


def delete_hold_with_fault(hold_id):
    valid, parsed_id, _ = original.parse_positive_int(hold_id, "id")
    selected = next((row for row in original.holds if row["id"] == parsed_id), None) if valid else None
    response = app.make_response(delete_hold(hold_id))
    if selected is not None and response.status_code == 200:
        # Cleanup scopes the deletion to the pair instead of the requested hold ID.
        pair = (selected["userId"], selected["bookId"])
        original.holds[:] = [
            row for row in original.holds if (row["userId"], row["bookId"]) != pair
        ]
    return response


def reset_with_slots():
    response = reset_database()
    book_slots[:] = [book["id"] for book in original.books]
    return response


def allocate_book_id_with_fault(kind):
    if kind != "books":
        return generate_unique_id(kind)
    slot = len(original.books)
    if slot < len(book_slots):
        # Active row count understates the high-water mark after a deletion.
        candidate = book_slots[slot]
        if any(book["id"] == candidate for book in original.books):
            return candidate
    book_id = generate_unique_id(kind)
    book_slots.append(book_id)
    return book_id


def select_fault(fault):
    app.view_functions["search_loans"] = search_loans_with_fault if fault == "C1" else search_loans
    app.view_functions["delete_hold"] = delete_hold_with_fault if fault == "C2" else delete_hold
    app.view_functions["reset_database"] = reset_with_slots if fault == "C3" else reset_database
    original.generate_unique_id = allocate_book_id_with_fault if fault == "C3" else generate_unique_id
    if fault == "C3":
        book_slots[:] = [book["id"] for book in original.books]


def main(default_port=23242):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faults", choices=("C1", "C2", "C3"), help="Enable one fault.")
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()
    select_fault(args.faults)
    app.run(host="127.0.0.1", port=args.port, threaded=False)


if __name__ == "__main__":
    main()

