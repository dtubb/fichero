"""A cloud call under a project's cap is booked at what it cost (the usage its answer reports), not at its worst case: the usage is
recorded inside the call's slot, while its reservation is open. Found measuring a real run: one 1,058-token call was booked at
$0.015 (its 8,192-token worst case) and a US$0.50 cap was spent after twenty calls."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig, spend, usage
from fichero_server.observability import episodes

IN_RATE, OUT_RATE = 1e-6, 1e-5


class _Answer(SimpleNamespace):
    pass


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": IN_RATE, "output_cost_per_token": OUT_RATE, "max_output_tokens": 8192})
    folder = tmp_path / "Cap.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\ncloud_spend_cap_usd: 5\n", encoding="utf-8")
    token = episodes.set_library(str(tmp_path / "Cap.fichero"))
    yield str(tmp_path / "Cap.fichero")
    episodes._episode_library_path.reset(token)


def _model(monkeypatch):
    message = _Answer(content='["ok"]', usage_metadata={"input_tokens": 1000, "output_tokens": 10, "total_tokens": 1010,
                                                         "input_token_details": {"cache_read": 0}}, response_metadata={})

    class Model:
        async def ainvoke(self, _messages):
            return message

    monkeypatch.setattr(llm, "get_langchain_model", lambda _config: Model())
    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", lambda *a, **k: _noop())


async def _noop():
    return None


def test_a_vision_call_books_its_reported_cost(library, monkeypatch):
    _model(monkeypatch)
    asyncio.run(llm.vision(images=["data:image/jpeg;base64,AAAA"], prompt="p", config=LLMConfig(provider="openrouter", model="m", max_tokens=64)))
    assert spend.booked_usd(library) == pytest.approx(1000 * IN_RATE + 10 * OUT_RATE)


def test_a_chat_call_books_its_reported_cost(library, monkeypatch):
    _model(monkeypatch)
    asyncio.run(llm.chat("hello", LLMConfig(provider="openrouter", model="m", max_tokens=64)))
    assert spend.booked_usd(library) == pytest.approx(1000 * IN_RATE + 10 * OUT_RATE)
