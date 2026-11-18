"""Run directed public API checks for the archive-inspired Library faults."""

from library_sut_netbox_gitea import FAULTS, create_app


def verify(fault, enabled):
    client = create_app(fault if enabled else None).test_client()

    def call(method, path, status=200, **data):
        response = client.open(path, method=method, **({"json": data} if method == "POST" else {}))
        assert response.status_code == status, (fault, enabled, path, response.status_code)
        return response.get_json()

    def add(kind, **data):
        return call("POST", "/" + kind, 201, **data)

    def loan(user, book):
        return add("loans", userId=user, bookId=book)

    def hold(user, book):
        return add("holds", userId=user, bookId=book)

    call("POST", "/reset")
    u, v, w = [add("users", name=name)["id"] for name in ("U", "V", "W")]
    a, b = [add("books", title=name)["id"] for name in ("A", "B")]
    if fault == "F1":
        hold(u, a)
        call("POST", "/loans", 400 if enabled else 201, userId=u, bookId=b)
        assert bool(call("GET", "/loans")) == (not enabled)
    elif fault == "F2":
        loan(v, a)
        loan(w, b)
        assert hold(u, a)["bookId"] == a
        created = hold(u, b)
        assert created["bookId"] == (a if enabled else b)
        assert created in call("GET", "/holds")
    elif fault == "F3":
        loan(u, a)
        first, second = hold(v, a), hold(w, a)
        call("DELETE", f"/loans/{u}/{a}")
        call("DELETE", f'/holds/{first["id"]}')
        assert call("GET", "/holds") == ([first, second] if enabled else [second])
    elif fault == "F4":
        loan(u, a)
        call("DELETE", f"/loans/{u}/{a}")
        current = loan(v, a)
        assert call("GET", f"/loans?userId={v}&bookId={a}") == [current]
        assert call("GET", f"/loans?userId={u}&bookId={a}") == ([current] if enabled else [])
        call("POST", "/reset")
        assert call("GET", "/loans") == []
    elif fault == "F5":
        hold(u, a)
        created = hold(v, a)
        assert created["userId"] == (u if enabled else v)
        assert {"id": created["id"], "bookId": a, "userId": v} in call("GET", "/holds")
    elif fault == "F6":
        loan(u, b)
        call("DELETE", f"/loans/{u}/{b}")
        loan(u, a)
        hold(v, a)
        call("DELETE", f"/loans/{u}/{a}", 500 if enabled else 200)
        assert call("GET", "/loans") == []


if __name__ == "__main__":
    for fault_id in FAULTS:
        verify(fault_id, enabled=False)
        verify(fault_id, enabled=True)
        print(f"{fault_id}: fault witness and baseline passed")
