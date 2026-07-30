from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest

from fichero_server.api.auth import initialize_token
from fichero_server.api.routes.auth import accounts as auth_accounts
from fichero_server.api.routes.auth import pairing
from fichero_server.db.manager import db_manager
from fichero_server.models import ActionAudit, DocType, Document, FileType, Status


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _library_headers(library_path: Path, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Fichero-Library-Path": str(library_path),
    }


def _create_library(root: Path, name: str) -> Path:
    package = root / f"{name}.fichero"
    package.mkdir()
    (package / "files").mkdir()
    (package / "storage").mkdir()
    (package / "lance").mkdir()
    db_manager.get_database(package)
    return package


def _clear_auth_state() -> None:
    auth_accounts._LOGIN_ATTEMPTS_BY_IP.clear()
    auth_accounts._LOGIN_ATTEMPTS_BY_ACCOUNT.clear()
    auth_accounts._INVITE_MINT_ATTEMPTS_BY_IP.clear()
    auth_accounts._INVITE_REDEEM_ATTEMPTS_BY_IP.clear()
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()


def setup_function() -> None:
    _clear_auth_state()


def teardown_function() -> None:
    _clear_auth_state()


@contextmanager
def _client(app_db, monkeypatch, client_addr: tuple[str, int] = ("testclient", 50000)):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.routes.ai.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app, client=client_addr) as client:
        yield client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


@contextmanager
def _client_bundle(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    monkeypatch.setenv("FICHERO_TAILNET_URL", "https://fichero-demo.ts.net")
    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.routes.ai.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with (
        TestClient(api_main.app, client=("127.0.0.1", 50000)) as local_client,
        TestClient(
            api_main.app,
            base_url="https://paired.example",
            client=("198.51.100.20", 5000),
        ) as remote_client,
    ):
        yield local_client, remote_client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


@asynccontextmanager
async def _async_client_bundle(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    monkeypatch.setenv("FICHERO_TAILNET_URL", "https://fichero-demo.ts.net")
    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero_server.api.routes.ai.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    local_transport = httpx.ASGITransport(
        app=api_main.app,
        client=("127.0.0.1", 50000),
    )
    remote_transport = httpx.ASGITransport(
        app=api_main.app,
        client=("198.51.100.20", 5000),
    )
    async with (
        httpx.AsyncClient(
            transport=local_transport,
            base_url="http://testserver",
        ) as local_client,
        httpx.AsyncClient(
            transport=remote_transport,
            base_url="https://paired.example",
        ) as remote_client,
    ):
        yield local_client, remote_client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def _bootstrap_create_owner(client: TestClient) -> None:
    response = client.post(
        "/api/users",
        headers=_bearer(initialize_token()),
        json={
            "username": "owner",
            "display_name": "Owner",
            "password": "owner-password",
            "is_owner": False,
        },
    )
    assert response.status_code == 200


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["session_token"]


def _mint_invite(client: TestClient, username: str, display_name: str) -> dict:
    response = client.post(
        "/api/auth/invites",
        headers=_bearer(initialize_token()),
        json={"username": username, "display_name": display_name},
    )
    assert response.status_code == 200
    return response.json()


def _register_library(client: TestClient, library_path: Path, name: str) -> None:
    response = client.post(
        "/api/registry/add",
        headers=_bearer(initialize_token()),
        params={"path": str(library_path), "name": name},
    )
    assert response.status_code == 200


def _pair_device(local_client: TestClient, remote_client: TestClient, session_token: str, device_name: str) -> dict:
    code_response = local_client.post(
        "/api/pair/code",
        headers=_bearer(session_token),
    )
    assert code_response.status_code == 200
    pair_response = remote_client.post(
        "/api/pair",
        json={"code": code_response.json()["code"], "device_name": device_name},
    )
    assert pair_response.status_code == 200
    return pair_response.json()


@pytest.mark.asyncio
async def test_multiuser_ann_flow_happy_path_and_acl_revocation(tmp_path, app_db, monkeypatch):
    primary = _create_library(tmp_path, "primary")
    secondary = _create_library(tmp_path, "secondary")

    async with _async_client_bundle(app_db, monkeypatch) as (local_client, remote_client):
        from fichero_server.api.routes.activity import stream_activities

        create_owner = await local_client.post(
            "/api/users",
            headers=_bearer(initialize_token()),
            json={
                "username": "owner",
                "display_name": "Owner",
                "password": "owner-password",
                "is_owner": False,
            },
        )
        assert create_owner.status_code == 200
        owner_login = await local_client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "owner-password"},
        )
        assert owner_login.status_code == 200
        owner_token = owner_login.json()["session_token"]
        add_primary = await local_client.post(
            "/api/registry/add",
            headers=_bearer(initialize_token()),
            params={"path": str(primary), "name": "Primary"},
        )
        add_secondary = await local_client.post(
            "/api/registry/add",
            headers=_bearer(initialize_token()),
            params={"path": str(secondary), "name": "Secondary"},
        )
        assert add_primary.status_code == 200
        assert add_secondary.status_code == 200

        invite = await local_client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "ann", "display_name": "Ann"},
        )
        assert invite.status_code == 200
        redeem = await local_client.post(
            "/api/auth/invites/redeem",
            json={
                "invite_token": invite.json()["invite_token"],
                "new_password": "ann-password",
                "is_owner": True,
            },
        )
        assert redeem.status_code == 200
        assert redeem.json()["user"]["is_owner"] is False
        ann_token = redeem.json()["session_token"]

        shared = await local_client.post(
            "/api/authz/share",
            headers=_library_headers(primary, owner_token),
            json={
                "user": "ann",
                "role": "editor",
                "object_type": "library",
            },
        )
        assert shared.status_code == 200

        accessible = await local_client.get(
            "/api/authz/libraries",
            headers=_bearer(ann_token),
        )
        assert accessible.status_code == 200
        assert accessible.json() == {
            "items": [
                {
                    "library_path": str(primary),
                    "library_name": "Primary",
                    "role": "editor",
                }
            ],
            "count": 1,
        }

        code_response = await local_client.post(
            "/api/pair/code",
            headers=_bearer(ann_token),
        )
        assert code_response.status_code == 200
        paired = await remote_client.post(
            "/api/pair",
            json={"code": code_response.json()["code"], "device_name": "Ann iPad"},
        )
        assert paired.status_code == 200
        paired_payload = paired.json()
        device_token = paired_payload["device_token"]
        device_id = paired_payload["device_id"]

        read_primary = await remote_client.post(
            "/api/search",
            headers=_library_headers(primary, device_token),
            json={"query": "", "limit": 1},
        )
        write_primary = await remote_client.post(
            "/api/search/saved",
            headers=_library_headers(primary, device_token),
            json={"query": "ann query"},
        )
        assert read_primary.status_code == 200
        assert write_primary.status_code == 200

        deny_other = await remote_client.post(
            "/api/search/saved",
            headers=_library_headers(secondary, device_token),
            json={"query": "denied query"},
        )
        assert deny_other.status_code == 403
        assert deny_other.json() == {
            "detail": "write access denied",
            "code": "library_access_denied",
            "library_path": str(secondary),
            "auth_kind": "device",
            "username": "ann",
            "required": "write",
        }

        activity_response = await stream_activities(
            db=db_manager.get_database(primary),
            types=None,
            levels=None,
        )
        owner_mutation = await local_client.post(
            "/api/search/saved",
            headers=_library_headers(primary, owner_token),
            json={"query": "owner mutation for stream"},
        )
        assert owner_mutation.status_code == 200
        payload = None
        for _ in range(5):
            line = await anext(activity_response.body_iterator)
            if not line or line.startswith(":") or not line.startswith("data: "):
                continue
            payload = json.loads(line.removeprefix("data: ").strip())
            break

        assert payload is not None
        assert payload["metadata"]["change_type"] == "savedsearch.created"
        assert payload["metadata"]["actor"] == "owner"

        denied_stream = await remote_client.get(
            "/api/activity/stream",
            headers=_library_headers(secondary, device_token),
        )
        assert denied_stream.status_code == 403
        assert denied_stream.json() == {
            "detail": "read access denied",
            "code": "library_access_denied",
            "library_path": str(secondary),
            "auth_kind": "device",
            "username": "ann",
            "required": "read",
        }

        revoke_device = await local_client.post(
            f"/api/pair/devices/{device_id}/revoke",
            headers=_bearer(owner_token),
        )
        assert revoke_device.status_code == 200

        revoked_follow_up = await remote_client.post(
            "/api/search/saved",
            headers=_library_headers(primary, device_token),
            json={"query": "should fail after device revoke"},
        )
        assert revoked_follow_up.status_code == 401
        assert revoked_follow_up.json() == {
            "detail": "missing or invalid Authorization header"
        }

        ann_user = app_db.get_user_by_username("ann")
        deactivate = await local_client.patch(
            f"/api/users/{ann_user.id}",
            headers=_bearer(owner_token),
            json={"active": False},
        )
        assert deactivate.status_code == 200

        deactivated_follow_up = await local_client.get("/api/auth/me", headers=_bearer(ann_token))
        assert deactivated_follow_up.status_code == 401
        assert deactivated_follow_up.json() == {
            "detail": "missing or invalid Authorization header"
        }


def test_multiuser_adversarial_owner_gates_denials_and_actor_attribution(
    tmp_path, app_db, monkeypatch
):
    primary = _create_library(tmp_path, "primary")

    with _client(app_db, monkeypatch) as client:
        _bootstrap_create_owner(client)
        owner_token = _login(client, "owner", "owner-password")
        _register_library(client, primary, "Primary")
        invite = _mint_invite(client, "ann", "Ann")
        ann = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": invite["invite_token"], "new_password": "ann-password"},
        )
        assert ann.status_code == 200
        ann_token = ann.json()["session_token"]

        share = client.post(
            "/api/authz/share",
            headers=_library_headers(primary, owner_token),
            json={"user": "ann", "role": "editor", "object_type": "library"},
        )
        assert share.status_code == 200

        cannot_invite = client.post(
            "/api/auth/invites",
            headers=_bearer(ann_token),
            json={"username": "eve", "display_name": "Eve"},
        )
        cannot_create_user = client.post(
            "/api/users",
            headers=_bearer(ann_token),
            json={
                "username": "eve",
                "display_name": "Eve",
                "password": "eve-password",
                "is_owner": True,
            },
        )
        cannot_self_grant = client.put(
            "/api/authz/members",
            headers=_library_headers(primary, ann_token),
            json={"user": "ann", "role": "owner"},
        )

        assert cannot_invite.status_code == 403
        assert cannot_create_user.status_code == 403
        assert cannot_self_grant.status_code == 403
        assert cannot_self_grant.json() == {"detail": "owner access required"}

        write_primary = client.post(
            "/api/search/saved",
            headers=_library_headers(primary, ann_token),
            json={"query": "ann actor audit"},
        )
        assert write_primary.status_code == 200

        bootstrap_off_loopback = None
        with _client(app_db, monkeypatch, client_addr=("192.0.2.44", 5000)) as remote_client:
            bootstrap_off_loopback = remote_client.get(
                "/api/providers",
                headers=_bearer(initialize_token()),
            )
        assert bootstrap_off_loopback.status_code == 401
        assert bootstrap_off_loopback.json() == {"detail": "bootstrap auth is loopback only"}

    primary_db = db_manager.get_database(primary)
    audits = sorted(primary_db.all(ActionAudit), key=lambda audit: audit.created_at)
    assert any(audit.action_name == "acl.set" and audit.actor == "owner" for audit in audits)
    assert any(audit.action_name == "savedsearch.save" and audit.actor == "ann" for audit in audits)


def test_reader_view_routes_require_read_access_for_the_selected_library(
    tmp_path, app_db, monkeypatch
):
    primary = _create_library(tmp_path, "primary")
    secondary = _create_library(tmp_path, "secondary")

    db_manager.get_database(secondary).save(
        Document(
            id="secondary-doc",
            name="Denied.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="secret transcript",
            status=Status.completed,
        )
    )

    with _client(app_db, monkeypatch) as client:
        _bootstrap_create_owner(client)
        owner_token = _login(client, "owner", "owner-password")
        _register_library(client, primary, "Primary")
        _register_library(client, secondary, "Secondary")
        invite = _mint_invite(client, "ann", "Ann")
        redeemed = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": invite["invite_token"], "new_password": "ann-password"},
        )
        assert redeemed.status_code == 200
        ann_token = redeemed.json()["session_token"]

        share = client.post(
            "/api/authz/share",
            headers=_library_headers(primary, owner_token),
            json={"user": "ann", "role": "viewer", "object_type": "library"},
        )
        assert share.status_code == 200

        denied_document = client.get(
            "/view/document/secondary-doc",
            headers=_library_headers(secondary, ann_token),
        )
        denied_global = client.get(
            "/view/kg/global",
            headers=_library_headers(secondary, ann_token),
        )

        expected = {
            "detail": "read access denied",
            "code": "library_access_denied",
            "library_path": str(secondary),
            "auth_kind": "session",
            "username": "ann",
            "required": "read",
        }
        assert denied_document.status_code == 403
        assert denied_document.json() == expected
        assert denied_global.status_code == 403
        assert denied_global.json() == expected


def test_multiuser_session_revoke_and_deactivate_kill_access(tmp_path, app_db, monkeypatch):
    primary = _create_library(tmp_path, "primary")

    with _client(app_db, monkeypatch) as client:
        _bootstrap_create_owner(client)
        owner_token = _login(client, "owner", "owner-password")
        _register_library(client, primary, "Primary")
        invite = _mint_invite(client, "ann", "Ann")
        redeemed = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": invite["invite_token"], "new_password": "ann-password"},
        )
        ann_token = redeemed.json()["session_token"]
        client.post(
            "/api/authz/share",
            headers=_library_headers(primary, owner_token),
            json={"user": "ann", "role": "editor", "object_type": "library"},
        )

        second_login = client.post(
            "/api/auth/login",
            json={"username": "ann", "password": "ann-password"},
        )
        assert second_login.status_code == 200
        second_token = second_login.json()["session_token"]

        ann_sessions = client.get(
            "/api/auth/sessions",
            headers=_bearer(ann_token),
        )
        assert ann_sessions.status_code == 200
        revoke = client.post(
            f"/api/auth/sessions/{ann_sessions.json()['items'][0]['id']}/revoke",
            headers=_bearer(ann_token),
        )
        assert revoke.status_code == 200

        revoked_follow_up = client.get("/api/auth/me", headers=_bearer(second_token))
        assert revoked_follow_up.status_code == 401
        assert revoked_follow_up.json() == {"detail": "missing or invalid Authorization header"}

        ann_user = app_db.get_user_by_username("ann")
        deactivate = client.patch(
            f"/api/users/{ann_user.id}",
            headers=_bearer(owner_token),
            json={"active": False},
        )
        assert deactivate.status_code == 200

        first_follow_up = client.get("/api/auth/me", headers=_bearer(ann_token))
        assert first_follow_up.status_code == 401
        assert first_follow_up.json() == {"detail": "missing or invalid Authorization header"}


def test_multiuser_invite_attack_surface_and_concurrent_redeem(
    tmp_path, app_db, monkeypatch
):
    _create_library(tmp_path, "primary")
    base_now = datetime(2026, 7, 5, 12, 0, 0)

    class FrozenDateTime(datetime):
        current = base_now

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else tz.fromutc(cls.current.replace(tzinfo=tz))

    with _client(app_db, monkeypatch) as client:
        _bootstrap_create_owner(client)

        invite = _mint_invite(client, "ann", "Ann")
        first = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": invite["invite_token"], "new_password": "ann-password"},
        )
        second = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": invite["invite_token"], "new_password": "other-password"},
        )
        invalid = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": "not-a-real-token", "new_password": "password"},
        )

        monkeypatch.setattr(auth_accounts, "datetime", FrozenDateTime)
        monkeypatch.setattr("fichero_server.db.app.datetime", FrozenDateTime)
        expiring = _mint_invite(client, "bea", "Bea")
        FrozenDateTime.current = base_now + auth_accounts.INVITE_TTL + timedelta(seconds=1)
        expired = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": expiring["invite_token"], "new_password": "bea-password"},
        )

    assert first.status_code == 200
    assert first.json()["user"]["is_owner"] is False
    assert second.status_code == 401
    assert second.json()["code"] == "invite_consumed"
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "invalid_invite"
    assert expired.status_code == 401
    assert expired.json()["code"] == "invite_expired"

    concurrent_invite = None
    with _client(app_db, monkeypatch) as client:
        concurrent_invite = _mint_invite(client, "cara", "Cara")

    def redeem_once(password: str) -> tuple[int, dict]:
        with _client(app_db, monkeypatch) as client:
            response = client.post(
                "/api/auth/invites/redeem",
                json={"invite_token": concurrent_invite["invite_token"], "new_password": password},
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem_once, ("cara-password-1", "cara-password-2")))

    assert sum(1 for status, _payload in results if status == 200) == 1
    assert sum(1 for status, _payload in results if status != 200) == 1
