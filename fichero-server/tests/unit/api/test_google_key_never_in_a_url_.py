"""A Google key is sent in the x-goog-api-key header, never in a URL: httpx logs request URLs at INFO, which put the
key in clear in the engine log (#, runner review 2)."""

import asyncio

import httpx

from fichero_server.api.routes.ai import provider_models

SECRET = "AIza-test-secret-key"


def test_the_google_models_list_sends_its_key_in_a_header(monkeypatch) -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"models": []})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real_client(transport=httpx.MockTransport(answer)))
    monkeypatch.setattr(provider_models, "get_api_key", lambda _provider: SECRET)
    monkeypatch.setattr(provider_models, "_live_cache_get", lambda _provider: None)
    monkeypatch.setattr(provider_models, "_live_cache_put", lambda *_a: None)

    asyncio.run(provider_models._live_google_models())

    assert seen, "the models list made no request"
    assert SECRET not in str(seen[0].url)
    assert seen[0].headers["x-goog-api-key"] == SECRET
