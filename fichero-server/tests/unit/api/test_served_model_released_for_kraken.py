"""The lane's release of a served model really stops it (`activity.lane.small-mac-one-heavy-model`, #5358).

`_RELEASE["local-model"]` freed nothing, so a 7B MLX model stayed in memory beside Kraken for its 10 idle minutes."""
from __future__ import annotations

import types

from fichero_server.api.routes.ai import local_inference as li
from fichero_server.execution import jobs


class _Process:
    def __init__(self, running: bool) -> None:
        self.running = running

    def is_running(self) -> bool:
        return self.running


class _Manager:
    def __init__(self, ident: str, *, managed: bool, running: bool = True) -> None:
        self.profile = types.SimpleNamespace(id=ident, managed_by_app=managed)
        self.process = _Process(running)
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True
        self.process.running = False


def test_stop_served_models_stops_the_engine_started_running_servers_only(monkeypatch):
    mine, theirs, idle = _Manager("mine", managed=True), _Manager("theirs", managed=False), _Manager("idle", managed=True, running=False)
    monkeypatch.setattr(li, "_MANAGERS", {m.profile.id: m for m in (mine, theirs, idle)})
    monkeypatch.setattr(li, "_IDLE_TIMERS", {})
    assert li.stop_served_models("test") == 1
    assert mine.stopped and not theirs.stopped and not idle.stopped  # a server the person runs is theirs to stop


def test_the_lanes_release_of_a_served_model_is_that_stop(monkeypatch):
    mine = _Manager("mine", managed=True)
    monkeypatch.setattr(li, "_MANAGERS", {"mine": mine})
    monkeypatch.setattr(li, "_IDLE_TIMERS", {})
    jobs._RELEASE["local-model"]("memory: the lane switches to kraken")
    assert mine.stopped


def test_the_release_waits_for_a_call_still_using_the_served_model_and_then_stops_it(monkeypatch):
    """## 822 MED: a Set Up try or a chat may be mid-read on the served model when the lane switches to Kraken; killing it would fail
    that call. The release waits (bounded) for the reads in flight to end, then stops."""
    from fichero_server.llm import local_inference as engine

    mine = _Manager("mine", managed=True)
    monkeypatch.setattr(li, "_MANAGERS", {"mine": mine})
    monkeypatch.setattr(li, "_IDLE_TIMERS", {})
    counts = iter([2, 1, 0])
    monkeypatch.setattr(engine, "reads_in_flight", lambda: next(counts))
    monkeypatch.setattr(li, "_RELEASE_LOOK_AGAIN_SECONDS", 0.0)
    assert li.stop_served_models("test") == 1 and mine.stopped


def test_a_call_that_does_not_end_keeps_the_server_and_the_release_says_why(monkeypatch, caplog):
    from fichero_server.llm import local_inference as engine

    mine = _Manager("mine", managed=True)
    monkeypatch.setattr(li, "_MANAGERS", {"mine": mine})
    monkeypatch.setattr(li, "_IDLE_TIMERS", {})
    monkeypatch.setattr(engine, "reads_in_flight", lambda: 1)
    monkeypatch.setattr(li, "_RELEASE_LOOK_AGAIN_SECONDS", 0.0)
    monkeypatch.setattr(li, "SERVED_RELEASE_WAIT_SECONDS", 0.0)
    with caplog.at_level("WARNING"):
        assert li.stop_served_models("test") == 0
    assert not mine.stopped and "still using it" in caplog.text and "mine" in caplog.text


def test_reads_in_flight_counts_the_live_holders_of_a_read_slot():
    import asyncio

    from fichero_server.llm import local_inference as engine

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        async def read():
            async with engine.local_read_slot(2):
                started.set()
                await release.wait()

        task = asyncio.create_task(read())
        await started.wait()
        during = engine.reads_in_flight()
        release.set()
        await task
        return during, engine.reads_in_flight()

    assert asyncio.run(scenario()) == (1, 0)
