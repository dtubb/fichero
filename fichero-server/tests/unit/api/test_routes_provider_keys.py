"""Coverage for provider API-key and connection status routes."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import httpx
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
    # #4534 renamed the keychain seam (has_api_key -> api_key_state /
    # has_supplied_api_key); the pin follows: NEITHER may run for local.
    monkeypatch.setattr(routes, "api_key_state", lambda _name: pytest.fail("local status must not read keychain"))
    monkeypatch.setattr(routes, "has_supplied_api_key", lambda _name: pytest.fail("local status must not probe supplied keys"))
    monkeypatch.setattr(routes, "keychain_available", lambda: False)

    response = routes.check_api_key_status("ollama")  # a plain def since #5257

    assert response.model_dump(exclude_none=True) == {
        "provider_type": "ollama",
        "has_api_key": True,
        "key_state": routes.ProviderKeyState.FOUND,
        "is_local": True,
        "keychain_available": False,
    }


# =============================================================================
# Test Connection: real probes (#4816 — a dead OpenRouter key reported
# success on every click because the untested branch treated "any non-empty
# key" as proof).
# =============================================================================


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Minimal async-context-manager stand-in for ``httpx.AsyncClient()``."""

    def __init__(self, response=None, exc: Exception | None = None):
        self._response = response
        self._exc = exc
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def get(self, url, headers=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "headers": headers or {}})
        if self._exc is not None:
            raise self._exc
        return self._response


def _mock_probe(monkeypatch, api_key, response=None, exc=None):
    fake_client = _FakeAsyncClient(response=response, exc=exc)
    monkeypatch.setattr(routes, "get_provider_info", lambda _name: SimpleNamespace(is_local=False))
    monkeypatch.setattr(routes, "get_api_key", lambda _name: api_key)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: fake_client)
    return fake_client


# Every provider with a real network probe as of #4816, and the URL each one
# must call. `anthropic` and `openrouter` have dedicated branches (different
# auth header / endpoint shape); the rest share `_BEARER_PROBE_TARGETS`.
_REAL_PROBE_PROVIDERS = [
    ("openrouter", "https://openrouter.ai/api/v1/key"),
    ("anthropic", "https://api.anthropic.com/v1/models"),
    *[(name, url) for name, (url, _label) in routes._BEARER_PROBE_TARGETS.items()],
]


@pytest.mark.parametrize("provider_type,expected_url", _REAL_PROBE_PROVIDERS)
def test_connection_test_real_probe_success_sets_verified(monkeypatch, provider_type, expected_url):
    fake_client = _mock_probe(monkeypatch, "a-real-key", response=_FakeResponse(200, {"data": []}))

    result = asyncio.run(routes.test_provider_connection(provider_type))

    assert result.success is True
    assert result.verified is True
    assert fake_client.calls[0]["url"] == expected_url
    if provider_type == "anthropic":
        assert fake_client.calls[0]["headers"]["x-api-key"] == "a-real-key"
    else:
        assert fake_client.calls[0]["headers"]["Authorization"] == "Bearer a-real-key"


@pytest.mark.parametrize("provider_type,expected_url", _REAL_PROBE_PROVIDERS)
def test_connection_test_real_probe_401_fails_unverified(monkeypatch, provider_type, expected_url):
    _mock_probe(monkeypatch, "a-dead-key", response=_FakeResponse(401))

    result = asyncio.run(routes.test_provider_connection(provider_type))

    assert result.success is False
    assert result.verified is not True
    assert result.message == "Invalid API key"


@pytest.mark.parametrize("status_code", [404, 429, 500])
@pytest.mark.parametrize("provider_type,expected_url", _REAL_PROBE_PROVIDERS)
def test_connection_test_real_probe_non_auth_status_is_unverified_not_failed(
    monkeypatch, provider_type, expected_url, status_code
):
    """Team-lead review: only 401/403 proves a bad key. A wrong/rate-limited/
    down endpoint (404/429/5xx) must not paint a GOOD key as broken -- that
    sends the user re-entering a key that was fine (#4816)."""
    _mock_probe(monkeypatch, "a-key", response=_FakeResponse(status_code))

    result = asyncio.run(routes.test_provider_connection(provider_type))

    assert result.success is True
    assert result.verified is False
    assert str(status_code) in result.message


@pytest.mark.parametrize("provider_type,expected_url", _REAL_PROBE_PROVIDERS)
def test_connection_test_real_probe_network_failure_reports_connectivity(
    monkeypatch, provider_type, expected_url
):
    _mock_probe(monkeypatch, "a-key", exc=httpx.ConnectError("boom"))

    result = asyncio.run(routes.test_provider_connection(provider_type))

    assert result.success is False
    assert result.verified is not True
    # Must not claim the KEY is bad when the network is what failed.
    assert "reachable" in result.message.lower() or "connect" in result.message.lower()
    assert "invalid" not in result.message.lower()


@pytest.mark.parametrize("provider_type,expected_url", _REAL_PROBE_PROVIDERS)
def test_connection_test_real_probe_no_key_unchanged(monkeypatch, provider_type, expected_url):
    _mock_probe(monkeypatch, None)

    result = asyncio.run(routes.test_provider_connection(provider_type))

    assert result.success is False
    assert result.message == "No API key configured"
    assert result.verified is not True


# =============================================================================
# Task 3 Part A: the "only an auth answer proves a bad key" rule applied
# uniformly to the five pre-existing probes (openai, huggingface, google,
# groq, deepl). Each provider's OWN bad-key status code(s) must still fail;
# any OTHER non-200 must now report unverified, not failed.
# =============================================================================

_LEGACY_PROBE_BAD_KEY_STATUS: dict[str, tuple[int, ...]] = {
    "openai": (401,),
    "huggingface": (401,),
    # Google's API-key errors surface as 400 (body reason API_KEY_INVALID),
    # never 401/403 -- kept as its real bad-key signal, not touched by #4816.
    "google": (400,),
    "groq": (401,),
    # DeepL answers a mismatched free/pro host with a bare 403; 401 also
    # covered defensively (existing code already checked both).
    "deepl": (401, 403),
}


@pytest.mark.parametrize("status_code", [404, 429, 500])
@pytest.mark.parametrize("provider_type", list(_LEGACY_PROBE_BAD_KEY_STATUS))
def test_legacy_probe_non_auth_status_is_unverified_not_failed(
    monkeypatch, provider_type, status_code
):
    assert status_code not in _LEGACY_PROBE_BAD_KEY_STATUS[provider_type]
    _mock_probe(monkeypatch, "a-key", response=_FakeResponse(status_code, {"models": [], "data": []}))

    result = asyncio.run(routes.test_provider_connection(provider_type))

    assert result.success is True
    assert result.verified is False
    assert str(status_code) in result.message


@pytest.mark.parametrize("provider_type", list(_LEGACY_PROBE_BAD_KEY_STATUS))
def test_legacy_probe_own_bad_key_status_still_fails(monkeypatch, provider_type):
    """The uniform rule must not swallow a provider's REAL bad-key signal
    (google's 400 in particular -- it is not 401/403, but it IS the bad-key
    answer and must keep failing, not soften to 'could not verify')."""
    for status_code in _LEGACY_PROBE_BAD_KEY_STATUS[provider_type]:
        _mock_probe(monkeypatch, "a-dead-key", response=_FakeResponse(status_code))

        result = asyncio.run(routes.test_provider_connection(provider_type))

        assert result.success is False, f"{provider_type}/{status_code} must still fail"
        assert result.verified is not True


def test_connection_test_untested_provider_reports_saved_not_verified(monkeypatch):
    """(c) — azure/bedrock/dashscope-shaped providers: a saved key must never
    read as a verified pass again."""
    monkeypatch.setattr(routes, "get_provider_info", lambda _name: SimpleNamespace(is_local=False))
    monkeypatch.setattr(routes, "get_api_key", lambda _name: "some-key")

    result = asyncio.run(routes.test_provider_connection("azure"))

    assert result.success is True
    assert result.verified is False
    assert result.message == "Key saved — this provider cannot be verified from here"


def test_connection_test_key_never_appears_in_response_or_logs(monkeypatch, caplog):
    sentinel = "SENTINEL-NOT-A-KEY"
    _mock_probe(monkeypatch, sentinel, response=_FakeResponse(401))

    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(routes.test_provider_connection("mistral"))

    assert sentinel not in result.message
    assert sentinel not in (result.model_dump_json())
    assert sentinel not in caplog.text


def test_a_slow_keychain_write_does_not_stall_the_engine(monkeypatch):
    """#5257: every connect sends each provider's key; the keychain write shells out to `security`
    (up to 10 s a call). As an `async def` it blocked the event loop, so the launch's health checks
    and library opens waited 20-30 s behind three keys. Now a slow write delays only its own request."""
    import time

    from fastapi import FastAPI

    from fichero_server.api.routes.auth.accounts import _require_owner_or_bootstrap

    # Any slow synchronous step in the handler (a keychain read, a validation) stands in here.
    monkeypatch.setattr(routes, "check_provider_api_key", lambda *_: time.sleep(1.0))
    monkeypatch.setattr(routes, "supply_api_key", lambda *_: None)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[_require_owner_or_bootstrap] = lambda: None

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    key_path = next(r.path for r in routes.router.routes if r.path.endswith("/{provider_type}/api-key"))

    async def run() -> tuple[float, float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://engine") as client:
            start = time.monotonic()

            async def timed(coro):
                await coro
                return time.monotonic() - start

            slow = asyncio.create_task(timed(client.post(key_path.replace("{provider_type}", "openai"),
                                                         json={"api_key": "sk-test"})))
            await asyncio.sleep(0.05)  # the key write is under way
            ping = await timed(client.get("/ping"))
            return ping, await slow

    ping_s, key_s = asyncio.run(run())
    assert key_s >= 0.9, key_s
    assert ping_s < 0.5, f"another request waited {ping_s:.2f}s behind a slow keychain write"


def test_a_supplied_key_is_held_in_memory_and_never_written_to_the_keychain(monkeypatch):
    """Maintainer, 2026-09-28: the app owns its keychain item; the engine writing it back on every
    connect was a second lifetime, a risk to the user's keychain, and (as an async def) a stall of
    the whole engine (#5257). The supply route checks the key and holds it; nothing else."""
    from types import SimpleNamespace

    writes, held = [], []
    monkeypatch.setattr(routes, "set_api_key", lambda *a: writes.append(a) or True)
    monkeypatch.setattr(routes, "keychain_available", lambda: True)
    monkeypatch.setattr(routes, "get_provider_info", lambda _name: SimpleNamespace(is_local=False))
    monkeypatch.setattr(routes, "validate_provider_config", lambda **_: None)
    monkeypatch.setattr(routes, "supply_api_key", lambda provider, key: held.append((provider, key)))

    response = routes.set_provider_api_key("openai", routes.APIKeyRequest(api_key="sk-test"), None)

    assert response.status == "stored"
    assert held == [("openai", "sk-test")]
    assert writes == [], "the supplied key was written to the keychain"
