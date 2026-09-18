"""Pin #4690: the embeddings prewarm must wait for readiness AND for quiet.

`_prewarm_embeddings()` used to run immediately after the tool-stack warm-up,
racing the app's own readiness poll for the GIL — measured (2026-09-17, real
launch) as a 5.2s window where the engine's access log shows zero completed
requests of any kind, the exact duration of the embeddings load. The first fix
deferred the call until `_first_registry_200_signal` fires — set by
`_observe_first_registry_200`, the middleware watching for a real authenticated
`GET /api/registry` 200 (the same leg `EngineReadinessProbe.probe()` checks
last).

Run 4 (2026-09-18) showed the readiness signal alone still fires too early:
`markReady()`'s own post-ready authenticated follow-up calls (session refresh,
identity load, library restore) run for several more seconds after "ready",
and those calls' responses landed inside the SAME GIL hold the prewarm had
just started. The second fix adds an idle gate: the prewarm also waits until
no non-`/api/health` request has completed for
`_EMBEDDINGS_PREWARM_IDLE_SECONDS`, re-armed by `_mark_request_activity()`
(called by the same middleware) on every qualifying request.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from fichero_server.api import main as api_main


@pytest.mark.asyncio
async def test_embeddings_prewarm_waits_for_first_registry_200_signal(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Readiness-signal gating, isolated from the idle gate (idle set to ~0
    here so this test proves ONLY the signal ordering, not the idle wait —
    that's `test_embeddings_prewarm_waits_for_idle_after_signal` below)."""
    calls: list[str] = []

    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: calls.append("prewarm"))
    monkeypatch.setattr(api_main, "_should_prewarm_embeddings", lambda: True)
    monkeypatch.setattr(api_main, "_EMBEDDINGS_PREWARM_IDLE_SECONDS", 0.01)

    caplog.set_level(logging.INFO, logger="fichero_server.api.main")

    async with api_main.lifespan(api_main.app):
        # Wait for the REAL tool-stack warm-up to finish — observed via its own
        # stamp, not a guessed sleep — before asserting embeddings hasn't run.
        for _ in range(200):  # up to 10s; real warm-up measured ~1.3s
            if any(
                "workflow tool stack warm-up complete" in r.message
                for r in caplog.records
            ):
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("tool-stack warm-up never completed — can't test ordering")

        assert calls == [], (
            "embeddings prewarm ran before the readiness signal — the #4690 "
            "regression this test pins (it should wait for a real "
            "/api/registry 200, not run unconditionally after tool warm-up)"
        )

        # Drive the signal directly (#4690: same style as
        # test_provider_seed_after_yield.py's blocking-event technique) —
        # no live request needed.
        api_main._mark_first_registry_200()

        for _ in range(100):  # up to 2s
            if calls:
                break
            await asyncio.sleep(0.02)
        assert calls == ["prewarm"], (
            f"embeddings prewarm did not run after the readiness signal fired: {calls!r}"
        )


@pytest.mark.asyncio
async def test_embeddings_prewarm_waits_for_idle_after_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run-4 regression: readiness alone is not enough — traffic must also go
    quiet. Drives `_mark_request_activity()` directly every 0.1s (synthetic
    non-health requests, arriving faster than the idle window can close) and
    asserts the prewarm does NOT run while they keep arriving, then DOES run
    within roughly idle+epsilon after they stop."""
    calls: list[str] = []

    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: calls.append("prewarm"))
    monkeypatch.setattr(api_main, "_should_prewarm_embeddings", lambda: True)
    monkeypatch.setattr(api_main, "_EMBEDDINGS_PREWARM_IDLE_SECONDS", 0.3)

    async with api_main.lifespan(api_main.app):
        api_main._mark_first_registry_200()

        # Simulate arriving requests every 0.1s — well inside the 0.3s idle
        # window, so each one re-arms it before it can close.
        for _ in range(8):
            api_main._mark_request_activity()
            await asyncio.sleep(0.1)
            assert calls == [], (
                "embeddings prewarm ran while requests were still arriving — "
                "the idle gate did not re-arm on activity (#4690 run-4 regression)"
            )

        # Traffic stops here. It should fire within idle (0.3s) + a small
        # margin for scheduling.
        for _ in range(100):  # up to 2s
            if calls:
                break
            await asyncio.sleep(0.02)
        assert calls == ["prewarm"], (
            f"embeddings prewarm did not run after the request stream went idle: {calls!r}"
        )


@pytest.mark.asyncio
async def test_registry_200_middleware_sets_signal_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The middleware, not just the direct-drive helper, must set the signal —
    a non-/api/registry 200, or a /api/registry NON-200, must not."""
    from starlette.requests import Request
    from starlette.responses import Response

    api_main._reset_first_registry_200_signal()

    def _request(path: str) -> Request:
        scope = {"type": "http", "path": path, "headers": []}
        return Request(scope)

    async def _call_next_200(_request: Request) -> Response:
        return Response(status_code=200)

    async def _call_next_401(_request: Request) -> Response:
        return Response(status_code=401)

    # Wrong status on the right path: must NOT set it.
    await api_main._observe_first_registry_200(_request("/api/registry"), _call_next_401)
    assert not api_main._first_registry_200_signal.is_set()

    # Right status, wrong path: must NOT set it.
    await api_main._observe_first_registry_200(_request("/api/health"), _call_next_200)
    assert not api_main._first_registry_200_signal.is_set()

    # Right path, right status: sets it.
    await api_main._observe_first_registry_200(_request("/api/registry"), _call_next_200)
    assert api_main._first_registry_200_signal.is_set()


@pytest.mark.asyncio
async def test_middleware_excludes_health_from_activity() -> None:
    """`/api/health` must not re-arm the idle window — it polls forever, so
    counting it would mean the idle window never closes."""
    from starlette.requests import Request
    from starlette.responses import Response

    def _request(path: str) -> Request:
        return Request({"type": "http", "path": path, "headers": []})

    async def _call_next_200(_request: Request) -> Response:
        return Response(status_code=200)

    api_main._last_request_at = 0.0
    await api_main._observe_first_registry_200(_request("/api/health"), _call_next_200)
    assert api_main._last_request_at == 0.0, "a /api/health 200 must not re-arm the idle window"

    await api_main._observe_first_registry_200(_request("/api/workflows"), _call_next_200)
    assert api_main._last_request_at > 0.0, "a non-health request must re-arm the idle window"
