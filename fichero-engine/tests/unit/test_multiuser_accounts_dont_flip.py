"""#3331 invariant: account rows alone never enable multi-user.

Before #3331, ``multiuser_enabled()`` fell back to ``_has_account_rows()`` — so
the mere existence of an account (e.g. the ``__paired_device_owner__`` side
effect) silently flipped multi-user ON, producing the phantom sign-in wall.
#3331 removed that fallback: multi-user is now explicit opt-in only. This locks
that in so the fallback can't be reintroduced.
"""
from __future__ import annotations

from fichero.security import accounts
from fichero.security.multiuser import multiuser_enabled


def test_accounts_alone_do_not_enable_multiuser(app_db, monkeypatch):
    # No explicit request: neither the env flag nor a persisted setting.
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)

    # Even with account rows present, multi-user must stay OFF.
    app_db.create_user(
        username="someone",
        display_name="Someone",
        password_hash=accounts.hash_password("pw"),
        is_owner=True,
        active=True,
    )
    assert app_db.list_users(), "precondition: an account row exists"

    assert multiuser_enabled() is False


def test_explicit_env_flag_still_enables(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    assert multiuser_enabled() is True


def test_explicit_off_disables(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    assert multiuser_enabled() is False
