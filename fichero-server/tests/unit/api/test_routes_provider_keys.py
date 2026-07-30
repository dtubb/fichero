"""Coverage for provider API-key and connection status routes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.ai import provider_keys as routes


def test_set_key_rejects_unavailable_keychain(monkeypatch):
    monkeypatch.setattr(routes, "keychain_available", lambda: False)

    with pytest.raises(HTTPException) as caught:
        routes.set_provider_api_key_impl("openai", "sk-test")

    assert caught.value.status_code == 503


def test_set_key_rejects_local_provider(monkeypatch):
    monkeypatch.setattr(routes, "keychain_available", lambda: True)
    monkeypatch.setattr(routes, "get_provider_info", lambda _name: SimpleNamespace(is_local=True))

    with pytest.raises(HTTPException) as caught:
        routes.set_provider_api_key_impl("ollama", "unused")

    assert caught.value.status_code == 400
    assert "don't need" in caught.value.detail


def test_set_key_validates_then_stores(monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "keychain_available", lambda: True)
    monkeypatch.setattr(routes, "get_provider_info", lambda _name: SimpleNamespace(is_local=False))
    monkeypatch.setattr(routes, "validate_provider_config", lambda **kwargs: calls.append(("validate", kwargs)))
    monkeypatch.setattr(routes, "set_api_key", lambda provider, key: calls.append((provider, key)) or True)

    routes.set_provider_api_key_impl("openai", "sk-test")

    assert calls == [("validate", {"provider_type": "openai", "api_key": "sk-test"}), ("openai", "sk-test")]


def test_status_reports_local_provider_without_reading_keychain(monkeypatch):
    monkeypatch.setattr(routes, "get_provider_info", lambda _name: SimpleNamespace(is_local=True))
    monkeypatch.setattr(routes, "has_api_key", lambda _name: pytest.fail("local status must not read keychain"))
    monkeypatch.setattr(routes, "keychain_available", lambda: False)

    response = asyncio.run(routes.check_api_key_status("ollama"))

    assert response.model_dump() == {
        "provider_type": "ollama",
        "has_api_key": True,
        "is_local": True,
        "keychain_available": False,
    }
