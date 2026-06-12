from __future__ import annotations

from datetime import datetime, timedelta
import importlib

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from fichero import accounts
from fichero.api.auth import attach_auth_middleware
from fichero.api.routes import pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_pairing_state():
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    yield
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()


@pytest.fixture
def pairing_client(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    import fichero.api.main as api_main
    from fichero.api.routes import auth_accounts
    from fichero.api.routes.providers import get_app_database as providers_app_db

    api_main = importlib.reload(api_main)
    api_main.app.dependency_overrides[auth_accounts.get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[pairing.get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[providers_app_db] = lambda: app_db
    with TestClient(api_main.app) as client:
        yield client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def _create_owner(app_db, *, active: bool = True):
    return app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
        active=active,
    )


def _owner_session_token(client: TestClient, app_db) -> str:
    _create_owner(app_db)
    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    assert response.status_code == 200
    return response.json()["session_token"]


def test_pairing_rejects_replay_after_code_is_used(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)
    code_response = pairing_client.post("/api/pair/code", headers=_bearer(session_token))
    assert code_response.status_code == 200
    code = code_response.json()["code"]

    first = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Owner iPad"},
    )
    replay = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Replay iPad"},
    )

    assert first.status_code == 200
    assert replay.status_code == 401


def test_pairing_rejects_code_after_ttl_prune(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)
    code = pairing_client.post(
        "/api/pair/code",
        headers=_bearer(session_token),
    ).json()["code"]
    pairing._PAIRING_CODES[code].expires_at = datetime.now() - timedelta(seconds=1)
    pairing._prune_pairing_codes(datetime.now())

    response = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Expired iPad"},
    )

    assert response.status_code == 401


def test_pairing_rate_limiter_returns_429_on_sixth_attempt(pairing_client):
    statuses = [
        pairing_client.post(
            "/api/pair",
            json={"code": "WRONG-CODE", "device_name": "Attacker"},
        ).status_code
        for _ in range(pairing.PAIRING_RATE_LIMIT + 1)
    ]

    assert statuses[: pairing.PAIRING_RATE_LIMIT] == [401] * pairing.PAIRING_RATE_LIMIT
    assert statuses[pairing.PAIRING_RATE_LIMIT] == 429


def test_pairing_rejects_code_for_deactivated_user(pairing_client, app_db):
    owner = _create_owner(app_db)
    code = "ABCD-EFGH"
    pairing._PAIRING_CODES[code] = pairing._PairingCode(
        code=code,
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=60),
    )
    app_db.set_active(owner.id, False)

    response = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Inactive Owner iPad"},
    )

    assert response.status_code == 401
    assert code not in pairing._PAIRING_CODES


def _auth_fork_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/private")
    async def private(request: Request):
        user = getattr(request.state, "user", None)
        return {
            "username": getattr(user, "username", None),
            "session": hasattr(request.state, "session"),
            "device": hasattr(request.state, "device"),
            "bootstrap": getattr(request.state, "bootstrap_auth", None),
        }

    attach_auth_middleware(app, "bootstrap-secret")
    return app


def test_auth_fork_accepts_valid_session_and_valid_device(monkeypatch, app_db):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    session_token = accounts.new_session_token()
    device_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(session_token),
        device_label="Mac",
        ttl=timedelta(days=1),
    )
    app_db.create_device(
        name="iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(device_token),
        ttl=timedelta(days=1),
    )
    client = TestClient(_auth_fork_app(), client=("192.0.2.10", 5000))

    session_response = client.get("/api/private", headers=_bearer(session_token))
    device_response = client.get("/api/private", headers=_bearer(device_token))

    assert session_response.status_code == 200
    assert session_response.json() == {
        "username": "alice",
        "session": True,
        "device": False,
        "bootstrap": False,
    }
    assert device_response.status_code == 200
    assert device_response.json() == {
        "username": "alice",
        "session": False,
        "device": True,
        "bootstrap": False,
    }


@pytest.mark.parametrize(
    "token_kind",
    ["revoked_device", "expired_session", "expired_device", "garbage"],
)
def test_auth_fork_rejects_invalid_token_matrix(monkeypatch, app_db, token_kind):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username=f"user-{token_kind}",
        display_name="User",
        password_hash=accounts.hash_password("password"),
    )
    token = accounts.new_session_token()
    if token_kind == "revoked_device":
        device = app_db.create_device(
            name="Revoked iPad",
            user_id=user.id,
            token_hash=accounts.hash_token(token),
            ttl=timedelta(days=1),
        )
        app_db.revoke_device(device.id)
    elif token_kind == "expired_session":
        app_db.create_session(
            user_id=user.id,
            token_hash=accounts.hash_token(token),
            device_label="Expired Mac",
            ttl=timedelta(seconds=-1),
        )
    elif token_kind == "expired_device":
        app_db.create_device(
            name="Expired iPad",
            user_id=user.id,
            token_hash=accounts.hash_token(token),
            ttl=timedelta(seconds=-1),
        )
    else:
        token = "not-a-real-token"
    client = TestClient(_auth_fork_app(), client=("192.0.2.10", 5000))

    response = client.get("/api/private", headers=_bearer(token))

    assert response.status_code == 401


def test_auth_fork_rejects_bootstrap_secret_from_non_loopback(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_auth_fork_app(), client=("192.0.2.10", 5000))

    response = client.get("/api/private", headers=_bearer("bootstrap-secret"))

    assert response.status_code == 401
