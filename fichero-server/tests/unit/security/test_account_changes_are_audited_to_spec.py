"""sharing.account-changes-are-audited (#5765): every account, invite and session change leaves an audit row."""
from __future__ import annotations

import pytest

from fichero_server.api.auth import initialize_token
from fichero_server.security import accounts

from .test_invites import _bearer, _client, _enable_multiuser, _login, clear_auth_invite_state  # noqa: F401


def _names(app_db) -> list[str]:
    return [a.action_name for a in app_db.list_action_audits()]


def test_every_account_invite_and_session_change_is_audited(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    owner = app_db.create_user(
        username="owner", display_name="Owner",
        password_hash=accounts.hash_password("password"), is_owner=True,
    )
    with _client(app_db, monkeypatch) as client:
        token = _login(client, "owner", "password")
        h = _bearer(token)
        made = client.post(
            "/api/users", headers=h,
            json={"username": "ann", "display_name": "Ann", "password": "password-1"},
        ).json()
        client.patch(f"/api/users/{made['id']}", headers=h, json={"display_name": "Ann T"})
        invite = client.post(
            "/api/auth/invites", headers=h, json={"username": "bob", "display_name": "Bob"}
        ).json()["invite"]
        client.post(f"/api/auth/invites/{invite['id']}/revoke", headers=h)
        ann_token = _login(client, "ann", "password-1")
        sid = next(s["id"] for s in client.get("/api/auth/sessions", headers=_bearer(ann_token)).json()["items"])
        client.post(f"/api/auth/sessions/{sid}/revoke", headers=_bearer(ann_token))
        client.delete(f"/api/users/{made['id']}", headers=h)

    rows = {a.action_name: a for a in app_db.list_action_audits()}
    for name in ("user.create", "user.update", "invite.create", "invite.revoke", "session.revoke", "user.delete"):
        assert name in rows, f"{name} left no audit row; have {sorted(rows)}"
    assert rows["user.create"].actor == f"user:{owner.id}"
    assert rows["user.create"].target_ids == [made["id"]]
    assert "password" not in str(rows["user.create"].params)
    assert "password-1" not in str(rows["user.update"].params)


def test_bootstrap_changes_are_audited_as_bootstrap(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner", display_name="Owner",
        password_hash=accounts.hash_password("password"), is_owner=True,
    )
    with _client(app_db, monkeypatch) as client:
        client.post(
            "/api/users", headers=_bearer(initialize_token()),
            json={"username": "cy", "display_name": "Cy", "password": "password-2"},
        )
    row = next(a for a in app_db.list_action_audits() if a.action_name == "user.create")
    assert row.actor == "bootstrap"


def test_account_audits_are_chained_and_keep_client_and_device(app_db, monkeypatch):
    """review 76: account rows are tamper-evident like action audits, and the client survives the save."""
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner", display_name="Owner",
        password_hash=accounts.hash_password("password"), is_owner=True,
    )
    with _client(app_db, monkeypatch) as client:
        h = {**_bearer(initialize_token()), "X-Fichero-Client": "fichero-cli"}
        for name in ("ann", "bob"):
            client.post("/api/users", headers=h,
                        json={"username": name, "display_name": name, "password": "password-1"})
    rows = [a for a in app_db.list_action_audits() if a.action_name == "user.create"]
    assert len(rows) == 2
    assert [r.chain_seq for r in rows] == [1, 2]
    assert rows[0].prev_hash is None and rows[1].prev_hash == rows[0].row_hash
    assert all(r.row_hash for r in rows)
    assert all(r.client == "fichero-cli" for r in rows)


def test_a_failed_audit_write_stops_the_change(app_db, monkeypatch):
    """review 76: the audit is written first, so no change can go unaudited."""
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner", display_name="Owner",
        password_hash=accounts.hash_password("password"), is_owner=True,
    )

    def boom(*a, **k):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(app_db, "save_chained_account_audit", boom)
    with _client(app_db, monkeypatch) as client:
        with pytest.raises(RuntimeError, match="audit store down"):
            client.post("/api/users", headers=_bearer(initialize_token()),
                        json={"username": "dee", "display_name": "Dee", "password": "password-1"})
    assert app_db.get_user_by_username("dee") is None
