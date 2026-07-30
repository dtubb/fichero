from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import importlib

import pytest
from fastapi.testclient import TestClient

from fichero_server.security import accounts
from fichero_server.api.auth import initialize_token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def _client(app_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.routes.ai.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app) as client:
        yield client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def test_list_sessions_as_owner_sees_all_users(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    viewer = app_db.create_user(
        username="viewer",
        display_name="Viewer",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    owner_token = accounts.new_session_token()
    app_db.create_session(
        user_id=owner.id,
        token_hash=accounts.hash_token(owner_token),
        device_label="Owner Mac",
        ttl=timedelta(days=1),
    )
    app_db.create_session(
        user_id=viewer.id,
        token_hash=accounts.hash_token(accounts.new_session_token()),
        device_label="Viewer iPad",
        ttl=timedelta(days=1),
    )

    with _client(app_db, monkeypatch) as client:
        response = client.get("/api/auth/sessions", headers=_bearer(owner_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert {item["user"]["username"] for item in payload["items"]} == {"owner", "viewer"}
    assert {item["device_label"] for item in payload["items"]} == {"Owner Mac", "Viewer iPad"}


def test_list_sessions_as_bootstrap_sees_all_users(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    app_db.create_session(
        user_id=owner.id,
        token_hash=accounts.hash_token(accounts.new_session_token()),
        device_label="Owner Mac",
        ttl=timedelta(days=1),
    )

    with _client(app_db, monkeypatch) as client:
        response = client.get("/api/auth/sessions", headers=_bearer(initialize_token()))

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_list_sessions_as_user_sees_only_own_rows(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    alice = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    bob = app_db.create_user(
        username="bob",
        display_name="Bob",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    alice_token = accounts.new_session_token()
    app_db.create_session(
        user_id=alice.id,
        token_hash=accounts.hash_token(alice_token),
        device_label="Alice Mac",
        ttl=timedelta(days=1),
    )
    app_db.create_session(
        user_id=bob.id,
        token_hash=accounts.hash_token(accounts.new_session_token()),
        device_label="Bob iPad",
        ttl=timedelta(days=1),
    )

    alice_sessions = app_db.list_sessions(user_id=alice.id)

    with _client(app_db, monkeypatch) as client:
        response = client.get("/api/auth/sessions", headers=_bearer(alice_token))

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": alice_sessions[0].id,
                "user": {
                    "id": alice.id,
                    "username": "alice",
                    "display_name": "Alice",
                },
                "device_label": "Alice Mac",
                "created": alice_sessions[0].created_at.isoformat(),
                "last_seen": alice_sessions[0].last_seen_at.isoformat(),
            }
        ],
        "count": 1,
    }


def test_list_sessions_returns_empty_for_user_with_zero_grants(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    app_db.create_device(
        name="Alice iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
        ttl=timedelta(days=1),
    )

    with _client(app_db, monkeypatch) as client:
        response = client.get("/api/auth/sessions", headers=_bearer(raw_token))

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


def test_user_a_never_sees_user_b_session(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    alice = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    bob = app_db.create_user(
        username="bob",
        display_name="Bob",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    alice_token = accounts.new_session_token()
    app_db.create_session(
        user_id=alice.id,
        token_hash=accounts.hash_token(alice_token),
        device_label="Alice Mac",
        ttl=timedelta(days=1),
    )
    bob_session = app_db.create_session(
        user_id=bob.id,
        token_hash=accounts.hash_token(accounts.new_session_token()),
        device_label="Bob iPad",
        ttl=timedelta(days=1),
    )

    with _client(app_db, monkeypatch) as client:
        response = client.get("/api/auth/sessions", headers=_bearer(alice_token))

    assert response.status_code == 200
    assert all(item["id"] != bob_session.id for item in response.json()["items"])


def test_revoke_session_invalidates_follow_up_request(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    session = app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
        device_label="Alice Mac",
        ttl=timedelta(days=1),
    )

    with _client(app_db, monkeypatch) as client:
        revoke = client.post(
            f"/api/auth/sessions/{session.id}/revoke",
            headers=_bearer(raw_token),
        )
        follow_up = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert revoke.status_code == 200
    assert follow_up.status_code == 401


def test_expired_session_returns_structured_code(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
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
        device_label="Alice Mac",
        ttl=timedelta(seconds=-1),
    )

    with _client(app_db, monkeypatch) as client:
        response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 401
    assert response.json()["detail"] == "missing or invalid Authorization header"
    assert response.json()["code"] == "session_expired"


def test_valid_session_stays_200(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
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
        device_label="Alice Mac",
        ttl=timedelta(days=1),
    )

    with _client(app_db, monkeypatch) as client:
        response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 200
