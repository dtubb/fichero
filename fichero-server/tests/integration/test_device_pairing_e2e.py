from __future__ import annotations

import importlib
from datetime import timedelta
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero_server.security import accounts
from fichero_server.api.auth import initialize_token
from fichero_server.api.routes.auth import pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_pairing_state():
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()
    yield
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()


@pytest.fixture
def pairing_harness(test_package, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    monkeypatch.setenv("FICHERO_TAILNET_URL", "https://fichero-demo.ts.net")

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.main import get_library_database, get_library_database_for_write
    from fichero_server.api.routes.entity.entities import _digest_library_database
    from fichero_server.api.routes.ai.providers import get_app_database
    from fichero_server.db import db_manager

    library_db = db_manager.get_database(test_package)
    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[_digest_library_database] = lambda: library_db
    api_main.app.dependency_overrides[get_library_database] = lambda: library_db
    api_main.app.dependency_overrides[get_library_database_for_write] = lambda: library_db

    headers = {"X-Fichero-Library-Path": quote(str(test_package), safe="/")}

    def make_client(*, base_url: str = "http://testserver", client_addr=("testclient", 5000)):
        return TestClient(
            api_main.app,
            base_url=base_url,
            client=client_addr,
            headers=headers,
        )

    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )

    try:
        yield {
            "owner": owner,
            "local_client": make_client(),
            "remote_https_client": make_client(
                base_url="https://paired.example",
                client_addr=("198.51.100.20", 5000),
            ),
            "remote_http_client": make_client(
                base_url="http://paired.example",
                client_addr=("198.51.100.20", 5000),
            ),
            "app_db": app_db,
        }
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def test_device_pairing_e2e_remote_pair_can_browse_library(pairing_harness):
    local_client = pairing_harness["local_client"]
    remote_client = pairing_harness["remote_https_client"]

    login = local_client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    assert login.status_code == 200

    code_response = local_client.post(
        "/api/pair/code",
        headers=_bearer(login.json()["session_token"]),
    )
    assert code_response.status_code == 200
    assert code_response.json()["tailnet_url"] == "https://fichero-demo.ts.net"

    pair_response = remote_client.post(
        "/api/pair",
        json={
            "code": code_response.json()["code"],
            "device_name": "Daniel iPad",
        },
    )
    assert pair_response.status_code == 200
    device_token = pair_response.json()["device_token"]

    documents = remote_client.get(
        "/api/documents?offset=0",
        headers=_bearer(device_token),
    )
    identity = remote_client.get(
        "/api/auth/identity",
        headers=_bearer(device_token),
    )

    assert documents.status_code == 200
    assert identity.status_code == 200
    assert identity.json()["auth_kind"] == "device"
    assert identity.json()["user"]["username"] == "owner"


def test_device_pairing_e2e_rejects_remote_pairing_without_https(pairing_harness):
    local_client = pairing_harness["local_client"]
    remote_http_client = pairing_harness["remote_http_client"]

    login = local_client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    assert login.status_code == 200
    code = local_client.post(
        "/api/pair/code",
        headers=_bearer(login.json()["session_token"]),
    ).json()["code"]

    response = remote_http_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Daniel iPad"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "remote pairing requires https"}

    code_response = remote_http_client.post(
        "/api/pair/code",
        headers=_bearer(login.json()["session_token"]),
    )
    assert code_response.status_code == 400
    assert code_response.json() == {"detail": "remote pairing requires https"}


def test_device_pairing_e2e_rejects_remote_pairing_without_spki_pin(
    pairing_harness, monkeypatch
):
    local_client = pairing_harness["local_client"]
    remote_client = pairing_harness["remote_https_client"]
    monkeypatch.delenv("FICHERO_TLS_SPKI_HASH", raising=False)

    login = local_client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    assert login.status_code == 200
    code = local_client.post(
        "/api/pair/code",
        headers=_bearer(login.json()["session_token"]),
    ).json()["code"]

    response = remote_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Daniel iPad"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "remote pairing unavailable without configured SPKI pin"
    }

    code_response = remote_client.post(
        "/api/pair/code",
        headers=_bearer(login.json()["session_token"]),
    )
    assert code_response.status_code == 503
    assert code_response.json() == {
        "detail": "remote pairing unavailable without configured SPKI pin"
    }


def test_device_pairing_e2e_rejects_revoked_and_expired_device_tokens(pairing_harness):
    remote_client = pairing_harness["remote_https_client"]
    app_db = pairing_harness["app_db"]
    owner = pairing_harness["owner"]

    expired_token = accounts.new_session_token()
    app_db.create_device(
        name="Expired iPad",
        user_id=owner.id,
        token_hash=accounts.hash_token(expired_token),
        ttl=timedelta(seconds=-1),
    )
    revoked_token = accounts.new_session_token()
    revoked = app_db.create_device(
        name="Revoked iPad",
        user_id=owner.id,
        token_hash=accounts.hash_token(revoked_token),
        ttl=timedelta(days=1),
    )
    app_db.revoke_device(revoked.id)

    expired = remote_client.get("/api/documents?offset=0", headers=_bearer(expired_token))
    revoked_response = remote_client.get(
        "/api/documents?offset=0",
        headers=_bearer(revoked_token),
    )

    assert expired.status_code == 401
    assert revoked_response.status_code == 401


def test_device_pairing_e2e_rejects_non_loopback_bootstrap_on_remote_library_request(
    pairing_harness,
):
    remote_client = pairing_harness["remote_https_client"]

    response = remote_client.get(
        "/api/documents?offset=0",
        headers=_bearer(initialize_token()),
    )

    assert response.status_code == 401
