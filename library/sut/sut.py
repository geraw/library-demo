"""
Library Management System REST API

This Flask application provides a RESTful API for managing a library system.
It handles books, users, loans, and holds with in-memory storage.

Routes:
- /users - User management
- /books - Book management
- /loans - Loan management
- /holds - Hold management
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, Response, jsonify, request

# Configure logging
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# In-memory storage
users: List[Dict[str, Any]] = []
books: List[Dict[str, Any]] = []
loans: List[Dict[str, Any]] = []
holds: List[Dict[str, Any]] = []


def parse_positive_int(value: Any, field_name: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """Validate positive integer IDs accepted by the model: int or numeric-string values."""
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


def get_json_object() -> Tuple[Optional[Dict[str, Any]], Optional[Response]]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "request body must be a JSON object"}), 400)
    return payload, None


# --- Database Management ---
def reset_database() -> tuple[Response, int]:
    """Reset all data stores and optionally initialize with provided data."""
    global users, books, loans, holds

    users = []
    loans = []
    holds = []
    books = []

    if request.is_json:
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            if "users" in data:
                users.extend(data["users"])
            if "loans" in data:
                loans.extend(data["loans"])
            if "holds" in data:
                holds.extend(data["holds"])
            if "books" in data:
                books.extend(data["books"])

    return (
        jsonify(
            {
                "message": "Database reset",
                "status": {
                    "users": len(users),
                    "loans": len(loans),
                    "holds": len(holds),
                    "books": len(books),
                },
            }
        ),
        200,
    )


# --- User Management ---
@app.route("/users", methods=["POST"])
def add_user() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error

    ok, user_id, user_err = parse_positive_int(payload.get("id"), "id")
    if not ok:
        return jsonify({"error": user_err}), 400

    name = payload.get("name")
    if not isinstance(name, str) or name == "":
        return jsonify({"error": "name must be a non-empty string"}), 400

    if any(u.get("id") == user_id for u in users):
        return jsonify({"error": "User already exists"}), 400

    user = {"id": user_id, "name": name}
    users.append(user)
    logger.info(f"Added new user: {user}")
    return jsonify(user), 201


@app.route("/users/<user_id>", methods=["DELETE"])
def delete_user(user_id: str) -> tuple[Response, int]:
    global users, loans, holds

    ok, parsed_user_id, err = parse_positive_int(user_id, "userId")
    if not ok:
        return jsonify({"error": err}), 400

    if any(loan.get("userId") == parsed_user_id for loan in loans) or any(
        hold.get("userId") == parsed_user_id for hold in holds
    ):
        return jsonify({"error": "Cannot delete user with active loans or holds"}), 400

    user = next((u for u in users if u.get("id") == parsed_user_id), None)
    if user is None:
        return jsonify({"error": "User not found"}), 404

    users = [u for u in users if u.get("id") != parsed_user_id]
    loans = [loan for loan in loans if loan.get("userId") != parsed_user_id]
    holds = [hold for hold in holds if hold.get("userId") != parsed_user_id]

    logger.info(f"Deleted user: {parsed_user_id}")
    return jsonify({"message": "User deleted"}), 200


@app.route("/users", methods=["GET"])
def search_users() -> Response:
    query = request.args.get("q", "").lower()
    results = [user for user in users if query in str(user).lower()] if query else users
    return jsonify(results)


# --- Book Management ---
@app.route("/books", methods=["POST"])
def add_book() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error

    ok, book_id, book_err = parse_positive_int(payload.get("id"), "id")
    if not ok:
        return jsonify({"error": book_err}), 400

    title = payload.get("title")
    if not isinstance(title, str) or title == "":
        return jsonify({"error": "title must be a non-empty string"}), 400

    if any(b.get("id") == book_id for b in books):
        return jsonify({"error": "Book already exists"}), 400

    book = {"id": book_id, "title": title}
    books.append(book)
    logger.info(f"Added new book: {book}")
    return jsonify(book), 201


@app.route("/books/<book_id>", methods=["DELETE"])
def delete_book(book_id: str) -> tuple[Response, int]:
    global books, loans, holds

    ok, parsed_book_id, err = parse_positive_int(book_id, "bookId")
    if not ok:
        return jsonify({"error": err}), 400

    if not any(b.get("id") == parsed_book_id for b in books):
        return jsonify({"error": "Book not found"}), 404

    if any(loan.get("bookId") == parsed_book_id for loan in loans) or any(
        hold.get("bookId") == parsed_book_id for hold in holds
    ):
        return jsonify({"error": "Cannot delete book with active loans or holds"}), 400

    books = [book for book in books if book.get("id") != parsed_book_id]
    loans = [loan for loan in loans if loan.get("bookId") != parsed_book_id]
    holds = [hold for hold in holds if hold.get("bookId") != parsed_book_id]

    logger.info(f"Deleted book: {parsed_book_id}")
    return jsonify({"message": "Book deleted"}), 200


@app.route("/books", methods=["GET"])
def search_books() -> Response:
    query = request.args.get("q", "").lower()
    results = [book for book in books if query in str(book).lower()] if query else books
    return jsonify(results)


@app.route("/books/<book_id>", methods=["GET"])
def get_book(book_id: str):
    ok, parsed_book_id, err = parse_positive_int(book_id, "bookId")
    if not ok:
        return jsonify({"error": err}), 400

    book = next((b for b in books if b.get("id") == parsed_book_id), None)
    if book is None:
        return jsonify({"error": "Book not found"}), 404
    return jsonify(book), 200


# --- Loan Management ---
@app.route("/loans", methods=["POST"])
def add_loan() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error

    user_ok, user_id, user_err = parse_positive_int(payload.get("userId"), "userId")
    if not user_ok:
        return jsonify({"error": user_err}), 400

    book_ok, book_id, book_err = parse_positive_int(payload.get("bookId"), "bookId")
    if not book_ok:
        return jsonify({"error": book_err}), 400

    if not any(u.get("id") == user_id for u in users):
        return jsonify({"error": f"User {user_id} does not exist"}), 400
    if not any(b.get("id") == book_id for b in books):
        return jsonify({"error": f"Book {book_id} does not exist"}), 400

    if any(loan.get("userId") == user_id for loan in loans):
        return jsonify({"error": "User already has an active loan"}), 400
    if any(loan.get("bookId") == book_id for loan in loans):
        return jsonify({"error": "Book already has an active loan"}), 400
    if any(loan.get("userId") == user_id and loan.get("bookId") == book_id for loan in loans):
        return jsonify({"error": "Loan already exists"}), 400

    loan = {"userId": user_id, "bookId": book_id}
    loans.append(loan)
    logger.info(f"Added new loan: {loan}")
    return jsonify(loan), 201


@app.route("/loans/<user_id>/<book_id>", methods=["DELETE"])
def delete_loan(user_id: str, book_id: str) -> tuple[Response, int]:
    global loans

    user_ok, parsed_user_id, user_err = parse_positive_int(user_id, "userId")
    if not user_ok:
        return jsonify({"error": user_err}), 400

    book_ok, parsed_book_id, book_err = parse_positive_int(book_id, "bookId")
    if not book_ok:
        return jsonify({"error": book_err}), 400

    matched = [loan for loan in loans if loan.get("userId") == parsed_user_id and loan.get("bookId") == parsed_book_id]
    if not matched:
        return jsonify({"error": "Loan not found"}), 404

    loans = [loan for loan in loans if not (loan.get("userId") == parsed_user_id and loan.get("bookId") == parsed_book_id)]
    logger.info(f"Deleted loan: userId={parsed_user_id}, bookId={parsed_book_id}")
    return jsonify({"message": "Loan deleted"}), 200


@app.route("/loans", methods=["GET"])
def search_loans() -> Response:
    user_id = request.args.get("userId")
    book_id = request.args.get("bookId")

    if user_id is not None:
        ok, parsed_user_id, err = parse_positive_int(user_id, "userId")
        if not ok:
            return jsonify({"error": err}), 400
    else:
        parsed_user_id = None

    if book_id is not None:
        ok, parsed_book_id, err = parse_positive_int(book_id, "bookId")
        if not ok:
            return jsonify({"error": err}), 400
    else:
        parsed_book_id = None

    results = loans
    if parsed_user_id is not None:
        results = [loan for loan in results if loan.get("userId") == parsed_user_id]
    if parsed_book_id is not None:
        results = [loan for loan in results if loan.get("bookId") == parsed_book_id]
    return jsonify(results)


# --- Hold Management ---
@app.route("/holds", methods=["POST"])
def add_hold() -> tuple[Response, int]:
    payload, error = get_json_object()
    if error is not None:
        return error

    ok, hold_id, hold_err = parse_positive_int(payload.get("id"), "id")
    if not ok:
        return jsonify({"error": hold_err}), 400

    user_ok, user_id, user_err = parse_positive_int(payload.get("userId"), "userId")
    if not user_ok:
        return jsonify({"error": user_err}), 400

    book_ok, book_id, book_err = parse_positive_int(payload.get("bookId"), "bookId")
    if not book_ok:
        return jsonify({"error": book_err}), 400

    if any(h.get("id") == hold_id for h in holds):
        return jsonify({"error": "Hold already exists"}), 400
    if not any(u.get("id") == user_id for u in users):
        return jsonify({"error": f"User {user_id} does not exist"}), 400
    if not any(b.get("id") == book_id for b in books):
        return jsonify({"error": f"Book {book_id} does not exist"}), 400

    hold = {"id": hold_id, "userId": user_id, "bookId": book_id}
    holds.append(hold)
    logger.info(f"Added new hold: {hold}")
    return jsonify(hold), 201


@app.route("/holds/<hold_id>", methods=["DELETE"])
def delete_hold(hold_id: str) -> tuple[Response, int]:
    global holds

    ok, parsed_hold_id, err = parse_positive_int(hold_id, "id")
    if not ok:
        return jsonify({"error": err}), 400

    if not any(hold.get("id") == parsed_hold_id for hold in holds):
        return jsonify({"error": "Hold not found"}), 404

    holds = [hold for hold in holds if hold.get("id") != parsed_hold_id]
    logger.info(f"Deleted hold with ID: {parsed_hold_id}")
    return jsonify({"message": "Hold deleted"}), 200


@app.route("/holds", methods=["GET"])
def search_holds() -> Response:
    query = request.args.get("q", "").lower()
    results = [hold for hold in holds if query in str(hold).lower()] if query else holds
    return jsonify(results)


# --- Application Entry Point ---
if __name__ == "__main__":
    HOST = "localhost"
    PORT = 23242
    DEBUG = True

    logger.info(f"Starting server on {HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)