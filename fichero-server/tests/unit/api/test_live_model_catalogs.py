"""Live model catalogs (2026-08-25): OpenRouter and Hugging Face lists come
from the providers' OWN endpoints, with LiteLLM's static snapshot as the
fallback — LiteLLM is for pricing, not the catalog (Daniel: 'only 3 models…
are we loading live from providers?')."""

import pytest

from fichero_server.api.routes.ai import provider_models as pm


@pytest.mark.anyio
async def test_live_catalog_wins_when_it_answers(monkeypatch):
    async def fake_live():
        return [{"model_id": "openrouter/live-model", "full_name": "Live Model",
                 "provider": "openrouter", "mode": "chat"}]

    monkeypatch.setitem(pm._LIVE_CATALOG_FETCHERS, "openrouter", fake_live)
    result = await pm.list_models_for_provider("openrouter", search=None, vision_only=False, sort_by="name")
    ids = [m.model_id for m in result.items]
    assert "openrouter/live-model" in ids


@pytest.mark.anyio
async def test_live_failure_falls_back_to_the_static_registry(monkeypatch):
    async def broken():
        raise RuntimeError("network down")

    monkeypatch.setitem(pm._LIVE_CATALOG_FETCHERS, "huggingface", broken)
    result = await pm.list_models_for_provider("huggingface", search=None, vision_only=False, sort_by="name")
    ids = [m.model_id for m in result.items]
    # The curated trio survives — the list is never WORSE than before.
    assert "Qwen/Qwen3-VL-8B-Instruct" in ids


def test_cache_round_trip():
    pm._live_cache_put("x", [{"model_id": "m"}])
    assert pm._live_cache_get("x") == [{"model_id": "m"}]
    assert pm._live_cache_get("missing") is None
