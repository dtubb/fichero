"""Pin #4690: the embeddings prewarm must wait for the app's readiness signal.

`_prewarm_embeddings()` used to run immediately after the tool-stack warm-up,
racing the app's own readiness poll for the GIL — measured (2026-09-17, real
launch) as a 5.2s window where the engine's access log shows zero completed
requests of any kind, the exact duration of the embeddings load. The fix defers
the call until `_first_registry_200_signal` fires — set by
`_observe_first_registry_200`, the middleware watching for a real authenticated
`GET /api/registry` 200 (the same leg `EngineReadinessProbe.probe()` checks
last).

This test proves both halves without depending on wall-clock timing beyond a
generous bound: `_prewarm_embeddings` is patched to a call-recorder, and the
test asserts it has NOT been called once the tool-stack warm-up's own log line
appears (via `caplog`, not a raw sleep-and-hope), then drives the readiness
signal directly (`_mark_first_registry_200()` — no live HTTP round trip) and
asserts the recorder fires shortly after.
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
    calls: list[str] = []

    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: calls.append("prewarm"))
    monkeypatch.setattr(api_main, "_should_prewarm_embeddings", lambda: True)

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
