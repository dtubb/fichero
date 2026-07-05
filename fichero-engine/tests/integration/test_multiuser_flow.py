from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
import importlib
from pathlib import Path

from fastapi.testclient import TestClient

from fichero.api.auth import initialize_token
from fichero.api.routes import auth_accounts, pairing
from fichero.db_manager import db_manager
from fichero.models import ActionAudit


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
    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app, client=client_addr) as client:
        yield client
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


def test_multiuser_ann_flow_happy_path_and_acl_revocation(tmp_path, app_db, monkeypatch):
    primary = _create_library(tmp_path, "primary")
    secondary = _create_library(tmp_path, "secondary")

    with _client(app_db, monkeypatch) as client:
        _bootstrap_create_owner(client)
        owner_token = _login(client, "owner", "owner-password")
        _register_library(client, primary, "Primary")
        _register_library(client, secondary, "Secondary")

        invite = _mint_invite(client, "ann", "Ann")
        redeem = client.post(
            "/api/auth/invites/redeem",
            json={
                "invite_token": invite["invite_token"],
                "new_password": "ann-password",
                "is_owner": True,
            },
        )
        assert redeem.status_code == 200
        assert redeem.json()["user"]["is_owner"] is False
        ann_token = redeem.json()["session_token"]

        shared = client.post(
            "/api/authz/share",
            headers=_library_headers(primary, owner_token),
            json={
                "user": "ann",
                "role": "editor",
                "object_type": "library",
            },
        )
        assert shared.status_code == 200

        accessible = client.get(
            "/api/authz/libraries",
            headers=_bearer(ann_token),
        )
        assert accessible.status_code == 200
        assert accessible.json() == [
            {
                "library_path": str(primary),
                "library_name": "Primary",
                "role": "editor",
            }
        ]

        read_primary = client.post(
            "/api/search",
            headers=_library_headers(primary, ann_token),
            json={"query": "", "limit": 1},
        )
        write_primary = client.post(
            "/api/search/saved",
            headers=_library_headers(primary, ann_token),
            json={"query": "ann query"},
        )
        assert read_primary.status_code == 200
        assert write_primary.status_code == 200

        deny_other = client.post(
            "/api/search/saved",
            headers=_library_headers(secondary, ann_token),
            json={"query": "denied query"},
        )
        assert deny_other.status_code == 403
        assert deny_other.json() == {
            "detail": "write access denied",
            "code": "library_access_denied",
            "library_path": str(secondary),
            "auth_kind": "session",
            "username": "ann",
            "required": "write",
        }

        revoke = client.delete(
            "/api/authz/members",
            headers=_library_headers(primary, owner_token),
            params={"user": "ann"},
        )
        assert revoke.status_code == 200

        after_revoke = client.post(
            "/api/search/saved",
            headers=_library_headers(primary, ann_token),
            json={"query": "should fail after revoke"},
        )
        assert after_revoke.status_code == 403
        assert after_revoke.json() == {
            "detail": "write access denied",
            "code": "library_access_denied",
            "library_path": str(primary),
            "auth_kind": "session",
            "username": "ann",
            "required": "write",
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
        cannot_pair = client.post(
            "/api/pair/code",
            headers=_bearer(ann_token),
        )
        cannot_self_grant = client.put(
            "/api/authz/members",
            headers=_library_headers(primary, ann_token),
            json={"user": "ann", "role": "owner"},
        )

        assert cannot_invite.status_code == 403
        assert cannot_create_user.status_code == 403
        assert cannot_pair.status_code == 403
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
            f"/api/auth/sessions/{ann_sessions.json()[0]['id']}/revoke",
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
        monkeypatch.setattr("fichero.app_db.datetime", FrozenDateTime)
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
