"""`activity.lane.each-unit-its-own-lane`: an Apple Vision page does not queue behind, or count against, Kraken's pages."""
from __future__ import annotations

import asyncio

from fichero_server.workflows import builder


def _run(coro):
    return asyncio.run(coro)


def test_an_apple_page_does_not_wait_for_krakens_memory_fan_out(monkeypatch):
    """A Kraken page is in flight and memory holds only one: a Kraken page waits, an Apple page goes."""
    monkeypatch.setattr(builder, "_GATE_POLL_SECONDS", 0.01)
    monkeypatch.setattr("fichero_server.llm.kraken_runtime.page_fan_out", lambda cap: 1)
    monkeypatch.setattr(builder, "_local_in_flight", 1)

    async def apple():
        async with builder.vision_slot(neural=True):
            return "read"

    assert _run(asyncio.wait_for(apple(), 2)) == "read"

    async def kraken():
        async with builder.vision_slot():
            return "read"

    try:
        _run(asyncio.wait_for(kraken(), 0.3))
        raise AssertionError("a second Kraken page started although memory holds one")
    except asyncio.TimeoutError:
        pass


def test_an_apple_page_is_not_counted_as_a_local_page_in_flight(monkeypatch):
    monkeypatch.setattr(builder, "_local_in_flight", 0)
    seen = []

    async def go():
        async with builder.vision_slot(neural=True):
            seen.append(builder._local_in_flight)

    _run(go())
    assert seen == [0] and builder._local_in_flight == 0


def test_the_apple_provider_is_the_neural_engine_and_a_cloud_one_is_not():
    from types import SimpleNamespace

    assert builder._is_neural_model(SimpleNamespace(provider="apple")) is True
    assert builder._is_neural_model(SimpleNamespace(provider="Apple")) is True
    assert builder._is_neural_model(SimpleNamespace(provider="kraken")) is False
    assert builder._is_neural_model(None) is False
