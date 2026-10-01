"""Pin #4690: the after-ready warm-up must wait for readiness AND for quiet -- and,
since #5283 (ruled 2026-10-01), it never loads the embedding model (about 1.5 GB).

The history below is of the embeddings load this warm-up used to run; the gates it
describes now hold the workflow tool-stack warm-up, which still runs here (#5228).

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
`_WARM_IDLE_SECONDS` (then `_EMBEDDINGS_PREWARM_IDLE_SECONDS`), re-armed by `_mark_request_activity()`
(called by the same middleware) on every qualifying request.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from fichero_server.api import main as api_main
from fichero_server.db import embeddings


def _watch_model_loads(monkeypatch) -> list[str]:
    loads: list[str] = []
    monkeypatch.setattr(embeddings, "_get_shared_embedder", lambda name, _cache: loads.append(name))
    return loads


def _warmed(caplog) -> bool:
    return any("workflow tool stack warm-up start" in r.message for r in caplog.records)


async def _until_warmed(caplog) -> None:
    for _ in range(500):  # up to 10s: the real tool-stack warm-up takes ~1.3 s
        if _warmed(caplog):
            break
        await asyncio.sleep(0.02)
    assert _warmed(caplog), "the warm-up never ran after the app was ready and quiet"


@pytest.mark.asyncio
async def test_warm_up_waits_for_first_registry_200_signal_and_loads_no_model(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Readiness-signal gating, isolated from the idle gate (idle set to ~0
    here so this test proves ONLY the signal ordering, not the idle wait —
    that's `test_warm_up_waits_for_idle_after_signal_and_loads_no_model` below)."""
    loads = _watch_model_loads(monkeypatch)
    monkeypatch.setattr(api_main, "_WARM_IDLE_SECONDS", 0.01)

    caplog.set_level(logging.INFO, logger="fichero_server.api.main")

    async with api_main.lifespan(api_main.app):
        # #5228: NOTHING warms before the readiness signal -- neither the tool
        # stack (it used to start at bind, holding the GIL through the app's
        # launch loads) nor embeddings. Give a bind-time warm-up time to show.
        await asyncio.sleep(0.3)
        assert not any(
            "workflow tool stack warm-up start" in r.message for r in caplog.records
        ), "the tool-stack warm-up started before the app was ready (#5228 regression)"


        # Drive the signal directly (#4690: same style as
        # test_provider_seed_after_yield.py's blocking-event technique) —
        # no live request needed. Held on app.state (2026-09-19 follow-up:
        # a bare module global raced across concurrent lifespans), so the
        # same `app` object `lifespan()` above was entered with.
        api_main._mark_first_registry_200(api_main.app)

        await _until_warmed(caplog)
        assert loads == [], "the embedding model was loaded at launch (#5283 regression)"


@pytest.mark.asyncio
async def test_warm_up_waits_for_idle_after_signal_and_loads_no_model(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Run-4 regression: readiness alone is not enough — traffic must also go
    quiet. Drives `_mark_request_activity()` directly every 0.1s (synthetic
    non-health requests, arriving faster than the idle window can close) and
    asserts the prewarm does NOT run while they keep arriving, then DOES run
    within roughly idle+epsilon after they stop."""
    loads = _watch_model_loads(monkeypatch)
    monkeypatch.setattr(api_main, "_WARM_IDLE_SECONDS", 0.3)
    caplog.set_level(logging.INFO, logger="fichero_server.api.main")

    async with api_main.lifespan(api_main.app):
        api_main._mark_first_registry_200(api_main.app)

        # Simulate arriving requests every 0.1s — well inside the 0.3s idle
        # window, so each one re-arms it before it can close.
        for _ in range(8):
            api_main._mark_request_activity(api_main.app)
            await asyncio.sleep(0.1)
            assert not _warmed(caplog), (
                "the warm-up ran while requests were still arriving — "
                "the idle gate did not re-arm on activity (#4690 run-4 regression)"
            )

        # Traffic stops here. It should fire within idle (0.3s) + a small
        # margin for scheduling.
        await _until_warmed(caplog)
        assert loads == [], "the embedding model was loaded once the app went quiet (#5283 regression)"


@pytest.mark.asyncio
async def test_registry_200_middleware_sets_signal_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The middleware, not just the direct-drive helper, must set the signal —
    a non-/api/registry 200, or a /api/registry NON-200, must not."""
    from starlette.requests import Request
    from starlette.responses import Response

    api_main._reset_first_registry_200_signal(api_main.app)

    # A real ASGI scope always carries "app" (Starlette sets it before
    # dispatch); the middleware reads `request.app.state` (2026-09-19
    # follow-up), so a synthetic scope for this direct test must too.
    def _request(path: str) -> Request:
        scope = {"type": "http", "path": path, "headers": [], "app": api_main.app}
        return Request(scope)

    async def _call_next_200(_request: Request) -> Response:
        return Response(status_code=200)

    async def _call_next_401(_request: Request) -> Response:
        return Response(status_code=401)

    # Wrong status on the right path: must NOT set it.
    await api_main._observe_first_registry_200(_request("/api/registry"), _call_next_401)
    assert not api_main.app.state.first_registry_200_signal.is_set()

    # Right status, wrong path: must NOT set it.
    await api_main._observe_first_registry_200(_request("/api/health"), _call_next_200)
    assert not api_main.app.state.first_registry_200_signal.is_set()

    # Right path, right status: sets it.
    await api_main._observe_first_registry_200(_request("/api/registry"), _call_next_200)
    assert api_main.app.state.first_registry_200_signal.is_set()


@pytest.mark.asyncio
async def test_middleware_excludes_health_from_activity() -> None:
    """`/api/health` must not re-arm the idle window — it polls forever, so
    counting it would mean the idle window never closes."""
    from starlette.requests import Request
    from starlette.responses import Response

    def _request(path: str) -> Request:
        return Request({"type": "http", "path": path, "headers": [], "app": api_main.app})

    async def _call_next_200(_request: Request) -> Response:
        return Response(status_code=200)

    api_main.app.state.last_request_at = 0.0
    await api_main._observe_first_registry_200(_request("/api/health"), _call_next_200)
    assert api_main.app.state.last_request_at == 0.0, "a /api/health 200 must not re-arm the idle window"

    await api_main._observe_first_registry_200(_request("/api/workflows"), _call_next_200)
    assert api_main.app.state.last_request_at > 0.0, "a non-health request must re-arm the idle window"
