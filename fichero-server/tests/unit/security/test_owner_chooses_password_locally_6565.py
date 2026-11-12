"""multiuser.turning-on-needs-an-owner-password (#6565): the owner of THIS Mac chooses their password through
`POST /api/auth/owner-password`, local only, so `owner_password_gap` clears even when first-run and migrate-owner
(which refuse an owner who already has a key) cannot be used. Through the real middleware."""
from __future__ import annotations

from fichero_server.security import accounts
from fichero_server.security.multiuser import OWNER_PASSWORD_SET_KEY, owner_password_gap
from tests.signed_in import signed_in_client, uds_client
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose

ROUTE = "/api/auth/owner-password"


def _people(harness, monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    db = harness.app_db
    owner = db.create_user(username="owner", display_name="Owner", password_hash=accounts.hash_password("random-" * 5), is_owner=True)
    ann = db.create_user(username="ann", display_name="Ann", password_hash=accounts.hash_password("x"), is_owner=False)
    return owner, ann


def _app(harness):
    """The app's own socket: Unix transport plus the start-up credential."""
    http = uds_client(harness)
    http.headers["Authorization"] = f"Bearer {harness.bootstrap}"
    return http


def test_the_local_owner_chooses_a_password_then_the_switch_follows(harness, monkeypatch):
    owner, _ann = _people(harness, monkeypatch)
    assert owner_password_gap(harness.app_db) is not None
    chosen = _app(harness).post(ROUTE, json={"password": "a chosen one"})
    assert chosen.status_code == 200, chosen.text
    assert harness.app_db.get_setting(OWNER_PASSWORD_SET_KEY) == "true"
    assert owner_password_gap(harness.app_db) is None
    assert accounts.verify_password("a chosen one", harness.app_db.get_user(owner.id).password_hash)
    on = _app(harness).put("/api/pair/multiuser", json={"enabled": True})
    assert on.status_code == 200, on.text


def test_the_eight_character_rule_is_the_engines(harness, monkeypatch):
    _people(harness, monkeypatch)
    short = _app(harness).post(ROUTE, json={"password": "short"})
    assert short.status_code == 422 and "8" in short.json()["detail"]
    assert owner_password_gap(harness.app_db) is not None


def test_it_is_refused_off_the_socket_and_for_anyone_but_the_owner(harness, monkeypatch):
    _owner, ann = _people(harness, monkeypatch)
    over_tcp = harness.host().post(ROUTE, json={"password": "a chosen one"})
    assert over_tcp.status_code == 403
    theirs = signed_in_client(harness, ann)
    other = uds_client(harness).post(ROUTE, json={"password": "a chosen one"}, headers=theirs.headers)
    assert other.status_code in (401, 403)
    nobody = uds_client(harness).post(ROUTE, json={"password": "a chosen one"})
    assert nobody.status_code in (401, 403)
    assert owner_password_gap(harness.app_db) is not None


def test_the_change_is_audited_without_the_password(harness, monkeypatch):
    _people(harness, monkeypatch)
    seen = []
    real = harness.app_db.save_chained_account_audit
    monkeypatch.setattr(harness.app_db, "save_chained_account_audit", lambda audit: (seen.append(audit), real(audit))[1])
    assert _app(harness).post(ROUTE, json={"password": "a chosen one"}).status_code == 200
    assert [a.action_name for a in seen] == ["owner.set_password"]
    assert "a chosen one" not in str(seen[0].model_dump())
