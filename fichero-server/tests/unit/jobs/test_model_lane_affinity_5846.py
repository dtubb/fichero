"""#5846 follow-up: Kraken keeps the model lane while its pages are queued or in flight; loads and unloads are logged."""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from fichero_server.execution import jobs


def _lane(model="kraken:blla"):
    return SimpleNamespace(loaded_model=model)


def test_a_queued_kraken_page_holds_other_models_off(db, monkeypatch):
    from fichero_server.db.manager import db_manager

    jobs.set_paused(True)  # queued, not run
    try:
        jobs.enqueue(db, "find-lines", "page-1", model="kraken:blla")
        key = str(db.path)
        monkeypatch.setattr(db_manager, "open_database", lambda k: db)
        assert jobs._loaded_work_queued([key], _lane()) is True
        assert jobs._loaded_work_queued([key], _lane("embedder")) is False
    finally:
        jobs.set_paused(False)


def test_a_page_in_the_gate_counts_as_loaded_work():
    from fichero_server.workflows.tools import vision_base

    async def go():
        seen = []
        async with vision_base._KRAKEN_PAGE_GATE:
            seen.append(vision_base._KrakenPageGate.in_flight)
        return seen

    assert asyncio.run(go()) == [1]
    assert vision_base._KrakenPageGate.in_flight == 0
    assert jobs._loaded_work_queued([], _lane("embedder")) is False  # only Kraken's pages hold the lane


def test_a_gate_waiter_that_is_cancelled_is_not_left_counted():
    from fichero_server.workflows.tools import vision_base

    async def go():
        async with vision_base._KRAKEN_PAGE_GATE:
            waiter = asyncio.ensure_future(vision_base._KRAKEN_PAGE_GATE.__aenter__())
            await asyncio.sleep(0.2)
            assert vision_base._KrakenPageGate.in_flight == 2
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)

    asyncio.run(go())
    assert vision_base._KrakenPageGate.in_flight == 0


def test_the_gate_in_flight_holds_the_lane_for_kraken(monkeypatch):
    from fichero_server.workflows.tools import vision_base

    monkeypatch.setattr(vision_base._KrakenPageGate, "in_flight", 1)
    assert jobs._loaded_work_queued([], _lane()) is True


def test_every_unload_logs_its_reason(caplog):
    import fichero_server.llm.kraken_runtime as kraken

    kraken._RESIDENT["read"] = ("m", object())
    with caplog.at_level(logging.INFO, logger=kraken.logger.name):
        kraken.release_resident_models("the lane switches to embedder for job j1")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("model-lane: unload kraken")]
    assert lines == ["model-lane: unload kraken (the lane switches to embedder for job j1)"]


def test_each_load_logs_once_and_a_reuse_logs_nothing(caplog):
    import fichero_server.llm.kraken_runtime as kraken

    kraken._RESIDENT.clear()
    with caplog.at_level(logging.INFO, logger=kraken.logger.name):
        for _ in range(3):  # three pages, one reader
            kraken._resident("read", "model-a", lambda: object())
    loads = [r.getMessage() for r in caplog.records if "model-lane: load kraken" in r.getMessage()]
    assert len(loads) == 1
    kraken._RESIDENT.clear()


def test_an_embed_waits_while_kraken_pages_are_in_flight_even_after_the_quiet_spell(db, monkeypatch):
    """WHY: a slow page outlasts the quiet spell; the embed must not take the lane (and unload Kraken) between
    a run's pages. Same clock-free shape as the quiet-spell test: the light job queued after the embed runs first
    only while the embed is held."""
    from fichero_server.workflows.tools import vision_base

    order = []
    monkeypatch.setattr(jobs, "SWITCH_AFTER_QUIET_SECONDS", 0.0)  # the spell is over
    monkeypatch.setitem(jobs.KINDS, "t-embed", jobs.Kind(run=lambda d, s: order.append("embed"), model="embedder"))
    monkeypatch.setitem(jobs.KINDS, "t-light", jobs.Kind(run=lambda d, s: order.append("light"), model=None))

    jobs.submit(db, "find-lines", "page", model="kraken:blla", fn=lambda: None).result(30)
    monkeypatch.setattr(vision_base._KrakenPageGate, "in_flight", 1)  # the run's next page is on its way
    embed = jobs.enqueue_many(db, "t-embed", ["page"])[0]
    jobs.enqueue_many(db, "t-light", ["page"])[0].result(30)
    assert order == ["light"]

    monkeypatch.setattr(vision_base._KrakenPageGate, "in_flight", 0)
    jobs._scheduler.wake(None)
    embed.result(30)
    assert order == ["light", "embed"]
