"""A slow synchronous action must never hold the event loop (#6355).

WHY: `registry.invoke` is the single synchronous write choke point. An `async def`
handler that calls it directly blocks the loop for the duration of the action —
the change stream, `/api/health` polling and every other client wait behind one
slow write. The handler must hand the call to a worker thread so the loop stays
responsive.

Method: patch `registry.invoke` to sleep 0.5 s, fire `POST /api/notes`
(`create_note`), and — from a watcher thread, once the action is demonstrably in
flight — schedule a trivial coroutine on the same loop and measure how long it
takes to execute.  On a held loop the probe waits ~0.5 s; off the loop it
executes in well under 0.2 s.
"""
from __future__ import annotations

import asyncio
import threading
import time
from urllib.parse import quote

import httpx

from fichero_server.actions.registry import ActionResult, registry
from fichero_server.api.auth import initialize_token
from fichero_server.api.main import app

SLEEP_SECONDS = 0.5
PROBE_OFFSET = 0.05  # well inside the 0.5 s window
MAX_HEALTH_DELAY = 0.2


def _slow_invoke(started: threading.Event):
    def invoke(db, name, raw_params, ctx, *, inverse_of=None):
        started.set()
        time.sleep(SLEEP_SECONDS)
        return ActionResult(
            True, {"title": "held", "body": "held body"}, "audit-test", []
        )

    return invoke


def test_health_is_not_delayed_while_create_note_runs_a_slow_action(
    client, monkeypatch, test_package
):
    started = threading.Event()
    monkeypatch.setattr(registry, "invoke", _slow_invoke(started))

    async def go() -> float:
        transport = httpx.ASGITransport(app=app)
        headers = {
            "X-Fichero-Library-Path": quote(str(test_package), safe="/"),
            "Authorization": f"Bearer {initialize_token()}",
        }
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers=headers
        ) as http:
            loop = asyncio.get_running_loop()
            create = asyncio.create_task(
                http.post("/api/notes", json={"title": "held", "body": "held body"})
            )
            probe_result: dict = {}

            def watch():
                try:
                    assert started.wait(5.0), "invoke never reached"
                    time.sleep(PROBE_OFFSET)
                    # Schedule a trivial coroutine on the event loop and measure
                    # how long until it actually runs.
                    t0 = time.monotonic()
                    fut = asyncio.run_coroutine_threadsafe(
                        asyncio.sleep(0), loop
                    )
                    fut.result(timeout=5)
                    probe_result["took"] = time.monotonic() - t0
                except Exception as exc:
                    probe_result["error"] = repr(exc)

            th = threading.Thread(target=watch, daemon=True)
            th.start()
            cr = await create
            assert cr.status_code == 200, cr.text
            while "took" not in probe_result and "error" not in probe_result:
                await asyncio.sleep(0.001)
            th.join(timeout=2)

        if "error" in probe_result:
            raise AssertionError(f"probe failed: {probe_result['error']}")
        return probe_result["took"]

    took = asyncio.run(go())
    assert took < MAX_HEALTH_DELAY, (
        f"event loop was blocked for {took:.3f}s during a slow action; "
        f"expected < {MAX_HEALTH_DELAY}s"
    )
