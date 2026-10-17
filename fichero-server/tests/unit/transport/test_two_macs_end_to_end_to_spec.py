"""library-sharing: sharing.two-macs-end-to-end (#5049), the in-process half.

One engine, two clients: A (loopback, the owner) and B (a paired device over https). Pair with the
one-time code, B reaches A's library, an edit B made and then A changed makes B's next edit a 409
(shared editing, not last-save-wins), and when A removes B's device B is refused at once. The real run
on two Macs is `docs/contributor_manual/testing/sharing-two-mac-checklist.md` on the M4.
"""

from __future__ import annotations

import importlib
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero_server.security import accounts
from fichero_server.api.routes.auth import pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def two_macs(test_package, app_db, monkeypatch):
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.main import get_library_database, get_library_database_for_write
    from fichero_server.api.routes.entity.entities import _digest_library_database
    from fichero_server.api.routes.ai.providers import get_app_database
    from fichero_server.db import db_manager

    library_db = db_manager.get_database(test_package)
    overrides = api_main.app.dependency_overrides
    overrides[get_app_database] = lambda: app_db
    overrides[_digest_library_database] = lambda: library_db
    overrides[get_library_database] = lambda: library_db
    overrides[get_library_database_for_write] = lambda: library_db
    headers = {"X-Fichero-Library-Path": quote(str(test_package), safe="/")}

    def client(base_url, addr):
        return TestClient(api_main.app, base_url=base_url, client=addr, headers=headers)

    app_db.create_user(
        username="owner", display_name="Owner",
        password_hash=accounts.hash_password("password"), is_owner=True,
    )
    try:
        yield {
            "a": client("http://testserver", ("testclient", 5000)),
            "b": client("https://paired.example", ("198.51.100.20", 5000)),
        }
    finally:
        overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)
        pairing._PAIRING_CODES.clear()


def test_pair_open_edit_stale_and_revoke(two_macs):
    a, b = two_macs["a"], two_macs["b"]
    session = a.post("/api/auth/login", json={"username": "owner", "password": "password"}).json()["session_token"]
    code = a.post("/api/pair/code", headers=_bearer(session)).json()["code"]

    paired = b.post("/api/pair", json={"code": code, "device_name": "Mac B"})
    assert paired.status_code == 200
    token = paired.json()["device_token"]
    device_id = next(d["id"] for d in a.get("/api/pair/devices", headers=_bearer(session)).json()["items"])

    # B opens A's library
    assert b.get("/api/authz/libraries", headers=_bearer(token)).status_code == 200

    # B writes a note; A edits it; B's next edit, made against the version B read, is refused 409
    made = b.post("/api/notes", json={"body": "from B"}, headers=_bearer(token))
    assert made.status_code in (200, 201), made.text
    note = made.json()
    assert a.patch(f"/api/notes/{note['id']}", json={"body": "A changed it"}, headers=_bearer(session)).status_code == 200
    stale = b.patch(
        f"/api/notes/{note['id']}",
        json={"body": "B edits the old text", "expected_updated_at": note["updated_at"]},
        headers=_bearer(token),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_body"] == "A changed it"

    # A removes B: B is refused on the next call
    assert a.post(f"/api/pair/devices/{device_id}/revoke", headers=_bearer(session)).status_code == 200
    assert b.get("/api/authz/libraries", headers=_bearer(token)).status_code == 401
