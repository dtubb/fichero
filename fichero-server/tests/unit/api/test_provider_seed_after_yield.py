"""Pin #4690: provider seed/collapse must run AFTER lifespan yields, not before.

`_seed_builtin_providers()` / `_collapse_duplicate_providers()` used to run
inline in the lifespan's pre-yield body, gating `yield` (and therefore gating
when uvicorn finishes startup and `/api/health` can answer) on two blocking
DuckDB round trips. #4690 moved both calls into `_warm_workflow_stack()`, the
existing post-bind warm-up that already runs on an executor thread and is
already awaited on shutdown (`warm_started`) — so the DB work no longer sits
on the critical path, but shutdown still guarantees it completed.

This test proves both halves of that claim without relying on wall-clock
timing: `_seed_builtin_providers` is patched to block on a `threading.Event`
until the test explicitly releases it, so if either function still ran
SYNCHRONOUSLY pre-yield (the old, unwanted behaviour), entering the `async
with lifespan(...)` body would never happen until the event is released —
which happens INSIDE that body. A regression therefore deadlocks this test
against the event's timeout instead of silently passing.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from fichero_server.api import main as api_main


@pytest.mark.asyncio
async def test_provider_seed_and_collapse_run_after_yield_not_before(monkeypatch) -> None:
    calls: list[str] = []
    release = threading.Event()

    def fake_seed() -> None:
        calls.append("seed-start")
        # Blocks the WARM-UP EXECUTOR THREAD only. If this ran inline in the
        # pre-yield coroutine instead (the regression this test guards), it
        # would block the event loop itself and `async with` would never
        # reach its body until the 5s timeout elapses — see module docstring.
        release.wait(timeout=5)
        calls.append("seed-done")

    def fake_collapse() -> None:
        calls.append("collapse")

    monkeypatch.setattr(api_main, "_seed_builtin_providers", fake_seed)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", fake_collapse)
    # Avoid the real (slow, network-fetching) embeddings warm-up; unrelated
    # to what this test pins.
    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: None)

    async with api_main.lifespan(api_main.app):
        # Startup (pre-yield) already completed — we are inside the
        # `async with` body — while the warm-up thread is still blocked
        # mid-`_seed_builtin_providers`. Give the executor thread a brief
        # window to actually start (it races the coroutine reaching this
        # point), then assert it has NOT been allowed to finish.
        for _ in range(50):
            if calls:
                break
            await asyncio.sleep(0.02)
        assert calls == ["seed-start"], (
            f"expected seed to be mid-flight (blocked) at the yield point, got {calls!r} — "
            "if this is ['seed-start', 'seed-done', ...] already, seed/collapse ran "
            "synchronously pre-yield again (the #4690 regression this test pins)"
        )
        release.set()
    # Lifespan __aexit__ awaits `warm_started` before returning, so by
    # here both calls must have completed in order.
    assert calls == ["seed-start", "seed-done", "collapse"]
