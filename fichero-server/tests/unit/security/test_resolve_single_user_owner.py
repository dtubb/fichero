"""Tests for auth._resolve_single_user_owner (the #3331 single-user path).

When multi-user is OFF, the loopback bootstrap token is the owner credential;
this resolves (or creates) the owner account so request.state.user is
populated — no login wall for the single-user local owner. These lock in the
create / return-existing / multiple / degrade-on-error branches.
"""
from __future__ import annotations

import logging


from fichero_server.security import accounts
from fichero_server.api.auth import _resolve_single_user_owner


def _make_owner(app_db, username: str, *, active: bool = True):
    return app_db.create_user(
        username=username,
        display_name=username.title(),
        password_hash=accounts.hash_password("pw"),
        is_owner=True,
        active=active,
    )


def test_creates_owner_when_none_exists(app_db):
    assert [u for u in app_db.list_users() if u.is_owner] == []
    owner = _resolve_single_user_owner()
    assert owner is not None
    assert owner.username == "owner"
    assert owner.is_owner is True
    assert owner.active is True
    # And it was persisted, not just returned.
    persisted = [u for u in app_db.list_users() if u.is_owner and u.active]
    assert len(persisted) == 1
    assert persisted[0].id == owner.id


def test_returns_existing_single_owner_without_creating(app_db):
    existing = _make_owner(app_db, "solo")
    before = len(app_db.list_users())
    owner = _resolve_single_user_owner()
    assert owner is not None
    assert owner.id == existing.id
    # No second account created.
    assert len(app_db.list_users()) == before


def test_multiple_owners_returns_first_active(app_db):
    first = _make_owner(app_db, "alpha")
    _make_owner(app_db, "beta")
    owner = _resolve_single_user_owner()
    assert owner is not None
    active_owners = [u for u in app_db.list_users() if u.is_owner and u.active]
    assert len(active_owners) == 2
    # Returns one of the active owners (the first in list order).
    assert owner.id == active_owners[0].id == first.id


def test_inactive_owner_is_ignored_and_one_is_created(app_db):
    # An inactive owner does not count — resolution must create an active one.
    _make_owner(app_db, "retired", active=False)
    owner = _resolve_single_user_owner()
    assert owner is not None
    assert owner.active is True
    assert owner.username == "owner"


def test_degrades_to_none_and_logs_on_error(monkeypatch, caplog):
    # get_app_db is imported inside the function; make it raise.
    import fichero_server.db.app as app_db_module

    def boom():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(app_db_module, "get_app_db", boom)
    with caplog.at_level(logging.WARNING, logger="fichero_server.api.auth"):
        result = _resolve_single_user_owner()
    assert result is None
    assert any("single-user owner resolution failed" in r.message for r in caplog.records)
