"""/api/health answers in under a second while a (faked) slow model load and read are in progress, and a held-up event
loop is logged with its stack (#5843, `contract.health-fast-under-load`)."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from fichero_server.api import main
from fichero_server.core import loop_lag


def test_health_answers_within_a_second_while_a_slow_load_and_read_run_off_the_loop():
    async def go() -> float:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://engine") as client:
            slow_load = asyncio.create_task(asyncio.to_thread(time.sleep, 2.5))  # a model loading in a thread
            slow_read = asyncio.create_task(asyncio.to_thread(time.sleep, 2.5))  # a page being read
            await asyncio.sleep(0.1)
            started = time.monotonic()
            response = await client.get("/api/health")
            took = time.monotonic() - started
            assert response.status_code == 200 and response.json()["status"] == "healthy"
            await asyncio.gather(slow_load, slow_read)
            return took

    assert asyncio.run(go()) < 1.0


def test_the_provisioned_runtime_versions_are_held_not_read_on_every_poll(monkeypatch):
    reads = []
    monkeypatch.setattr(main, "_held_dependencies", None)
    monkeypatch.setattr(main, "_read_dependency_versions", lambda: reads.append(1) or {"kraken": "7"})

    for _ in range(5):
        assert main._dependency_versions() == {"kraken": "7"}

    assert len(reads) == 1


def test_a_loop_held_up_by_a_blocking_call_is_logged_with_where_it_was(caplog):
    async def go() -> None:
        stop = loop_lag.start(asyncio.get_running_loop(), ping_seconds=0.05, slow_seconds=0.2)
        await asyncio.sleep(0.1)
        time.sleep(0.6)  # a blocking call on the loop: what the log must name
        await asyncio.sleep(0.2)
        stop.set()

    with caplog.at_level(logging.WARNING, logger=loop_lag.logger.name):
        asyncio.run(go())

    held = [r.getMessage() for r in caplog.records if "event loop was held" in r.getMessage()]
    assert held and "time.sleep" in held[0]
