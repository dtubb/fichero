"""The lifespan stops its loop watcher however the server ends (#6007, api signal hang): the watcher and its dump timer were stopped only
after a clean `yield`, so a body that raised left a thread pinging a loop that was going away."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.api import main as api_main


def _watchers() -> set[threading.Thread]:
    return {t for t in threading.enumerate() if t.name == "loop-lag-watch" and t.is_alive()}


# The real lifespan (threads, executors, a shutdown): a stall ends the test with a thread dump, not the suite.
@pytest.mark.timeout(60, method="thread")
@pytest.mark.asyncio
async def test_a_body_that_raises_still_stops_the_loop_watcher(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    before = _watchers()
    stopped = []
    from fichero_server.core import loop_lag

    real_stop = loop_lag.stop_watchdog
    monkeypatch.setattr(loop_lag, "stop_watchdog", lambda: stopped.append(True) or real_stop())

    with pytest.raises(RuntimeError, match="the body failed"):
        async with api_main.lifespan(api_main.app):
            assert _watchers() - before, "the lifespan started no watcher"
            raise RuntimeError("the body failed")

    assert stopped, "stop_watchdog was not called after the body raised"
    deadline = time.monotonic() + 5  # the watcher leaves at its next ping (0.5 s)
    while _watchers() - before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not (_watchers() - before), "a loop-lag watcher was left running after the body raised"
