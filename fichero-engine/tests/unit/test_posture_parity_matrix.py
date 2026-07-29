from __future__ import annotations

import importlib
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fichero.api.auth import attach_auth_middleware, initialize_token
from fichero.security.multiuser import multiuser_enabled


@pytest.fixture(autouse=True)
def _restore_api_main_after_reload():
    """Undo `_main_client`'s auth-enabled reload of fichero.api.main (#4243).

    `_main_client` reloads the module with FICHERO_DISABLE_AUTH=0 and, before
    this fixture, nothing reloaded it back — every later suite in the process
    then built TestClients against an auth-enforcing app and failed with 401s
    (26 order-dependent failures in the full run, all green standalone).
    monkeypatch restores the ENV, but an import-time decision needs the module
    itself restored.
    """
    yield
    import fichero.api.main as api_main

    # Unconditional, with the env pinned for the reload: teardown ordering vs
    # monkeypatch is not guaranteed, and the suite-wide default (conftest) is
    # auth disabled — rebuild the module in that state, whatever this test did.
    prior = os.environ.get("FICHERO_DISABLE_AUTH")
    os.environ["FICHERO_DISABLE_AUTH"] = "1"
    try:
        importlib.reload(api_main)
    finally:
        if prior is None:
            os.environ.pop("FICHERO_DISABLE_AUTH", None)
        else:
            os.environ["FICHERO_DISABLE_AUTH"] = prior


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _auth_probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/private")
    async def private():
        return {"private": True}

    attach_auth_middleware(app, "test-token")
    return app


def _main_client(app_db, monkeypatch, client_addr: tuple[str, int] = ("testclient", 50000)):
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero.api.routes import auth_accounts, pairing
    from fichero.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[auth_accounts.get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[pairing.get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    client = TestClient(api_main.app, client=client_addr)
    return client, api_main


def test_single_user_loopback_bootstrap_and_owner_pairing_keep_working(
    app_db, monkeypatch
) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")

    bootstrap = TestClient(_auth_probe_app())
    private = bootstrap.get("/api/private", headers={"Authorization": "Bearer test-token"})
    assert private.status_code == 200

    client, api_main = _main_client(app_db, monkeypatch)
    try:
        pair_code = client.post(
            "/api/pair/code",
            headers=_bearer(initialize_token()),
        )
        assert pair_code.status_code == 200

        paired = client.post(
            "/api/pair",
            json={"code": pair_code.json()["code"], "device_name": "Owner iPad"},
        )
        assert paired.status_code == 200

        device_private = bootstrap.get(
            "/api/private",
            headers=_bearer(paired.json()["device_token"]),
            cookies=client.cookies,
        )
        assert device_private.status_code == 200
    finally:
        api_main.app.dependency_overrides.clear()
        client.close()


def test_single_user_non_loopback_bootstrap_stays_401(monkeypatch) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")

    client = TestClient(_auth_probe_app(), client=("192.0.2.10", 5000))
    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "loopback only"}


def test_transport_signals_do_not_auto_enable_multiuser() -> None:
    assert (
        multiuser_enabled(
            {
                "FICHERO_PUBLIC_BASE_URL": "https://fichero.tail123.ts.net",
                "FICHERO_ENABLE_BONJOUR": "1",
                "FICHERO_BIND_HOST": "100.64.0.10",
                "FICHERO_REMOTE_BACKEND_BIND_HOST": "100.64.0.11",
            }
        )
        is False
    )


def test_multiuser_loopback_keeps_bootstrap_owner_and_login_available(
    app_db, monkeypatch
) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")

    bootstrap = TestClient(_auth_probe_app())
    private = bootstrap.get("/api/private", headers={"Authorization": "Bearer test-token"})
    assert private.status_code == 200

    client, api_main = _main_client(app_db, monkeypatch)
    try:
        create_owner = client.post(
            "/api/users",
            headers=_bearer(initialize_token()),
            json={
                "username": "owner",
                "display_name": "Owner",
                "password": "password",
                "is_owner": False,
            },
        )
        assert create_owner.status_code == 200

        login = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "password"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["username"] == "owner"
    finally:
        api_main.app.dependency_overrides.clear()
        client.close()
