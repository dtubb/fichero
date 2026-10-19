"""The vision-level Kraken page gate lets in as many pages as the seam does (`source.read.two-pages-at-once`, review 341
and 343): the lane's Kraken jobs are enqueued from inside it, so a gate of one never even queued two pages."""
from __future__ import annotations

import asyncio

from fichero_server.llm import kraken_runtime
from fichero_server.workflows.tools import vision_base


def _run(coro):
    return asyncio.run(coro)


def test_two_pages_are_inside_when_the_seam_allows_two_and_the_third_waits(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "pages_at_once", lambda person: 2)
    gate = vision_base._KRAKEN_PAGE_GATE

    async def go():
        await gate.__aenter__()
        await gate.__aenter__()
        third = asyncio.ensure_future(gate.__aenter__())
        await asyncio.sleep(0.2)
        assert vision_base._KrakenPageGate._inside == 2 and not third.done()
        assert vision_base._KrakenPageGate.in_flight == 3
        await gate.__aexit__(None, None, None)
        await asyncio.wait_for(third, 2)
        assert vision_base._KrakenPageGate._inside == 2
        await gate.__aexit__(None, None, None)
        await gate.__aexit__(None, None, None)

    _run(go())
    assert vision_base._KrakenPageGate._inside == 0 and vision_base._KrakenPageGate.in_flight == 0


def test_one_page_at_a_time_when_the_seam_allows_one(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "pages_at_once", lambda person: 1)
    gate = vision_base._KRAKEN_PAGE_GATE

    async def go():
        await gate.__aenter__()
        second = asyncio.ensure_future(gate.__aenter__())
        await asyncio.sleep(0.2)
        assert not second.done()
        await gate.__aexit__(None, None, None)
        await asyncio.wait_for(second, 2)
        await gate.__aexit__(None, None, None)

    _run(go())
    assert vision_base._KrakenPageGate._inside == 0


def _gate_asks(monkeypatch, starter_is_a_person: bool) -> list[bool]:
    """What the gate asks `pages_at_once`, from a workflow thread with no `jobs._current`, under a run whose starter is
    (or is not) a person (review 344)."""
    import threading

    from fichero_server.db import db_manager
    from fichero_server.execution import jobs

    asked: list[bool] = []
    monkeypatch.setattr(kraken_runtime, "pages_at_once", lambda person: asked.append(person) or (2 if person else 1))
    monkeypatch.setattr(db_manager, "get_database", lambda path: object())
    monkeypatch.setattr(jobs, "person_waits_on", lambda db, task_id: starter_is_a_person)

    def workflow_thread():
        assert not hasattr(jobs._current, "person")  # nothing set it on this thread
        async def go():
            vision_base.note_who_started_the_run("run-1", "/lib")
            await vision_base._KRAKEN_PAGE_GATE.__aenter__()
            await vision_base._KRAKEN_PAGE_GATE.__aexit__(None, None, None)
        asyncio.run(go())

    t = threading.Thread(target=workflow_thread, name="workflow-run-1")
    t.start()
    t.join()
    return asked


def test_a_persons_run_asks_for_two_pages_from_a_workflow_thread(monkeypatch):
    assert _gate_asks(monkeypatch, True) == [True]


def test_an_automatic_run_asks_for_one_page_from_a_workflow_thread(monkeypatch):
    assert _gate_asks(monkeypatch, False) == [False]
