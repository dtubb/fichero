"""#2407 regression guard: first authenticated device call must not need a retry.

The report was "403 on first call, 200 on retry" from iPad across a mixed burst
of app-wide and library routes. Pin the backend contract directly: a freshly
paired device token, no pre-seeded ACL rows, and the FIRST request to each
route succeeds.
"""

from __future__ import annotations

import importlib
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero.security import accounts
from fichero.security import authz
from fichero.api.routes import pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def paired_device_client(test_package, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()

    import fichero.api.main as api_main
    from fichero.api.routes.providers import get_app_database

    api_main = importlib.reload(api_main)
    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    client = TestClient(
        api_main.app,
        headers={"X-Fichero-Library-Path": quote(str(test_package), safe="/")},
    )

    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    normalized_path = authz.normalize_library_path(test_package)
    assert normalized_path is not None
    assert app_db.list_library_roles(normalized_path) == []

    login = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    assert login.status_code == 200
    session_token = login.json()["session_token"]
    code_response = client.post("/api/pair/code", headers=_bearer(session_token))
    assert code_response.status_code == 200
    pair_response = client.post(
        "/api/pair",
        json={
            "code": code_response.json()["code"],
            "device_name": "First-call iPad",
        },
    )
    assert pair_response.status_code == 200
    device_token = pair_response.json()["device_token"]

    try:
        yield client, device_token, normalized_path, owner
    finally:
        client.close()
        api_main.app.dependency_overrides.clear()
        pairing._PAIRING_CODES.clear()
        pairing._PAIRING_ATTEMPTS.clear()
        pairing._PAIRING_RENEW_ATTEMPTS.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


@pytest.mark.parametrize(
    ("path", "expects_owner_backfill"),
    [
        ("/api/chains?limit=50", False),
        ("/api/authz/libraries", False),
        ("/api/documents?offset=0", True),
        ("/api/workflows/tools", False),
        ("/api/workflows", True),
        ("/api/chat/conversations", True),
        ("/api/search/saved", True),
    ],
)
def test_fresh_paired_device_first_call_never_403s(
    paired_device_client,
    app_db,
    path,
    expects_owner_backfill,
):
    client, device_token, normalized_path, owner = paired_device_client

    response = client.get(path, headers=_bearer(device_token))

    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    roles = app_db.list_library_roles(normalized_path)
    if expects_owner_backfill:
        assert [(row.user_id, row.role) for row in roles] == [(owner.id, authz.ROLE_OWNER)]
    else:
        assert roles == []
