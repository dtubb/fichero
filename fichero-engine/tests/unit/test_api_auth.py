from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fichero import accounts
from fichero.api.auth import attach_auth_middleware, initialize_token
from fichero.api.routes import pairing


def _app_with_auth() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/docs/")
    async def docs_index():
        return {"docs": True}

    @app.get("/api/private")
    async def private():
        return {"private": True}

    attach_auth_middleware(app, "test-token")
    return app


def test_docs_subpath_is_unauthenticated():
    client = TestClient(_app_with_auth())
    response = client.get("/docs/")
    assert response.status_code == 200
    assert response.json() == {"docs": True}


def test_private_endpoint_still_requires_bearer_token():
    client = TestClient(_app_with_auth())
    no_auth = client.get("/api/private")
    assert no_auth.status_code == 401

    authed = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )
    assert authed.status_code == 200


def test_bootstrap_secret_rejects_non_loopback_multiuser(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_app_with_auth(), client=("192.0.2.10", 5000))

    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 401


def test_bootstrap_secret_accepts_loopback_without_forwarding(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_app_with_auth())

    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200


def test_bootstrap_secret_rejects_forwarded_loopback_multiuser(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_app_with_auth())

    response = client.get(
        "/api/private",
        headers={
            "Authorization": "Bearer test-token",
            "X-Forwarded-For": "192.0.2.10",
        },
    )

    assert response.status_code == 401


def test_non_loopback_device_token_authenticates_multiuser(monkeypatch, app_db):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_token = accounts.new_session_token()
    app_db.create_device(
        name="Alice iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
    )
    client = TestClient(_app_with_auth(), client=("192.0.2.10", 5000))

    response = client.get(
        "/api/private",
        headers={"Authorization": f"Bearer {raw_token}"},
    )

    assert response.status_code == 200


def test_non_loopback_device_token_authenticates_single_user(monkeypatch, app_db):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    raw_token = accounts.new_session_token()
    owner = pairing._single_user_pairing_owner(app_db)
    app_db.create_device(
        name="Alice iPad",
        user_id=owner.id,
        token_hash=accounts.hash_token(raw_token),
    )
    client = TestClient(_app_with_auth(), client=("192.0.2.10", 5000))

    response = client.get(
        "/api/private",
        headers={"Authorization": f"Bearer {raw_token}"},
    )

    assert response.status_code == 200


def test_initialize_token_rotates_when_file_contains_device_token(monkeypatch, tmp_path, app_db):
    token_path = tmp_path / ".api-key"
    monkeypatch.setattr("fichero.api.auth._token_file_path", lambda: token_path)

    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_device_token = accounts.new_session_token()
    app_db.create_device(
        name="Test iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_device_token),
    )
    token_path.write_text(raw_device_token)

    rotated = initialize_token()

    assert rotated != raw_device_token
    assert token_path.read_text() == rotated


def test_initialize_token_rotates_when_file_contains_session_token(
    monkeypatch, tmp_path, app_db
):
    token_path = tmp_path / ".api-key"
    monkeypatch.setattr("fichero.api.auth._token_file_path", lambda: token_path)

    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_session_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_session_token),
        device_label="Mac",
        ttl=timedelta(days=1),
    )
    token_path.write_text(raw_session_token)

    rotated = initialize_token()

    assert rotated != raw_session_token
    assert token_path.read_text() == rotated
