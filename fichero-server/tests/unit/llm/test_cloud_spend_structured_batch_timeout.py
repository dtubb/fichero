"""The cloud spend cap holds for every kind of call (#5943, #6083): a structured call books its reported cost, not its worst case;
a batch is held against the cap like the calls it is, and one past the cap is refused before anything is sent; a call whose wall
clock ran out books its reservation (the provider may still bill it); a call that answered without usage books its worst case; a
call the provider refused with an error books nothing."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from fichero_server import llm
from fichero_server.llm import LLMConfig, spend, usage
from fichero_server.observability import episodes

IN_RATE, OUT_RATE = 1e-6, 1e-5
USAGE = {"input_tokens": 1000, "output_tokens": 10, "total_tokens": 1010, "input_token_details": {"cache_read": 0}}
ACTUAL = 1000 * IN_RATE + 10 * OUT_RATE
CONFIG = LLMConfig(provider="openrouter", model="m", max_tokens=64)


class Reply(BaseModel):
    ok: str = ""


def _library(tmp_path, monkeypatch, cap):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": IN_RATE, "output_cost_per_token": OUT_RATE, "max_output_tokens": 8192})
    folder = tmp_path / "Cap.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text(f"cloud_allowed: true\ncloud_spend_cap_usd: {cap}\n", encoding="utf-8")
    token = episodes.set_library(str(tmp_path / "Cap.fichero"))
    return str(tmp_path / "Cap.fichero"), token


@pytest.fixture
def library(tmp_path, monkeypatch):
    path, token = _library(tmp_path, monkeypatch, 5)
    yield path
    episodes._episode_library_path.reset(token)


@pytest.fixture
def tiny_cap(tmp_path, monkeypatch):
    path, token = _library(tmp_path, monkeypatch, 0.001)  # below one call's worst case (64 tokens out + default input)
    yield path
    episodes._episode_library_path.reset(token)


def _message(with_usage=True):
    return SimpleNamespace(content="ok", usage_metadata=USAGE if with_usage else None, response_metadata={})


def _install(monkeypatch, model):
    monkeypatch.setattr(llm, "get_langchain_model", lambda _config: model)

    async def ready(*a, **k):
        return None

    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)


class _Structured:
    def __init__(self, behave):
        self.behave = behave

    def with_structured_output(self, schema, **kw):
        outer = self

        class Bound:
            async def ainvoke(self, _messages):
                return await outer.behave(schema)

        return Bound()


def test_a_structured_call_books_its_reported_cost(library, monkeypatch):
    async def answer(schema):
        return {"raw": _message(), "parsed": schema(ok="x"), "parsing_error": None}

    _install(monkeypatch, _Structured(answer))
    asyncio.run(llm.chat_structured("p", Reply, CONFIG))
    assert spend.booked_usd(library) == pytest.approx(ACTUAL)


def test_a_structured_reply_that_would_not_parse_is_still_booked_at_its_cost(library, monkeypatch):
    async def answer(schema):
        return {"raw": _message(), "parsed": None, "parsing_error": "bad"}

    _install(monkeypatch, _Structured(answer))
    with pytest.raises(RuntimeError, match="parse failed"):
        asyncio.run(llm.chat_structured("p", Reply, CONFIG))
    assert spend.booked_usd(library) == pytest.approx(ACTUAL)


def test_an_answer_with_no_usage_books_the_worst_case(library, monkeypatch):
    async def answer(schema):
        return {"raw": _message(with_usage=False), "parsed": schema(ok="x"), "parsing_error": None}

    _install(monkeypatch, _Structured(answer))
    asyncio.run(llm.chat_structured("p", Reply, CONFIG))
    assert spend.booked_usd(library) == pytest.approx(spend.worst_case_usd(CONFIG))


def test_a_provider_error_books_nothing(library, monkeypatch):
    async def answer(schema):
        raise ValueError("400 bad request")

    _install(monkeypatch, _Structured(answer))
    with pytest.raises(Exception):
        asyncio.run(llm.chat_structured("p", Reply, CONFIG))
    assert spend.booked_usd(library) == 0


def test_a_call_that_times_out_books_its_reservation(library, monkeypatch):
    async def answer(schema):
        await asyncio.sleep(10)

    monkeypatch.setattr(llm, "_call_budget", lambda _config: 0.05)
    _install(monkeypatch, _Structured(answer))
    with pytest.raises(RuntimeError, match="provider hang"):
        asyncio.run(llm.chat_structured("p", Reply, CONFIG))
    assert spend.booked_usd(library) == pytest.approx(spend.worst_case_usd(CONFIG))


class _Batch:
    def __init__(self, result=None, hang=False):
        self.result, self.hang, self.sent = result, hang, 0

    async def abatch(self, inputs, **kw):
        self.sent += len(inputs)
        if self.hang:
            await asyncio.sleep(10)
        return self.result if self.result is not None else [_message() for _ in inputs]


def test_a_batch_books_the_cost_of_each_answer(library, monkeypatch):
    _install(monkeypatch, _Batch())
    asyncio.run(llm.chat_batch(["a", "b", "c"], CONFIG))
    assert spend.booked_usd(library) == pytest.approx(3 * ACTUAL)


def test_a_vision_batch_books_the_cost_of_each_answer(library, monkeypatch):
    _install(monkeypatch, _Batch())
    asyncio.run(llm.vision_batch([["data:image/jpeg;base64,AA"], ["data:image/jpeg;base64,AB"]], "p", CONFIG))
    assert spend.booked_usd(library) == pytest.approx(2 * ACTUAL)


def test_a_batch_past_the_cap_is_refused_and_nothing_is_sent(tiny_cap, monkeypatch):
    model = _Batch()
    _install(monkeypatch, model)
    with pytest.raises(spend.CloudSpendRefusedError):
        asyncio.run(llm.chat_batch(["a", "b"], CONFIG))
    assert model.sent == 0 and spend.booked_usd(tiny_cap) == 0


def test_a_vision_batch_past_the_cap_is_refused(tiny_cap, monkeypatch):
    model = _Batch()
    _install(monkeypatch, model)
    with pytest.raises(spend.CloudSpendRefusedError):
        asyncio.run(llm.vision_batch([["data:image/jpeg;base64,AA"]], "p", CONFIG))
    assert model.sent == 0


def test_a_batch_holds_one_worst_case_per_call(library, monkeypatch):
    seen = []

    async def watch(inputs, **kw):
        seen.append(spend._RESERVED.get(library, 0.0))
        return [_message() for _ in inputs]

    model = _Batch()
    model.abatch = watch
    _install(monkeypatch, model)
    asyncio.run(llm.chat_batch(["a", "b", "c"], CONFIG))
    assert seen == [pytest.approx(3 * spend.worst_case_usd(CONFIG))]
    assert spend._RESERVED.get(library, 0.0) == 0


def test_a_batch_that_times_out_books_its_reservation(library, monkeypatch):
    monkeypatch.setattr(llm, "_call_budget", lambda _config: 0.05)
    _install(monkeypatch, _Batch(hang=True))
    results = None
    try:
        results = asyncio.run(llm.chat_batch(["a", "b"], CONFIG))
    except Exception:
        pass
    assert results is None or all(isinstance(r, llm.LLMBatchItemError) for r in results)
    assert spend.booked_usd(library) == pytest.approx(2 * spend.worst_case_usd(CONFIG))


def test_a_batch_whose_items_all_failed_books_nothing(library, monkeypatch):
    _install(monkeypatch, _Batch(result=[ValueError("400"), ValueError("400")]))
    results = asyncio.run(llm.chat_batch(["a", "b"], CONFIG))
    assert all(isinstance(r, llm.LLMBatchItemError) for r in results)
    assert spend.booked_usd(library) == 0
