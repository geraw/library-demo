"""
Library Management System REST API - E6 logic-mutant fixture (v013).

Healthy behaviour is the experiment contract of sut_buggy_issta.py with ISSTA_BUGS=none (no
per-reader loan cap, one active loan per book, no duplicate active pair, deletes blocked by
loans or holds). Exactly one logic mutation from library/bug_mapping_library_system.md
(chapters 2-3) is enabled per process, selected by the environment variable ISSTA_BUGS, which
the v006 observer forwards from its --bugs argument. "none" is the healthy control.

Input-validation (type) mutations are deliberately absent. See MUTANTS for the catalogue.
"""

import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, Response, jsonify, request

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# id -> (catalogue reference, description, channel expected to kill it)
MUTANTS: Dict[str, Tuple[str, str, str]] = {
    "U1": ("2.3.3", "POST /users answers 200 instead of 201", "native"),
    "U2": ("2.4.2", "delete_user ignores holds (a reader with a hold is deleted)", "native"),
    "U3": ("2.4.3", "delete_user ignores loans (a reader with a loan is deleted)", "native"),
    "U4": ("2.4.1", "delete_user checks loan.bookId against the reader id instead of loan.userId", "native"),
    "U5": ("2.4.4", "delete_user removes the first reader in the pool instead of the addressed one", "observer"),
    "U6": ("2.4.6", "delete_user answers 404 for an existing reader and deletes nothing", "native"),
    "U7": ("2.4.5", "delete_user answers 204 instead of 200", "native"),
    "B1": ("2.6.3", "POST /books answers 200 instead of 201", "native"),
    "B2": ("2.7.1", "delete_book skips the existence check: a missing book answers 200", "native"),
    "B3": ("2.7.3", "delete_book ignores holds (a held book is deleted)", "native"),
    "B4": ("2.7.4", "delete_book ignores loans (a loaned book is deleted)", "native"),
    "B5": ("2.7.5", "delete_book deletes every book except the addressed one", "observer"),
    "B6": ("2.8.2", "GET /books/{id} answers 404 for an existing book", "native+observer"),
    "B7": ("2.7.2", "delete_book checks loan.userId against the book id instead of loan.bookId", "native"),
    "L1": ("2.9.4", "add_loan without the one-active-loan-per-book check", "native"),
    "L2": ("2.9.6a", "add_loan without the reader-exists check", "native"),
    "L3": ("2.9.6b", "add_loan without the book-exists check", "native"),
    "L4": ("2.10.1", "delete_loan removes every loan of the reader OR of the book (and -> or)", "observer"),
    "L5": ("2.10.2", "delete_loan: 404 for an existing loan (nothing deleted), 200 for a missing one", "native"),
    "L6": ("2.10.3", "delete_loan matches with reader and book swapped (never finds the loan)", "native"),
    "L7": ("2.11.2", "GET /loans applies the bookId filter to all loans, ignoring the userId filter", "none (list contents are not checked)"),
    "L8": ("3.8", "add_loan on a loaned book answers 400 but records the loan anyway", "observer"),
    "H1": ("2.12.2", "add_hold without the reader-exists check", "native"),
    "H2": ("2.12.3", "add_hold without the book-exists check", "native"),
    "H3": ("2.12.6", "add_hold rejects a second hold by the same reader with 400", "native"),
    "H4": ("2.13.1", "delete_hold deletes every hold except the addressed one", "observer"),
    "H5": ("2.13.2", "delete_hold: 404 for an existing hold (nothing deleted), 200 for a missing one", "native"),
    "H6": ("2.13.3", "delete_hold answers 400 while the hold's book is on loan", "native"),
    "H7": ("3.5", "add_hold rejects a second hold on the same book with 400", "native"),
    "H8": ("3.16", "add_loan rejects a reader who is not the first holder of the book with 400", "native"),
}

_raw = os.environ.get("ISSTA_BUGS", "none").strip()
MUTANT: Optional[str] = None if _raw.lower() == "none" else _raw
if MUTANT is not None and MUTANT not in MUTANTS:
    raise ValueError("ISSTA_BUGS must be none or one of: " + ", ".join(MUTANTS))
BUGS = set()  # kept for the observer's fixture check; ISSTA mutations are never enabled here


def on(mutant: str) -> bool:
    return MUTANT == mutant


users: List[Dict[str, Any]] = []
books: List[Dict[str, Any]] = []
loans: List[Dict[str, Any]] = []
holds: List[Dict[str, Any]] = []


def parse_positive_int(value: Any, field_name: str) -> Tuple[bool, Optional[int], Optional[str]]:
    if isinstance(value, bool):
        return False, None, f"{field_name} must be a positive integer"
    if isinstance(value, int):
        numeric = value
    elif isinstance(value, str):
        value = value.strip()
        if value == "" or not re.fullmatch(r"\d+", value):
            return False, None, f"{field_name} must be a positive integer"
        numeric = int(value)
    else:
        return False, None, f"{field_name} must be a positive integer"
    if numeric <= 0:
        return False, None, f"{field_name} must be a positive integer"
    return True, numeric, None


_ID_MIN = 100000
_ID_MAX = 999999
_issued_ids: Dict[str, set] = {"users": set(), "books": set(), "loans": set(), "holds": set()}


def generate_unique_id(id_kind: str) -> int:
    issued = _issued_ids[id_kind]
    while True:
        candidate = random.randint(_ID_MIN, _ID_MAX)
        if candidate not in issued:
            issued.add(candidate)
            return candidate


def get_json_object() -> Tuple[Optional[Dict[str, Any]], Optional[Response]]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "request body must be a JSON object"}), 400)
    return payload, None


@app.route("/reset", methods=["POST"])
def reset_database() -> tuple[Response, int]:
    global users, books, loans, holds
    users, books, loans, holds = [], [], [], []
    for kind in _issued_ids:
        _issued_ids[kind] = set()
    return jsonify({"message": "Database reset", "status": {"users": 0, "loans": 0, "holds": 0, "books": 0}}), 200


# --- Users ---
@app.route("/users", methods=["POST"])
def add_user() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error
    name = payload.get("name")
    if not isinstance(name, str) or name == "":
        return jsonify({"error": "name must be a non-empty string"}), 400
    user = {"id": generate_unique_id("users"), "name": name}
    users.append(user)
    return jsonify(user), (200 if on("U1") else 201)


@app.route("/users/<user_id>", methods=["DELETE"])
def delete_user(user_id: str) -> tuple[Response, int]:
    global users, loans, holds
    ok, uid, err = parse_positive_int(user_id, "userId")
    if not ok:
        return jsonify({"error": err}), 400

    if on("U4"):
        has_loan = any(loan.get("bookId") == uid for loan in loans)
    elif on("U3"):
        has_loan = False
    else:
        has_loan = any(loan.get("userId") == uid for loan in loans)
    has_hold = False if on("U2") else any(hold.get("userId") == uid for hold in holds)
    if has_loan or has_hold:
        return jsonify({"error": "Cannot delete user with active loans or holds"}), 400

    user = next((u for u in users if u.get("id") == uid), None)
    if on("U6"):
        if user is not None:
            return jsonify({"error": "User not found"}), 404
    elif user is None:
        return jsonify({"error": "User not found"}), 404

    if on("U5") and users:
        users = users[1:]
    else:
        users = [u for u in users if u.get("id") != uid]
    loans = [loan for loan in loans if loan.get("userId") != uid]
    holds = [hold for hold in holds if hold.get("userId") != uid]
    if on("U7"):
        return Response(status=204), 204
    return jsonify({"message": "User deleted"}), 200


@app.route("/users", methods=["GET"])
def search_users() -> Response:
    query = request.args.get("q", "").lower()
    return jsonify([u for u in users if query in str(u).lower()] if query else users)


# --- Books ---
@app.route("/books", methods=["POST"])
def add_book() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error
    title = payload.get("title")
    if not isinstance(title, str) or title == "":
        return jsonify({"error": "title must be a non-empty string"}), 400
    book = {"id": generate_unique_id("books"), "title": title}
    books.append(book)
    return jsonify(book), (200 if on("B1") else 201)


@app.route("/books/<book_id>", methods=["DELETE"])
def delete_book(book_id: str) -> tuple[Response, int]:
    global books, loans, holds
    ok, bid, err = parse_positive_int(book_id, "bookId")
    if not ok:
        return jsonify({"error": err}), 400

    if not on("B2") and not any(b.get("id") == bid for b in books):
        return jsonify({"error": "Book not found"}), 404

    if on("B7"):
        has_loan = any(loan.get("userId") == bid for loan in loans)
    elif on("B4"):
        has_loan = False
    else:
        has_loan = any(loan.get("bookId") == bid for loan in loans)
    has_hold = False if on("B3") else any(hold.get("bookId") == bid for hold in holds)
    if has_loan or has_hold:
        return jsonify({"error": "Cannot delete book with active loans or holds"}), 400

    if on("B5"):
        books = [book for book in books if book.get("id") == bid]
    else:
        books = [book for book in books if book.get("id") != bid]
    loans = [loan for loan in loans if loan.get("bookId") != bid]
    holds = [hold for hold in holds if hold.get("bookId") != bid]
    return jsonify({"message": "Book deleted"}), 200


@app.route("/books", methods=["GET"])
def search_books() -> Response:
    query = request.args.get("q", "").lower()
    return jsonify([b for b in books if query in str(b).lower()] if query else books)


@app.route("/books/<book_id>", methods=["GET"])
def get_book(book_id: str):
    ok, bid, err = parse_positive_int(book_id, "bookId")
    if not ok:
        return jsonify({"error": err}), 400
    book = next((b for b in books if b.get("id") == bid), None)
    if book is None or on("B6"):
        return jsonify({"error": "Book not found"}), 404
    return jsonify(book), 200


# --- Loans ---
@app.route("/loans", methods=["POST"])
def add_loan() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error
    user_ok, uid, user_err = parse_positive_int(payload.get("userId"), "userId")
    if not user_ok:
        return jsonify({"error": user_err}), 400
    book_ok, bid, book_err = parse_positive_int(payload.get("bookId"), "bookId")
    if not book_ok:
        return jsonify({"error": book_err}), 400
    if not on("L2") and not any(u.get("id") == uid for u in users):
        return jsonify({"error": f"User {uid} does not exist"}), 400
    if not on("L3") and not any(b.get("id") == bid for b in books):
        return jsonify({"error": f"Book {bid} does not exist"}), 400
    if on("H8"):
        holders = [hold.get("userId") for hold in holds if hold.get("bookId") == bid]
        if holders and holders[0] != uid:
            return jsonify({"error": "Book is reserved by another reader"}), 400
    if not on("L1") and any(loan.get("bookId") == bid for loan in loans):
        if on("L8"):
            loans.append({"id": generate_unique_id("loans"), "userId": uid, "bookId": bid})
        return jsonify({"error": "Book already has an active loan"}), 400
    if any(loan.get("userId") == uid and loan.get("bookId") == bid for loan in loans):
        return jsonify({"error": "Loan already exists"}), 400
    loan = {"id": generate_unique_id("loans"), "userId": uid, "bookId": bid}
    loans.append(loan)
    return jsonify(loan), 201


@app.route("/loans/<user_id>/<book_id>", methods=["DELETE"])
def delete_loan(user_id: str, book_id: str) -> tuple[Response, int]:
    global loans
    user_ok, uid, user_err = parse_positive_int(user_id, "userId")
    if not user_ok:
        return jsonify({"error": user_err}), 400
    book_ok, bid, book_err = parse_positive_int(book_id, "bookId")
    if not book_ok:
        return jsonify({"error": book_err}), 400

    if on("L6"):
        matched = [loan for loan in loans if loan.get("userId") == bid and loan.get("bookId") == uid]
    else:
        matched = [loan for loan in loans if loan.get("userId") == uid and loan.get("bookId") == bid]
    if on("L5"):
        if matched:
            return jsonify({"error": "Loan not found"}), 404
        return jsonify({"message": "Loan deleted"}), 200
    if not matched:
        return jsonify({"error": "Loan not found"}), 404

    if on("L4"):
        loans = [loan for loan in loans if not (loan.get("userId") == uid or loan.get("bookId") == bid)]
    else:
        loans = [loan for loan in loans if not (loan.get("userId") == uid and loan.get("bookId") == bid)]
    return jsonify({"message": "Loan deleted"}), 200


@app.route("/loans", methods=["GET"])
def search_loans() -> Response:
    user_id = request.args.get("userId")
    book_id = request.args.get("bookId")
    parsed_user_id = parsed_book_id = None
    if user_id is not None:
        ok, parsed_user_id, err = parse_positive_int(user_id, "userId")
        if not ok:
            return jsonify({"error": err}), 400
    if book_id is not None:
        ok, parsed_book_id, err = parse_positive_int(book_id, "bookId")
        if not ok:
            return jsonify({"error": err}), 400
    results = loans
    if parsed_user_id is not None:
        results = [loan for loan in results if loan.get("userId") == parsed_user_id]
    if parsed_book_id is not None:
        source = loans if on("L7") else results
        results = [loan for loan in source if loan.get("bookId") == parsed_book_id]
    return jsonify(results)


# --- Holds ---
@app.route("/holds", methods=["POST"])
def add_hold() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error
    user_ok, uid, user_err = parse_positive_int(payload.get("userId"), "userId")
    if not user_ok:
        return jsonify({"error": user_err}), 400
    book_ok, bid, book_err = parse_positive_int(payload.get("bookId"), "bookId")
    if not book_ok:
        return jsonify({"error": book_err}), 400
    if not on("H1") and not any(u.get("id") == uid for u in users):
        return jsonify({"error": f"User {uid} does not exist"}), 400
    if not on("H2") and not any(b.get("id") == bid for b in books):
        return jsonify({"error": f"Book {bid} does not exist"}), 400
    if on("H3") and any(hold.get("userId") == uid for hold in holds):
        return jsonify({"error": "Reader already has a hold"}), 400
    if on("H7") and any(hold.get("bookId") == bid for hold in holds):
        return jsonify({"error": "Book already has a hold"}), 400
    hold = {"id": generate_unique_id("holds"), "userId": uid, "bookId": bid}
    holds.append(hold)
    return jsonify(hold), 201


@app.route("/holds/<hold_id>", methods=["DELETE"])
def delete_hold(hold_id: str) -> tuple[Response, int]:
    global holds
    ok, hid, err = parse_positive_int(hold_id, "id")
    if not ok:
        return jsonify({"error": err}), 400
    hold = next((h for h in holds if h.get("id") == hid), None)
    if on("H5"):
        if hold is not None:
            return jsonify({"error": "Hold not found"}), 404
        return jsonify({"message": "Hold deleted"}), 200
    if hold is None:
        return jsonify({"error": "Hold not found"}), 404
    if on("H6") and any(loan.get("bookId") == hold.get("bookId") for loan in loans):
        return jsonify({"error": "Cannot cancel a hold on a loaned book"}), 400
    if on("H4"):
        holds = [h for h in holds if h.get("id") == hid]
    else:
        holds = [h for h in holds if h.get("id") != hid]
    return jsonify({"message": "Hold deleted"}), 200


@app.route("/holds", methods=["GET"])
def search_holds() -> Response:
    query = request.args.get("q", "").lower()
    return jsonify([h for h in holds if query in str(h).lower()] if query else holds)


if __name__ == "__main__":
    logger.info(f"E6 fixture, mutant={MUTANT}")
    app.run(host="localhost", port=23242, debug=False)
