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
