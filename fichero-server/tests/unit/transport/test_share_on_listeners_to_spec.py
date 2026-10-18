"""sharing.share-on-choice / sharing.listener (#5736): the `.local` listener follows "This network".

Unset (a Mac updated from before the choice existed): on only if a device is actually paired, so an
update never drops the owner's phone; a fresh setup has none, so it stays off. An explicit choice wins.
"""

import pytest

from fichero_server import __main__ as backend_main
from fichero_server.security import accounts

LAN = "192.168.1.42"


@pytest.fixture(autouse=True)
def _lan(monkeypatch):
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: LAN)
    monkeypatch.delenv("FICHERO_THIS_NETWORK", raising=False)


def _pair_device(app_db, revoked=False):
    user = app_db.list_users()[0] if hasattr(app_db, "list_users") and app_db.list_users() else None
    user_id = user.id if user else backend_main_owner(app_db)
    device = app_db.create_device(name="iPhone", user_id=user_id, token_hash=accounts.hash_token("t"))
    if revoked:
        app_db.revoke_device(device.id)
    return device


def backend_main_owner(app_db):
    from fichero_server.api.auth import ensure_owner_account

    return ensure_owner_account(app_db).id


def test_an_update_with_a_paired_device_keeps_the_local_listener(app_db, monkeypatch):
    _pair_device(app_db)
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


def test_a_fresh_setup_with_no_device_opens_no_local_listener(app_db):
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_a_revoked_device_does_not_keep_it_open(app_db):
    _pair_device(app_db, revoked=True)
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_an_explicit_off_wins_over_a_paired_device(app_db, monkeypatch):
    _pair_device(app_db)
    monkeypatch.setenv("FICHERO_THIS_NETWORK", "0")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_an_explicit_on_opens_it_with_no_device(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_THIS_NETWORK", "1")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]
