"""Vision result-cache hygiene (2026-08-24, Ann's ensemble re-runs).

Two poisons found live: the cache key omitted sampling params, so the
empty-response retry (which raises max_tokens to get a DIFFERENT answer)
replayed the cached failure in 2ms; and empty answers were cached at all,
so every later RUN failed instantly without one provider call.
"""

from __future__ import annotations

import asyncio

import fichero_server.llm as llm_module
from fichero_server.llm import LLMConfig, _vision_cache_key


def _cfg(**over):
    base = dict(provider="openrouter", model="qwen/qwen3.6-plus")
    base.update(over)
    return LLMConfig(**base)


def test_cache_key_varies_with_sampling_params():
    prompt, images = "transcribe", ["https://x/img.jpg"]
    base = _vision_cache_key(_cfg(), prompt, images)
    assert _vision_cache_key(_cfg(max_tokens=8192), prompt, images) != base
    assert _vision_cache_key(_cfg(temperature=0.9), prompt, images) != base
    assert _vision_cache_key(_cfg(), prompt, images) == base


def test_empty_answer_is_never_cached(monkeypatch):
    calls = 0

    class FakeResponse:
        content = ""
        usage_metadata = None

    class FakeModel:
        async def ainvoke(self, messages):
            nonlocal calls
            calls += 1
            return FakeResponse()

    monkeypatch.setattr(llm_module, "get_langchain_model", lambda config: FakeModel())

    async def no_op(config):
        return None

    monkeypatch.setattr(llm_module, "_ensure_managed_local_provider_ready", no_op)
    llm_module._LLM_RESULT_CACHE.clear()

    config = _cfg()
    for _ in range(2):
        out = asyncio.run(llm_module.vision(
            images=["https://x/img.jpg"], prompt="transcribe", config=config
        ))
        assert out == ""

    # Both calls reached the (fake) provider — the empty first answer was
    # not replayed from cache.
    assert calls == 2
    assert not llm_module._LLM_RESULT_CACHE
