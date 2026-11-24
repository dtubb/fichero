"""#6813 `recipes-run.engine.quits-when-asked`: a shutdown that hangs still ends the engine, and its children, at the deadline."""
from __future__ import annotations

import asyncio
import subprocess
import threading
from unittest.mock import MagicMock

from fichero_server.api import main


def test_a_hung_shutdown_kills_the_engines_children_and_exits(monkeypatch):
    child = subprocess.Popen(["sleep", "60"])
    exited = threading.Event()
    codes = []
    try:
        timer = main._arm_quit_deadline(0.3, exit=lambda code: (codes.append(code), exited.set()))
        assert exited.wait(5), "the deadline passed with the engine still running"
        assert codes == [70]
        assert child.wait(5) == -9, "the forked child was killed with the engine's exit"
        timer.join(1)
    finally:
        child.kill()


def test_a_shutdown_that_ends_in_time_leaves_the_timer_idle(monkeypatch):
    exited = threading.Event()
    timer = main._arm_quit_deadline(30, exit=lambda code: exited.set())
    timer.cancel()
    assert not exited.is_set()


def test_the_teardown_arms_the_deadline_before_any_step(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "_arm_quit_deadline", lambda *a, **k: seen.append("armed") or MagicMock())

    async def step(what, fn):
        seen.append(what)

    monkeypatch.setattr(main, "_step", step)
    asyncio.run(main._teardown(None, parent_watcher=MagicMock(), periodic_snapshot_task=None, bonjour_started=None,
                               tailnet_forward=None, mcp_tools_started=None, warm_started=None))
    assert seen[0] == "armed" and len(seen) > 1


def test_a_teardown_that_finishes_leaves_no_timer_to_kill_the_process(monkeypatch):
    async def step(what, fn):
        pass

    monkeypatch.setattr(main, "_step", step)
    timers = []
    real = main._arm_quit_deadline
    monkeypatch.setattr(main, "_arm_quit_deadline", lambda: timers.append(real(30, exit=lambda code: None)) or timers[-1])
    asyncio.run(main._teardown(None, parent_watcher=MagicMock(), periodic_snapshot_task=None, bonjour_started=None,
                               tailnet_forward=None, mcp_tools_started=None, warm_started=None))
    timers[0].join(1)
    assert not timers[0].is_alive(), "the deadline timer outlived the teardown and would exit the process"
