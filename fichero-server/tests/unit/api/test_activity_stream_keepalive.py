"""An idle activity stream must SURVIVE its keepalives (2026-08-10).

The old loop re-created and cancelled its two wait-tasks every iteration —
including the keepalive path, whose `continue` still runs the loop's finally
— and cancelling the `anext()` task FINALIZES the tracker's async generator:
the next iteration got StopAsyncIteration and returned. Every idle stream
died at its first 10-second keepalive; every client re-subscribed a second
later, forever (~11s churn in the live log).

Tested against the route's own StreamingResponse body iterator — httpx's
ASGITransport buffers whole bodies, so an SSE cannot be observed through it.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.api.routes.system import activity as activity_module
from fichero_server.db.manager import db_manager


@pytest.mark.anyio
async def test_idle_stream_survives_multiple_keepalives(monkeypatch, test_package):
    # Tiny keepalive so the test observes several ticks in well under a second.
    monkeypatch.setattr(activity_module, "_KEEPALIVE_TIMEOUT", 0.05)

    db = db_manager.get_database(test_package)
    response = await activity_module.stream_activities(db=db, types=None, levels=None)

    keepalives = 0
    iterator = response.body_iterator
    try:
        async with asyncio.timeout(5):
            async for chunk in iterator:
                text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
                if "keepalive" in text:
                    keepalives += 1
                    # Three quiet ticks: the old code could not get past ONE —
                    # its first keepalive finalized the tracker generator and
                    # the stream returned.
                    if keepalives >= 3:
                        break
    finally:
        await iterator.aclose()

    assert keepalives >= 3, "the stream died before its third keepalive"
