from __future__ import annotations

from datetime import datetime, timedelta
import importlib

import pytest
from fastapi.testclient import TestClient

from fichero import accounts
from fichero.actions import registry
from fichero.api.auth import initialize_token
from fichero.api.routes import pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_multiuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")


def _disable_multiuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)


@pytest.fixture(autouse=True)
def clear_pairing_state():
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    yield
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()


@pytest.fixture
def client(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app) as test_client:
        yield test_client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def test_bootstrap_first_user_creates_owner(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    response = client.post(
        "/api/users",
        headers=_bearer(initialize_token()),
        json={
            "username": "owner",
            "display_name": "Owner",
            "password": "password-1",
            "is_owner": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "owner"
    assert data["is_owner"] is True
    assert app_db.get_user_by_username("owner").is_owner is True


def test_login_success_returns_session_and_me(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("correct horse battery staple"),
        is_owner=True,
    )

    response = client.post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "correct horse battery staple",
            "device_label": "MacBook Pro",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["username"] == "alice"
    assert payload["session_token"]

    me = client.get("/api/auth/me", headers=_bearer(payload["session_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_login_unknown_user_and_bad_password_both_return_401(
    client, app_db, monkeypatch
):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("correct horse battery staple"),
        is_owner=True,
    )

    missing = client.post(
        "/api/auth/login",
        json={"username": "missing", "password": "whatever"},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("alice", "wrong-password"),
        ("missing", "anything"),
    ],
)
def test_login_rejects_bad_credentials(client, app_db, monkeypatch, username, password):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("correct horse battery staple"),
        is_owner=True,
    )

    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )

    assert response.status_code == 401


def test_expired_session_is_rejected(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
        device_label="test-device",
        ttl=timedelta(seconds=-1),
    )

    response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 401


def test_revoked_session_is_rejected(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    app_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        device_label="test-device",
        ttl=timedelta(days=1),
    )
    app_db.revoke_session(token_hash)

    response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 401


def test_multiple_concurrent_sessions_per_user(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )

    first = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password"},
    )
    second = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password", "device_label": "iPad"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_token = first.json()["session_token"]
    second_token = second.json()["session_token"]
    assert first_token != second_token

    assert client.get("/api/auth/me", headers=_bearer(first_token)).status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(second_token)).status_code == 200


def test_owner_only_admin_rejects_non_owner(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    app_db.create_user(
        username="member",
        display_name="Member",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )

    login = client.post(
        "/api/auth/login",
        json={"username": "member", "password": "password"},
    )
    assert login.status_code == 200

    response = client.get(
        "/api/users",
        headers=_bearer(login.json()["session_token"]),
    )

    assert response.status_code == 403


def test_multiuser_flag_off_leaves_shared_secret_behavior_unchanged(
    client,
    app_db,
    monkeypatch,
):
    _disable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
        device_label="test-device",
        ttl=timedelta(days=1),
    )

    login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password"},
    )
    assert login.status_code == 404

    session_auth = client.get("/api/providers", headers=_bearer(raw_token))
    assert session_auth.status_code == 401

    shared_secret = client.get("/api/providers", headers=_bearer(initialize_token()))
    assert shared_secret.status_code == 200


def test_pairing_valid_code_returns_device_token_that_authenticates(
    client,
    app_db,
    monkeypatch,
):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    session_token = login.json()["session_token"]

    code_response = client.post("/api/pair/code", headers=_bearer(session_token))
    assert code_response.status_code == 200

    pair_response = client.post(
        "/api/pair",
        json={
            "code": code_response.json()["code"],
            "device_name": "Alice iPad",
        },
    )

    assert pair_response.status_code == 200
    device_token = pair_response.json()["device_token"]
    me = client.get("/api/auth/me", headers=_bearer(device_token))
    assert me.status_code == 200
    assert me.json()["username"] == "owner"


def test_revoked_device_token_is_rejected(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_token = accounts.new_session_token()
    device = app_db.create_device(
        name="Alice iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
    )
    app_db.revoke_device(device.id)

    response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 401


def test_pairing_rejects_reused_and_expired_codes(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    session_token = login.json()["session_token"]

    code = client.post("/api/pair/code", headers=_bearer(session_token)).json()["code"]
    first = client.post(
        "/api/pair",
        json={"code": code, "device_name": "Alice iPad"},
    )
    reused = client.post(
        "/api/pair",
        json={"code": code, "device_name": "Alice iPad"},
    )

    expired_code = client.post(
        "/api/pair/code",
        headers=_bearer(session_token),
    ).json()["code"]
    pairing._PAIRING_CODES[expired_code].expires_at = datetime.now() - timedelta(
        seconds=1
    )
    expired = client.post(
        "/api/pair",
        json={"code": expired_code, "device_name": "Alice iPad"},
    )

    assert first.status_code == 200
    assert reused.status_code == 401
    assert expired.status_code == 401


def test_pairing_is_rate_limited(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    statuses = [
        client.post(
            "/api/pair",
            json={"code": "NOPE", "device_name": "Alice iPad"},
        ).status_code
        for _ in range(pairing.PAIRING_RATE_LIMIT + 1)
    ]

    assert statuses[:-1] == [401] * pairing.PAIRING_RATE_LIMIT
    assert statuses[-1] == 429


def test_pairing_attempt_pruning_removes_stale_hosts():
    now = datetime.now()
    stale = now - pairing.PAIRING_RATE_WINDOW - timedelta(seconds=1)
    current = now - timedelta(seconds=1)
    pairing._PAIRING_ATTEMPTS.update(
        {
            "stale.example": [stale],
            "mixed.example": [stale, current],
            "current.example": [current],
        }
    )

    pairing._prune_pairing_attempts(now)

    assert "stale.example" not in pairing._PAIRING_ATTEMPTS
    assert pairing._PAIRING_ATTEMPTS["mixed.example"] == [current]
    assert pairing._PAIRING_ATTEMPTS["current.example"] == [current]


def test_device_actions_are_registered():
    assert "device.list" in registry.names()
    assert "device.revoke" in registry.names()
