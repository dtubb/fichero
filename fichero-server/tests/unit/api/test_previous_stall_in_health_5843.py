"""The last event-loop stall is written by the watcher and reported once by the next engine (`activity.engine.restart-says-why`, #5843).

WHY: the held engine is the one the app restarts, so health could not say what held it; the next engine says it, once.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest

from fichero_server import startup_warnings
from fichero_server.core import loop_lag
from fichero_server.models import HealthResponse


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
    startup_warnings.set_previous_stall(None)
    before = {t for t in threading.enumerate() if t.name == "loop-lag-watch"}
    yield
    # A watcher's last act is clear_stall(), which reads FICHERO_BASE_PATH: join it while this test's value is still set, not after
    # monkeypatch has put back another test's (#6007, ## 991). Only the watchers THIS test started: one it does not own (the session
    # client's, an earlier leak) is not its to wait for (## 994).
    for watcher in [t for t in threading.enumerate() if t.name == "loop-lag-watch" and t not in before]:
        watcher.join(5)
        assert not watcher.is_alive(), "a loop-lag watcher outlived its test"
    startup_warnings.set_previous_stall(None)


@pytest.fixture
def loop_and_sink():
    """An event loop and a file for the watcher's dump, both closed after the test (#6007): the test left them open, and its
    `dump_file` stayed referenced by a repeating dump timer armed process-wide."""
    import faulthandler

    loop = asyncio.new_event_loop()
    sink = open("/dev/null", "w")
    try:
        yield loop, sink
    finally:
        if loop_lag._dump_enabled():  # a run without the suite's switch: put back what the watcher armed
            faulthandler.cancel_dump_traceback_later()
        loop.close()
        sink.close()


def test_a_stall_is_written_while_held_and_gone_once_the_loop_answers(tmp_path, loop_and_sink):
    loop, sink = loop_and_sink
    ready = threading.Event()
    release = threading.Event()

    # A blocking call made from an engine module: the record names the innermost fichero_server frame (a call made
    # from this test module would be named by its innermost frame, the stdlib's `threading:wait`).
    scope = {"__name__": "fichero_server.held", "release": release}
    exec("def hold():\n    release.wait(60)  # the test releases it; this ceiling cannot expire under a loaded machine", scope)
    hold = scope["hold"]

    async def blocker():
        ready.set()
        hold()

    # start the watcher from inside the loop thread, as the lifespan does
    async def boot():
        return loop_lag.start(loop, ping_seconds=0.05, slow_seconds=0.2, dump_seconds=600, record_seconds=0.1, dump_file=sink)

    def run():
        asyncio.set_event_loop(loop)
        stop = loop.run_until_complete(boot())
        loop.run_until_complete(blocker())
        stop.set()

    t = threading.Thread(target=run)
    t.start()
    assert ready.wait(30)
    path = tmp_path / loop_lag.STALL_FILE
    deadline = time.monotonic() + 30
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    first = json.loads(path.read_text())["seconds"]
    deadline = time.monotonic() + 30  # held on: the record keeps up (seconds are whole, so it takes over 1 s to show)
    while json.loads(path.read_text())["seconds"] <= first and time.monotonic() < deadline:
        time.sleep(0.1)
    assert json.loads(path.read_text())["seconds"] > first, "the record stayed at the first figure while the hold lasted"
    record = json.loads(path.read_text())  # killed mid-stall: this is what the next engine finds
    assert record["frame"] == "fichero_server.held:hold", record
    release.set()
    t.join(30)
    deadline = time.monotonic() + 30
    while path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not path.exists(), "a stall the engine recovered from is not reported after a normal relaunch"
    assert not list(tmp_path.glob("*.tmp"))


def test_the_next_engine_reports_it_once_then_it_is_gone(tmp_path):
    loop_lag.record_stall("fichero_server.kraken_runtime:load_model", 41.2)
    assert loop_lag.take_previous_stall() == "41s in fichero_server.kraken_runtime:load_model"
    assert not (tmp_path / loop_lag.STALL_FILE).exists()
    assert loop_lag.take_previous_stall() is None


def test_it_rides_health_dependencies_without_a_path():
    from fichero_server.api import main as api_main

    startup_warnings.set_previous_stall("41s in fichero_server.kraken_runtime:load_model")
    health = api_main._with_server_proof(HealthResponse(status="healthy"), None)
    value = health.dependencies["previous_stall"]
    assert value == "41s in fichero_server.kraken_runtime:load_model"
    assert "/" not in value and "\\" not in value


def test_a_corrupt_or_path_bearing_file_is_ignored(tmp_path):
    path = tmp_path / loop_lag.STALL_FILE
    path.write_text("{not json")
    assert loop_lag.take_previous_stall() is None
    path.write_text(json.dumps({"frame": "/Users/bob/x.py:load", "seconds": 3}))
    assert loop_lag.take_previous_stall() is None, "a value with a path never reaches health"
    assert not path.exists()


def test_a_stall_with_no_engine_frame_is_named_by_its_innermost_frame():
    import sys

    def outer():
        return loop_lag.culprit(sys._getframe())

    assert outer() == f"{__name__}:outer"


def test_the_loop_watcher_leaves_the_suites_hang_dump_alone_when_told_to(monkeypatch):
    """`FICHERO_LOOP_DUMP=0` (set for the whole suite): starting, pinging and stopping the watcher make no call on faulthandler's one
    process-wide dump timer, so the suite's own hang dump stays armed. Without it the engine re-arms it every heartbeat."""
    import faulthandler

    calls = []
    monkeypatch.setattr(faulthandler, "dump_traceback_later", lambda *a, **k: calls.append("arm"))
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", lambda: calls.append("cancel"))

    def run_one_ping() -> None:
        loop = asyncio.new_event_loop()
        try:
            async def boot():
                stop = loop_lag.start(loop, ping_seconds=0.02, slow_seconds=5, dump_seconds=600)
                await asyncio.sleep(0.2)  # several heartbeats
                stop.set()
                loop_lag.stop_watchdog()

            loop.run_until_complete(boot())
        finally:
            loop.close()

    monkeypatch.setenv("FICHERO_LOOP_DUMP", "0")
    run_one_ping()
    assert calls == [], "the watcher touched the suite's hang dump while FICHERO_LOOP_DUMP=0"
    monkeypatch.delenv("FICHERO_LOOP_DUMP")
    run_one_ping()
    assert "arm" in calls and "cancel" in calls, "the engine's default (a dump armed per heartbeat) must stay"

