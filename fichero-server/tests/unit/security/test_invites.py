from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import importlib

import pytest
from fastapi.testclient import TestClient

from fichero_server.security import accounts
from fichero_server.api.auth import initialize_token
from fichero_server.api.routes.auth import accounts as auth_accounts
from fichero_server.api.routes.auth import pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_multiuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")


class _Clock:
    """A movable stand-in for ``utc_now`` — always aware UTC.

    The clock seam is ``utc_now`` in each module (#4347); patching
    ``<module>.datetime`` no longer intercepts anything, which is how these
    tests silently started running against the real wall clock.
    """

    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _freeze_clock(monkeypatch: pytest.MonkeyPatch, current: datetime) -> _Clock:
    clock = _Clock(current)
    monkeypatch.setattr(auth_accounts, "utc_now", clock)
    monkeypatch.setattr("fichero_server.db.app.utc_now", clock)
    return clock


def _iso_z(value: datetime) -> str:
    """Serialize the way the API does: aware UTC with a ``Z`` offset."""
    return value.isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def clear_auth_invite_state():
    auth_accounts._LOGIN_ATTEMPTS_BY_IP.clear()
    auth_accounts._LOGIN_ATTEMPTS_BY_ACCOUNT.clear()
    auth_accounts._INVITE_MINT_ATTEMPTS_BY_IP.clear()
    auth_accounts._INVITE_REDEEM_ATTEMPTS_BY_IP.clear()
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    yield
    auth_accounts._LOGIN_ATTEMPTS_BY_IP.clear()
    auth_accounts._LOGIN_ATTEMPTS_BY_ACCOUNT.clear()
    auth_accounts._INVITE_MINT_ATTEMPTS_BY_IP.clear()
    auth_accounts._INVITE_REDEEM_ATTEMPTS_BY_IP.clear()
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()


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


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["session_token"]


def test_invite_mint_is_owner_only(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    app_db.create_user(
        username="member",
        display_name="Member",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )

    with _client(app_db, monkeypatch) as client:
        member_token = _login(client, "member", "password")
        denied = client.post(
            "/api/auth/invites",
            headers=_bearer(member_token),
            json={"username": "invitee", "display_name": "Invitee"},
        )
        allowed = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "invitee", "display_name": "Invitee"},
        )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["invite"]["username"] == "invitee"
    assert allowed.json()["redemption_url"].startswith("fichero://invite?token=")


def test_invite_redeem_creates_account_sets_password_and_issues_session(
    app_db, monkeypatch
):
    _enable_multiuser(monkeypatch)

    with _client(app_db, monkeypatch) as client:
        invite = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "invitee", "display_name": "Invitee"},
        )
        assert invite.status_code == 200

        redeemed = client.post(
            "/api/auth/invites/redeem",
            json={
                "invite_token": invite.json()["invite_token"],
                "new_password": "correct horse battery staple",
            },
        )
        assert redeemed.status_code == 200

        me = client.get(
            "/api/auth/me",
            headers=_bearer(redeemed.json()["session_token"]),
        )

    user = app_db.get_user_by_username("invitee")
    assert user is not None
    assert user.active is True
    assert accounts.verify_password("correct horse battery staple", user.password_hash) is True
    assert me.status_code == 200
    assert me.json()["username"] == "invitee"


def test_invite_is_one_time_only(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    with _client(app_db, monkeypatch) as client:
        invite = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "invitee", "display_name": "Invitee"},
        )
        token = invite.json()["invite_token"]

        first = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": token, "new_password": "password-1"},
        )
        second = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": token, "new_password": "password-2"},
        )

    assert first.status_code == 200
    assert second.status_code == 401
    assert second.json()["code"] == "invite_consumed"


def test_invites_keep_short_qr_ttl_but_email_lives_for_a_day(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    base_now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
    _freeze_clock(monkeypatch, base_now)

    with _client(app_db, monkeypatch) as client:
        qr = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "qr-user", "display_name": "QR User", "channel": "qr"},
        )
        messages = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={
                "username": "messages-user",
                "display_name": "Messages User",
                "channel": "messages",
            },
        )
        email = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "email-user", "display_name": "Email User", "channel": "email"},
        )

    assert qr.status_code == 200
    assert messages.status_code == 200
    assert email.status_code == 200
    assert qr.json()["invite"]["expires_at"] == _iso_z(base_now + timedelta(minutes=15))
    assert messages.json()["invite"]["expires_at"] == _iso_z(
        base_now + timedelta(minutes=15)
    )
    assert email.json()["invite"]["expires_at"] == _iso_z(base_now + timedelta(days=1))
    assert qr.json()["invite"]["channel"] == "qr"
    assert messages.json()["invite"]["channel"] == "messages"
    assert email.json()["invite"]["channel"] == "email"


def test_invite_redemption_records_a_durable_notice(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    with _client(app_db, monkeypatch) as client:
        invite = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "invitee", "display_name": "Invitee", "channel": "email"},
        )
        redeemed = client.post(
            "/api/auth/invites/redeem",
            json={
                "invite_token": invite.json()["invite_token"],
                "new_password": "password-1",
            },
        )

    assert redeemed.status_code == 200
    notices = [audit for audit in app_db.list_action_audits() if audit.action_name == "invite.redeemed"]
    assert len(notices) == 1
    assert notices[0].target_ids == [invite.json()["invite"]["id"]]
    assert notices[0].params == {"username": "invitee", "channel": "email"}


def test_expired_invite_fails(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    base_now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
    clock = _freeze_clock(monkeypatch, base_now)

    with _client(app_db, monkeypatch) as client:
        invite = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "invitee", "display_name": "Invitee"},
        )
        token = invite.json()["invite_token"]
        clock.current = base_now + auth_accounts.INVITE_TTL + timedelta(seconds=1)
        expired = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": token, "new_password": "password-1"},
        )

    assert expired.status_code == 401
    assert expired.json()["code"] == "invite_expired"


def test_invalid_invite_fails(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    with _client(app_db, monkeypatch) as client:
        response = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": "not-a-real-token", "new_password": "password-1"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_invite"


def test_owner_can_list_and_revoke_pending_invites(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    with _client(app_db, monkeypatch) as client:
        invite = client.post(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
            json={"username": "invitee", "display_name": "Invitee"},
        )
        invite_id = invite.json()["invite"]["id"]
        token = invite.json()["invite_token"]

        listed = client.get(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
        )
        revoked = client.post(
            f"/api/auth/invites/{invite_id}/revoke",
            headers=_bearer(initialize_token()),
        )
        after = client.get(
            "/api/auth/invites",
            headers=_bearer(initialize_token()),
        )
        redeem = client.post(
            "/api/auth/invites/redeem",
            json={"invite_token": token, "new_password": "password-1"},
        )

    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert [item["username"] for item in listed.json()["items"]] == ["invitee"]
    assert revoked.status_code == 200
    assert after.status_code == 200
    assert after.json() == {"items": [], "count": 0}
    assert redeem.status_code == 401
    assert redeem.json()["code"] == "invite_revoked"
