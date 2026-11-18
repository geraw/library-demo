"""Verify public HTTP witnesses against the original, baseline and isolated faults."""

from importlib.util import module_from_spec

from server import app, original, select_fault


def send(client, method, path, status=200, **body):
    options = {"json": body} if method == "POST" else {}
    response = client.open(path, method=method, **options)
    assert response.status_code == status, (method, path, response.status_code, response.get_json())
    return response.get_json()


def create(client, resource, **body):
    return send(client, "POST", f"/{resource}", 201, **body)


def c1(client):
    def setup():
        send(client, "POST", "/reset")
        users = [create(client, "users", name=name) for name in ("Dana", "Yossi")]
        books = [create(client, "books", title=title) for title in ("A", "B")]
        return [
            create(client, "loans", userId=user["id"], bookId=book["id"])
            for user, book in zip(users, books)
        ]

    first, second = setup()
    query = f'/loans?userId={first["userId"]}'
    assert send(client, "GET", query) == [first]
    affected = send(client, "GET", "/loans") == [first]
    if not affected:
        assert send(client, "GET", "/loans") == [first, second]

    first, second = setup()
    assert send(client, "GET", "/loans") == [first, second]
    assert send(client, "GET", f'/loans?userId={first["userId"]}') == [first]
    return affected


def c2(client):
    send(client, "POST", "/reset")
    user = create(client, "users", name="Dana")["id"]
    book = create(client, "books", title="A")["id"]
    another_book = create(client, "books", title="B")["id"]
    unrelated = create(client, "holds", userId=user, bookId=another_book)
    first = create(client, "holds", userId=user, bookId=book)
    send(client, "DELETE", f'/holds/{first["id"]}')
    assert send(client, "GET", "/holds") == [unrelated]

    first = create(client, "holds", userId=user, bookId=book)
    second = create(client, "holds", userId=user, bookId=book)
    assert first["id"] != second["id"]
    send(client, "DELETE", f'/holds/{first["id"]}')
    remaining = send(client, "GET", "/holds")
    assert remaining in ([unrelated], [unrelated, second])
    return remaining == [unrelated]


def c3(client):
    send(client, "POST", "/reset")
    first = create(client, "books", title="A")
    second = create(client, "books", title="B")
    control = create(client, "books", title="control")
    assert len({first["id"], second["id"], control["id"]}) == 3

    send(client, "POST", "/reset")
    first = create(client, "books", title="A")
    second = create(client, "books", title="B")
    send(client, "DELETE", f'/books/{first["id"]}')
    assert send(client, "GET", "/books") == [second]
    replacement = create(client, "books", title="C")
    assert replacement["id"] != first["id"]
    assert send(client, "GET", f'/books/{second["id"]}') == second
    readback = send(client, "GET", f'/books/{replacement["id"]}')
    assert send(client, "GET", "/books") == [second, replacement]
    return replacement["id"] == second["id"] and readback != replacement


def main():
    original_spec = original.__spec__

    pristine = module_from_spec(original_spec)
    original_spec.loader.exec_module(pristine)
    witnesses = {"C1": c1, "C2": c2, "C3": c3}
    for name, witness in witnesses.items():
        assert not witness(pristine.app.test_client()), ("original", name)
    print("Original: all witnesses and controls passed")
    for fault in (None, *witnesses):
        select_fault(fault)
        for name, witness in witnesses.items():
            assert witness(app.test_client()) == (fault == name), (fault, name)
        print(f"{fault or 'off'}: witnesses and controls passed")


if __name__ == "__main__":
    main()
