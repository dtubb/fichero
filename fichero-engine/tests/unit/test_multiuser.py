from __future__ import annotations

import pytest

from fichero.security import authz
from fichero.api.auth import _use_multiuser_auth
from fichero.security.multiuser import multiuser_enabled


def test_multiuser_enabled_explicit_flag(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")

    assert multiuser_enabled() is True
    assert _use_multiuser_auth() is True
    assert authz.multiuser_enabled() is True


def test_multiuser_disabled_by_default(monkeypatch):
    """Single-user local launch is opt-in: multiuser OFF unless signalled (#2721)."""
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("FICHERO_ENABLE_BONJOUR", raising=False)
    monkeypatch.delenv("FICHERO_BIND_HOST", raising=False)
    monkeypatch.delenv("FICHERO_REMOTE_BACKEND_BIND_HOST", raising=False)

    assert multiuser_enabled() is False
    assert _use_multiuser_auth() is False
    assert authz.multiuser_enabled() is False


def test_multiuser_transport_signals_do_not_auto_enable(monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("FICHERO_ENABLE_BONJOUR", "1")
    monkeypatch.setenv("FICHERO_BIND_HOST", "100.64.0.10")
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://fichero.tail123.ts.net")

    assert multiuser_enabled() is False
    assert _use_multiuser_auth() is False
    assert authz.multiuser_enabled() is False


def test_multiuser_enabled_by_persisted_setting(monkeypatch, app_db):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    app_db.set_setting("multiuser.enabled", "true")

    assert multiuser_enabled() is True
    assert _use_multiuser_auth() is True
    assert authz.multiuser_enabled() is True


def test_multiuser_denies_unresolved_direct_action_actor(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")

    with pytest.raises(authz.AuthorizationError, match="write access denied"):
        authz.assert_can_write("ui", tmp_path / "test.fichero")


def test_multiuser_not_enabled_by_existing_accounts(monkeypatch, app_db):
    """Account rows alone do NOT enable multi-user — explicit opt-in only (#3331)."""
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash="hash",
        is_owner=True,
    )

    assert multiuser_enabled() is False
    assert _use_multiuser_auth() is False
    assert authz.multiuser_enabled() is False


def test_multiuser_disabled_with_explicit_off(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("FICHERO_ENABLE_BONJOUR", raising=False)
    monkeypatch.delenv("FICHERO_BIND_HOST", raising=False)
    monkeypatch.delenv("FICHERO_REMOTE_BACKEND_BIND_HOST", raising=False)

    assert multiuser_enabled() is False
    assert _use_multiuser_auth() is False
    assert authz.multiuser_enabled() is False
