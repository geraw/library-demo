"""Run the Library SUT with at most one archive-inspired fault."""

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from flask import jsonify, request


FAULTS = ("F1", "F2", "F3", "F4", "F5", "F6")


def create_app(fault=None):
    if fault not in (None, *FAULTS):
        raise ValueError(fault)
    original = Path(__file__).resolve().parents[1] / "mutants-v003" / "original.py"
    spec = spec_from_file_location("_archive_library", original)
    library = module_from_spec(spec)
    spec.loader.exec_module(library)
    app = library.app
    if fault is None:
        return app

    returned_by_book = {}
    views = app.view_functions

    def has_loan(*, user_id=None, book_id=None):
        return any((user_id is None or row["userId"] == user_id)
                   and (book_id is None or row["bookId"] == book_id)
                   for row in library.loans)

    def positive_id(value):
        return library.parse_positive_int(value, "id")[1]

    if fault == "F1":
        @app.before_request
        def reject_loan_when_patron_has_another_hold():
            if request.endpoint != "add_loan":
                return
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return
            user_id = positive_id(payload.get("userId"))
            book_id = positive_id(payload.get("bookId"))
            if (user_id is not None and book_id is not None
                    and any(user["id"] == user_id for user in library.users)
                    and any(book["id"] == book_id for book in library.books)
                    and not has_loan(user_id=user_id) and not has_loan(book_id=book_id)
                    and any(hold["userId"] == user_id and hold["bookId"] != book_id
                            for hold in library.holds)):
                return jsonify(error="User already has an active loan"), 400

    if fault in ("F2", "F5"):
        add_hold = views["add_hold"]

        def add_hold_with_fault():
            response = app.make_response(add_hold())
            if response.status_code != 201:
                return response
            created = response.get_json()
            user_id, book_id = created["userId"], created["bookId"]
            existing = [hold for hold in library.holds if hold["id"] != created["id"]]
            if fault == "F2" and has_loan(book_id=book_id):
                prior = next((hold for hold in existing if hold["userId"] == user_id
                              and hold["bookId"] != book_id and has_loan(book_id=hold["bookId"])), None)
                if prior is not None:
                    row = next(hold for hold in library.holds if hold["id"] == created["id"])
                    row["bookId"] = prior["bookId"]
                    return jsonify(row), 201
            if fault == "F5":
                prior = next((hold for hold in existing if hold["bookId"] == book_id
                              and hold["userId"] != user_id), None)
                if prior is not None:
                    created["userId"] = prior["userId"]
                    return jsonify(created), 201
            return response

        views["add_hold"] = add_hold_with_fault

    if fault in ("F3", "F4", "F6"):
        reset_database = views["reset_database"]
        delete_loan = views["delete_loan"]

        def reset_with_history():
            response = reset_database()
            returned_by_book.clear()
            return response

        def return_with_history(user_id, book_id):
            response = app.make_response(delete_loan(user_id, book_id))
            if response.status_code == 200:
                patron, book = positive_id(user_id), positive_id(book_id)
                returned_by_book[book] = patron
                if fault == "F6" and any(hold["bookId"] == book and hold["userId"] != patron
                                         for hold in library.holds):
                    return jsonify(error="Failed to process waiting holds after return"), 500
            return response

        views["reset_database"] = reset_with_history
        views["delete_loan"] = return_with_history

    if fault == "F3":
        delete_hold = views["delete_hold"]

        def delete_hold_with_fault(hold_id):
            target = next((hold for hold in library.holds if hold["id"] == positive_id(hold_id)), None)
            if target is not None:
                book = target["bookId"]
                if (book in returned_by_book and not has_loan(book_id=book)
                        and any(hold["id"] != target["id"] and hold["bookId"] == book
                                for hold in library.holds)):
                    return jsonify(message="Hold deleted"), 200
            return delete_hold(hold_id)

        views["delete_hold"] = delete_hold_with_fault

    if fault == "F4":
        search_loans = views["search_loans"]

        def search_loans_with_fault():
            response = app.make_response(search_loans())
            patron = positive_id(request.args.get("userId"))
            book = positive_id(request.args.get("bookId"))
            if (response.status_code == 200 and patron is not None and book is not None
                    and returned_by_book.get(book) == patron):
                return jsonify([loan for loan in library.loans if loan["bookId"] == book])
            return response

        views["search_loans"] = search_loans_with_fault

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faults", choices=FAULTS, help="Enable one fault (default: all disabled).")
    parser.add_argument("--port", default=23601, type=int, help="Listening port (default: 23601).")
    args = parser.parse_args()
    create_app(args.faults).run(host="127.0.0.1", port=args.port, threaded=False)

