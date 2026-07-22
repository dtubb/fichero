from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from fichero.security import accounts
from fichero.api.auth import initialize_token
from fichero.models import Conversation


def _ensure_owner(app_db) -> None:
    if app_db.get_user_by_username("owner") is None:
        app_db.create_user(
            username="owner",
            display_name="Owner",
            password_hash=accounts.hash_password("password"),
            is_owner=True,
        )


@pytest.mark.parametrize(
    "path",
    [
        "/api/workflows",
        "/api/documents",
        "/api/chat/conversations",
        "/api/entities",
        "/api/claims",
    ],
)
def test_multiuser_bootstrap_owner_can_read_library_routes(client, app_db, monkeypatch, path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _ensure_owner(app_db)

    response = client.get(path)

    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"


def test_multiuser_bootstrap_owner_can_invoke_registry_writes_across_domains(
    client, db, app_db, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _ensure_owner(app_db)

    db.save(Conversation(id="conv-bootstrap", title="Bootstrap chat", messages=[]))
    payloads = [
        (
            "workflow.create",
            {
                "name": "Bootstrap workflow",
                "description": "owner invariant coverage",
                "nodes": [],
                "edges": [],
            },
        ),
        ("document.create", {"name": "Bootstrap doc"}),
        ("conversation.duplicate", {"conversation_id": "conv-bootstrap"}),
        ("entity.create", {"canonical_name": "Bootstrap entity"}),
        ("claim.create", {"text": "Bootstrap claim"}),
    ]

    for action_name, params in payloads:
        response = client.post(
            "/api/actions/invoke",
            json={"name": action_name, "params": params},
        )
        assert (
            response.status_code == 200
        ), f"{action_name} returned {response.status_code}: {response.text}"


def test_multiuser_loopback_bootstrap_identity_is_the_login_gate_contract(
    client, app_db, monkeypatch
):
    """The exact triple the Mac app's login gate reads (#3941).

    SessionStore.resolvePhase decides whether to show a sign-in wall from these
    three facts. Pin all of them together: each one alone looks like a different
    bug, and it was the *combination* that put a login wall in front of the Mac
    that owns the engine.

    ``user`` is null on purpose — the bootstrap credential carries no *session*
    user — which is why the gate must key off ``is_owner_access`` and NOT off
    ``user`` (#3819 tried the latter and could never fire here).
    """
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _ensure_owner(app_db)

    assert client.get("/api/auth/me").status_code == 401, (
        "/auth/me deliberately 401s the bootstrap credential: it reports the "
        "session user and bootstrap has none. A 401 here must NOT be read as "
        "'show a login wall' — see identity below."
    )

    identity = client.get("/api/auth/identity")

    assert identity.status_code == 200
    assert identity.json() == {
        "multiuser_enabled": True,
        "auth_kind": "bootstrap",
        "user": None,
        "is_owner_access": True,
    }


def test_non_loopback_bootstrap_secret_cannot_claim_owner_access(
    test_package, app_db, monkeypatch
):
    """is_owner_access is loopback-only — the Mac app's gate depends on it.

    The gate ungates the library whenever the engine reports is_owner_access
    (#3941), so a remote caller holding a leaked bootstrap secret must never be
    able to elicit that field. Bootstrap auth is rejected before identity runs.
    """
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    _ensure_owner(app_db)

    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    try:
        with TestClient(
            api_main.app,
            client=("192.0.2.10", 5000),
            headers={"X-Fichero-Library-Path": str(test_package)},
        ) as client:
            response = client.get(
                "/api/auth/identity",
                headers={"Authorization": f"Bearer {initialize_token()}"},
            )
            assert response.status_code == 401
            assert "is_owner_access" not in response.text
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def test_non_loopback_bootstrap_secret_cannot_invoke_registry_write(
    test_package, app_db, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    _ensure_owner(app_db)

    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    try:
        with TestClient(
            api_main.app,
            client=("192.0.2.10", 5000),
            headers={"X-Fichero-Library-Path": str(test_package)},
        ) as client:
            response = client.post(
                "/api/actions/invoke",
                headers={"Authorization": f"Bearer {initialize_token()}"},
                json={"name": "document.create", "params": {"name": "Remote Bootstrap Doc"}},
            )
            assert response.status_code == 401
            assert response.json() == {"detail": "bootstrap auth is loopback only"}
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def test_non_owner_session_and_device_registry_writes_stay_acl_checked(
    test_package, app_db, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    library_path = str(test_package)
    _ensure_owner(app_db)
    viewer = app_db.create_user(
        username="viewer",
        display_name="Viewer",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_device_token = accounts.new_session_token()
    app_db.create_device(
        name="Viewer iPad",
        user_id=viewer.id,
        token_hash=accounts.hash_token(raw_device_token),
    )

    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    try:
        with TestClient(
            api_main.app,
            headers={"X-Fichero-Library-Path": library_path},
        ) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "viewer", "password": "password"},
            )
            assert login.status_code == 200
            for auth_kind, token in (
                ("session", login.json()["session_token"]),
                ("device", raw_device_token),
            ):
                response = client.post(
                    "/api/actions/invoke",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"name": "document.create", "params": {"name": f"Denied {auth_kind} doc"}},
                )
                assert response.status_code == 403
                assert response.json() == {
                    "detail": "write access denied",
                    "code": "library_access_denied",
                    "library_path": library_path,
                    "auth_kind": auth_kind,
                    "username": "viewer",
                    "required": "write",
                }
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)
