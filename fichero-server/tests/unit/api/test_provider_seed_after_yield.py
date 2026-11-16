"""The app database opens and the built-in providers are seeded AFTER the socket answers, and no other request sees it half-done
(`engine.launch.health-answers-before-the-rest`, #6371; replaces the SF9 pin that seed/collapse ran before the yield).

History: #4690 moved the seed off the pre-yield path to get health answering sooner; SF9 (2026-09-18) moved it back because
`loadProviders()` at the app's `markReady()` could read an unseeded database and latch first-launch setup. The race is now closed
by a gate, not by ordering: health answers at once with `starting: ["app-db"]`, and every other request waits for the seed
(`_wait_for_the_app_database`), so the SF9 failure cannot return.
"""

from __future__ import annotations

import asyncio
import threading
import types

import httpx
import pytest

from fichero_server.api import main as api_main


# The test enters the real lifespan (threads, executors, a shutdown): a stall must end the test with a thread dump, not the
# suite (the "thread" method dumps every stack; the repo default "signal" cannot interrupt a blocked executor join).
@pytest.mark.timeout(60, method="thread")
@pytest.mark.asyncio
async def test_health_answers_while_the_seed_is_pending_and_other_requests_wait_for_it(monkeypatch) -> None:
    calls: list[str] = []
    release = threading.Event()

    def blocked_seed() -> None:
        release.wait(30)
        calls.append("seed")

    monkeypatch.setattr(api_main, "_seed_builtin_providers", blocked_seed)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: calls.append("collapse"))

    transport = httpx.ASGITransport(app=api_main.app)
    async with api_main.lifespan(api_main.app), httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = (await client.get("/api/health")).json()
        assert health["starting"] == ["app-db"], health
        assert calls == [], "health answered before the seed finished"

        # The gate is a middleware behind authentication; drive it with the request a signed-in caller would make.
        reached = []

        async def next_handler(_request):
            reached.append("route")
            return "answer"

        request = types.SimpleNamespace(app=api_main.app, scope={"path": "/api/registry"})
        other = asyncio.create_task(api_main._wait_for_the_app_database(request, next_handler))
        await asyncio.sleep(0.5)
        assert not other.done() and reached == [], "a non-health request ran against an unseeded database"

        release.set()
        assert await other == "answer"
        assert calls == ["seed", "collapse"]
        assert (await client.get("/api/health")).json()["starting"] == []
    assert calls == ["seed", "collapse"]
