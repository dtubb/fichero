from __future__ import annotations

from fichero import authz
from fichero.api.auth import _use_multiuser_auth
from fichero.multiuser import multiuser_enabled


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


def test_multiuser_enabled_by_public_base_url(monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://fichero.tail123.ts.net")

    assert multiuser_enabled() is True
    assert _use_multiuser_auth() is True
    assert authz.multiuser_enabled() is True


def test_multiuser_enabled_by_bonjour(monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("FICHERO_ENABLE_BONJOUR", "1")

    assert multiuser_enabled() is True
    assert _use_multiuser_auth() is True
    assert authz.multiuser_enabled() is True


def test_multiuser_enabled_by_non_loopback_bind(monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("FICHERO_ENABLE_BONJOUR", raising=False)
    monkeypatch.setenv("FICHERO_BIND_HOST", "100.64.0.10")

    assert multiuser_enabled() is True
    assert _use_multiuser_auth() is True
    assert authz.multiuser_enabled() is True


def test_multiuser_disabled_with_explicit_off(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("FICHERO_ENABLE_BONJOUR", raising=False)
    monkeypatch.delenv("FICHERO_BIND_HOST", raising=False)
    monkeypatch.delenv("FICHERO_REMOTE_BACKEND_BIND_HOST", raising=False)

    assert multiuser_enabled() is False
    assert _use_multiuser_auth() is False
    assert authz.multiuser_enabled() is False
