from __future__ import annotations

from datetime import datetime, timedelta
import importlib

from fastapi.testclient import TestClient
import pytest
from fichero_server.security import accounts
import fichero_server.api.auth as api_auth


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_multiuser(monkeypatch) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")


def _make_client(app_db):
    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    return api_main


def _cleanup_client(api_main) -> None:
    api_main.app.dependency_overrides.clear()
    importlib.reload(api_main)


@pytest.fixture
def client(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    api_main = _make_client(app_db)
    with TestClient(api_main.app) as test_client:
        yield test_client
    _cleanup_client(api_main)
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")


def test_session_sliding_expiry_extends_within_refresh_window(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    monkeypatch.setenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", "300")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    session = app_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        device_label="test-device",
        ttl=timedelta(days=30),
    )
    frozen_now = session.expires_at - timedelta(seconds=60)
    app_db.touch_session(token_hash, when=frozen_now - timedelta(minutes=5))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz is None else tz.fromutc(frozen_now.replace(tzinfo=tz))

    monkeypatch.setattr(api_auth, "datetime", FrozenDateTime)

    response = client.get("/api/auth/me", headers=_bearer(raw_token))
    updated = app_db.get_session_by_token_hash(token_hash)

    assert response.status_code == 200
    assert updated.expires_at == frozen_now + timedelta(days=30)
    assert updated.last_seen_at == frozen_now


def test_session_sliding_expiry_respects_last_seen_throttle(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    monkeypatch.setenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", "300")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    session = app_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        device_label="test-device",
        ttl=timedelta(days=30),
    )
    frozen_now = session.expires_at - timedelta(seconds=60)
    app_db.touch_session(token_hash, when=frozen_now - timedelta(seconds=30))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz is None else tz.fromutc(frozen_now.replace(tzinfo=tz))

    monkeypatch.setattr(api_auth, "datetime", FrozenDateTime)

    response = client.get("/api/auth/me", headers=_bearer(raw_token))
    updated = app_db.get_session_by_token_hash(token_hash)

    assert response.status_code == 200
    assert updated.expires_at == session.expires_at
    assert updated.last_seen_at == frozen_now - timedelta(seconds=30)


def test_session_sliding_expiry_does_not_extend_outside_refresh_window(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    monkeypatch.setenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", "300")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    session = app_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        device_label="test-device",
        ttl=timedelta(days=30),
    )
    frozen_now = session.expires_at - timedelta(minutes=10)
    app_db.touch_session(token_hash, when=frozen_now - timedelta(minutes=5))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz is None else tz.fromutc(frozen_now.replace(tzinfo=tz))

    monkeypatch.setattr(api_auth, "datetime", FrozenDateTime)

    response = client.get("/api/auth/me", headers=_bearer(raw_token))
    updated = app_db.get_session_by_token_hash(token_hash)

    assert response.status_code == 200
    assert updated.expires_at == session.expires_at
    assert updated.last_seen_at == frozen_now
