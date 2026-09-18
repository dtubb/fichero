"""Pin #4690/SF9: provider seed/collapse must run BEFORE lifespan yields.

History (filename kept for continuity, behaviour flipped 2026-09-18 — SF9):
#4690 originally moved `_seed_builtin_providers()` / `_collapse_duplicate_providers()`
OFF the pre-yield path onto the post-bind warm-up executor, to get two blocking
DuckDB round trips off the critical path to "health can answer". That measured
~147ms — negligible — and it opened a real cross-commit race: `loadProviders()`
at `markReady()` (Swift, `AppState+Readiness.swift`) is fire-and-forget and can
call `GET /api/providers` before this seed lands on a FRESH install (empty
app.duckdb, no rows yet), reading `[]` and latching
`isFirstLaunchProviderSetup = true` (`AppState+Providers.swift`) permanently
for the session — a user who will have a provider a moment later sees
first-launch setup. SF9 reverted the move: the negligible cost is worth
removing the race STRUCTURALLY (seed/collapse complete before the socket can
even answer, so no client request can ever race them) rather than adding a
second readiness signal for a ~147ms saving.

This test pins the CURRENT (reverted) behaviour: seed/collapse run
SYNCHRONOUSLY in the lifespan coroutine, in order, and have ALREADY completed
by the time `async with lifespan(app):` hands control to its body — no
threading/event trickery needed here (unlike the embeddings-prewarm test),
because there is no longer a background thread race to synchronize with; a
regression back to the post-yield executor would show up as `calls == []` (or
partial) at the assertion point below, since Python's single-threaded
coroutine execution means everything before `yield` in the generator body has
unconditionally run by the time `__aenter__` returns.
"""

from __future__ import annotations

import pytest

from fichero_server.api import main as api_main


@pytest.mark.asyncio
async def test_provider_seed_and_collapse_run_before_yield(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: calls.append("seed"))
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: calls.append("collapse"))
    # Avoid the real (slow, network-fetching) embeddings warm-up; unrelated
    # to what this test pins (it's already deferred past readiness, #4690).
    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: None)

    async with api_main.lifespan(api_main.app):
        assert calls == ["seed", "collapse"], (
            f"expected seed+collapse to have ALREADY completed before yield, got {calls!r} — "
            "if this is [] or partial, seed/collapse moved back to the post-yield warm-up "
            "executor, reintroducing the SF9 loadProviders()/isFirstLaunchProviderSetup race"
        )
    # Unaffected by shutdown — still exactly these two, in order.
    assert calls == ["seed", "collapse"]
