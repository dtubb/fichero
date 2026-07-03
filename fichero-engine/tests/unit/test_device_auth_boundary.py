from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from fichero import accounts


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_client(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")

    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app) as client:
        yield client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def _create_owner(app_db):
    return app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )


def _owner_session_token(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    assert response.status_code == 200
    return response.json()["session_token"]


def _assert_no_secret_leak(response, *secrets: str) -> None:
    body = response.text
    for secret in secrets:
        if secret:
            assert secret not in body


def test_pair_code_rejects_missing_invalid_and_expired_tokens_without_secret_leak(
    auth_client, app_db
):
    _create_owner(app_db)
    expired_token = accounts.new_session_token()
    app_db.create_device(
        name="Expired iPad",
        user_id=app_db.get_user_by_username("owner").id,
        token_hash=accounts.hash_token(expired_token),
        ttl=timedelta(seconds=-1),
    )
    invalid_token = "not-a-real-token"

    missing = auth_client.post("/api/pair/code", headers={"Authorization": ""})
    invalid = auth_client.post("/api/pair/code", headers=_bearer(invalid_token))
    expired = auth_client.post("/api/pair/code", headers=_bearer(expired_token))

    for response, secret in [
        (missing, ""),
        (invalid, invalid_token),
        (expired, expired_token),
    ]:
        assert response.status_code == 401
        _assert_no_secret_leak(response, secret)


def test_pairing_owner_endpoints_reject_non_owner_session_scope_with_403(
    auth_client, app_db
):
    app_db.create_user(
        username="member",
        display_name="Member",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    login = auth_client.post(
        "/api/auth/login",
        json={"username": "member", "password": "password"},
    )
    assert login.status_code == 200
    session_token = login.json()["session_token"]

    code_response = auth_client.post("/api/pair/code", headers=_bearer(session_token))
    list_response = auth_client.get("/api/pair/devices", headers=_bearer(session_token))

    for response in [code_response, list_response]:
        assert response.status_code == 403
        assert response.json()["detail"] == "owner access required"
        _assert_no_secret_leak(response, session_token)


def test_pair_route_malformed_requests_stay_4xx_and_do_not_leak_secrets(
    auth_client, app_db
):
    _create_owner(app_db)
    session_token = _owner_session_token(auth_client)
    code = auth_client.post("/api/pair/code", headers=_bearer(session_token)).json()["code"]

    missing_field = auth_client.post("/api/pair", json={"code": code})
    malformed_json = auth_client.post(
        "/api/pair",
        content='{"code": "ABCD-EFGH",',
        headers={"Content-Type": "application/json"},
    )

    for response, secret in [
        (missing_field, code),
        (malformed_json, "ABCD-EFGH"),
    ]:
        assert 400 <= response.status_code < 500
        _assert_no_secret_leak(response, secret, session_token)
