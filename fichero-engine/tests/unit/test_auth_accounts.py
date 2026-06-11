from __future__ import annotations

from datetime import timedelta
import importlib

import pytest
from fastapi.testclient import TestClient

from fichero import accounts
from fichero.api.auth import initialize_token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_multiuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")


def _disable_multiuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)


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
