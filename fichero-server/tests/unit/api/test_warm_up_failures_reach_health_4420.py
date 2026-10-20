"""A start-up warm-up that fails is said in `GET /api/health` (`startup_warnings`), not only logged (#4420 seam).

WHY: `_warm_configured_provider_keys` and `warm_supported_locales` caught every exception and only logged, so a caller
could not tell a skipped warm-up from one that never ran (`test_swallowed_exception_seam`).
"""
from __future__ import annotations

import sys

import pytest

from fichero_server import startup_warnings
from fichero_server.models import HealthResponse


@pytest.fixture(autouse=True)
def _clean():
    startup_warnings._WARNINGS.clear()
    yield
    startup_warnings._WARNINGS.clear()


def test_a_failed_keychain_warm_up_is_in_health(monkeypatch):
    from fichero_server.api import main as api_main
    from fichero_server.security import keychain

    monkeypatch.setattr(keychain, "warm_api_keys", lambda types: (_ for _ in ()).throw(RuntimeError("locked: /Users/bob/Library/Keychains")))
    api_main._warm_configured_provider_keys()
    health = api_main._with_server_proof(HealthResponse(status="healthy"), None)
    assert health.dependencies["provider_keys"] == "failed: RuntimeError", health.dependencies
    assert "bob" not in str(health.dependencies) and "/Users" not in str(health.dependencies), "class only: health is unauthenticated"


def test_a_failed_vision_locale_warm_up_is_in_health(monkeypatch):
    from fichero_server.api import main as api_main
    from fichero_server.workflows.tools import vision_base

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(vision_base, "_supported_vision_locales", lambda: (_ for _ in ()).throw(OSError("no bundle at /Applications/Fichero.app")))
    vision_base.warm_supported_locales()
    health = api_main._with_server_proof(HealthResponse(status="healthy"), None)
    assert health.dependencies["vision_locales"] == "failed: OSError", health.dependencies
    assert "/Applications" not in str(health.dependencies)


def test_a_clean_start_says_nothing():
    from fichero_server.api import main as api_main

    deps = api_main._with_server_proof(HealthResponse(status="healthy"), None).dependencies
    assert "provider_keys" not in deps and "vision_locales" not in deps
