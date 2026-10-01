"""`sharing.who-did-it` (#5319): every edit to a shared library says who made it, and where.

Found on the 2026-10-01 two-Mac run with Multi-user off: the host's own note was audited as
`system` and the paired Mac's as `owner`, with nothing naming the Mac. If these break, a shared
library's history can no longer tell the host's edits from a paired device's.
"""

from __future__ import annotations

import hashlib
import importlib
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero_server.api.auth import initialize_token
from fichero_server.security import accounts
from fichero_server.api.routes.auth import pairing
from fichero_server.models import ActionAudit


@pytest.fixture(params=["0", "1"], ids=["multiuser-off", "multiuser-on"])
def shared_library(request, test_package, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", request.param)
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.main import get_library_database, get_library_database_for_write
    from fichero_server.api.routes.ai.providers import get_app_database
    from fichero_server.db import db_manager

    library_db = db_manager.get_database(test_package)
    app_db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("password"), is_owner=True
    )
    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[get_library_database] = lambda: library_db
    api_main.app.dependency_overrides[get_library_database_for_write] = lambda: library_db
    headers = {"X-Fichero-Library-Path": quote(str(test_package), safe="/")}
    host = TestClient(api_main.app, client=("testclient", 5000), headers=headers)
    remote = TestClient(
        api_main.app, base_url="https://paired.example", client=("198.51.100.20", 5000), headers=headers
    )
    try:
        yield host, remote, library_db
    finally:
        api_main.app.dependency_overrides.clear()
        pairing._PAIRING_CODES.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def _note_audit(db, body: str) -> ActionAudit:
    digest = hashlib.sha256(body.encode()).hexdigest()
    rows = [r for r in db.query(ActionAudit) if r.action_name == "note.create" and r.params.get("body_sha256") == digest]
    assert len(rows) == 1, [(r.action_name, r.actor) for r in db.query(ActionAudit)]
    return rows[0]


def test_the_host_and_a_paired_mac_are_told_apart_in_the_audit(shared_library):
    host, remote, db = shared_library
    bootstrap = {"Authorization": f"Bearer {initialize_token()}"}
    # With Multi-user on, a pairing code needs a signed-in person (`sharing.multiuser-pairing`).
    login = host.post("/api/auth/login", json={"username": "owner", "password": "password"})
    pairer = {"Authorization": f"Bearer {login.json()['session_token']}"} if login.status_code == 200 else bootstrap

    assert host.post("/api/notes", json={"body": "made on the host"}, headers=bootstrap).status_code == 200

    code = host.post("/api/pair/code", headers=pairer)
    assert code.status_code == 200, code.text
    paired = remote.post("/api/pair", json={"code": code.json()["code"], "device_name": "MBP-test"})
    assert paired.status_code == 200, paired.text
    device = {"Authorization": f"Bearer {paired.json()['device_token']}"}
    assert remote.post("/api/notes", json={"body": "made on the MBP"}, headers=device).status_code == 200

    on_host = _note_audit(db, "made on the host")
    on_mbp = _note_audit(db, "made on the MBP")
    # Loopback + the bootstrap token is the owner (ruled), never an anonymous `system`.
    assert on_host.actor == "owner"
    assert on_host.device is None
    # The device is the owner's (Multi-user off: it acts as the owner), and the row names it.
    assert on_mbp.actor == "owner"
    assert on_mbp.device == {"id": paired.json()["device_id"], "name": "MBP-test"}
