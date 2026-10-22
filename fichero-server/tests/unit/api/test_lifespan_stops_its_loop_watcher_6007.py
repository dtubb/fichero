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


@pytest.mark.timeout(60, method="thread")
@pytest.mark.asyncio
async def test_the_projects_are_checkpointed_and_closed_when_the_lifespan_ends_badly(monkeypatch) -> None:
    """## 990: the rest of the shutdown was skipped when an exception or a cancel reached the `yield`, leaving every project's WAL to
    replay at the next open. A raising body now still checkpoints and closes the projects, and one failing step does not skip the rest."""
    from fichero_server.db.manager import db_manager

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    seen: list[str] = []
    real_checkpoint, real_close = db_manager.checkpoint_all, db_manager.close_all
    monkeypatch.setattr(db_manager, "checkpoint_all", lambda: seen.append("checkpoint") or real_checkpoint())
    monkeypatch.setattr(db_manager, "close_all", lambda: seen.append("close") or real_close())

    async def unload_models():
        seen.append("unload")

    monkeypatch.setattr(api_main, "shutdown_managed_local_inference_services", unload_models)

    def fail_checkpoint_of_the_app_db():
        seen.append("app-db")
        raise RuntimeError("the app database is busy")

    monkeypatch.setattr("fichero_server.db.app.checkpoint_app_db", fail_checkpoint_of_the_app_db)

    with pytest.raises(RuntimeError, match="the body failed"):
        async with api_main.lifespan(api_main.app):
            raise RuntimeError("the body failed")

    assert seen[:4] == ["checkpoint", "app-db", "close", "unload"], seen  # the failing app-db step did not stop the rest
    assert "close" in seen and "unload" in seen, "a step after the failing one was skipped"
    assert seen.index("checkpoint") < seen.index("close") < seen.index("unload"), "the normal order (projects first) changed"


@pytest.mark.timeout(60, method="thread")
@pytest.mark.asyncio
async def test_a_cancelled_lifespan_still_checkpoints_and_closes_the_projects(monkeypatch) -> None:
    """## 993: the product case of ## 990: the lifespan task is cancelled while the server runs (a forced shutdown), so a CancelledError
    reaches the `yield`. The whole shutdown still runs, and the first step failing (the SSE signal) does not skip the databases."""
    import asyncio

    from fichero_server.db.manager import db_manager

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    seen: list[str] = []
    real_checkpoint, real_close = db_manager.checkpoint_all, db_manager.close_all
    monkeypatch.setattr(db_manager, "checkpoint_all", lambda: seen.append("checkpoint") or real_checkpoint())
    monkeypatch.setattr(db_manager, "close_all", lambda: seen.append("close") or real_close())

    def fail_sse():
        seen.append("sse")
        raise RuntimeError("the stream registry is gone")

    monkeypatch.setattr("fichero_server.api.change_stream.signal_sse_shutdown", fail_sse)
    running = asyncio.Event()

    async def serve():
        async with api_main.lifespan(api_main.app):
            running.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(serve())
    await asyncio.wait_for(running.wait(), 30)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert seen[0] == "sse" and "checkpoint" in seen and seen.index("checkpoint") < seen.index("close"), seen


@pytest.mark.timeout(60, method="thread")
@pytest.mark.asyncio
async def test_every_shutdown_step_runs_on_a_normal_quit_and_none_fails(monkeypatch, caplog) -> None:
    """The teardown moved out of `lifespan` into `_teardown` (## 990) and one step kept a name that had been a local of `lifespan`
    (`tailscale_serve`): a NameError that `_step` logged and carried on from, so Tailscale serve was never stopped at quit. Every step
    runs, none logs a failure, and the Tailscale stop is actually called."""
    import logging

    from fichero_server.security import tailscale_serve

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    stopped = []
    monkeypatch.setattr(tailscale_serve, "stop_for_engine", lambda forward, log=None: stopped.append(forward))

    with caplog.at_level(logging.ERROR, logger=api_main.logger.name):
        async with api_main.lifespan(api_main.app):
            pass

    failed = [r.getMessage() for r in caplog.records if "Shutdown step" in r.getMessage()]
    assert failed == [], f"a shutdown step failed: {failed}"
    assert len(stopped) == 1, "the Tailscale serve stop did not run at quit"
