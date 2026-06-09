"""Per-library change-event SSE endpoint (#1863).

``GET /api/changes/stream`` — one connection per app window. Drains the
per-library subscriber queue fed by ``emit_change`` and yields each
``ChangeEvent`` as an SSE ``data:`` frame, with keepalive comments to hold the
connection open. Mirrors the workflow-run SSE stream
(``api/routes/workflow_execution/core.py``), generalized from one thread-id to
one library path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from fichero.api.change_stream import _change_hub, format_change_sse

logger = logging.getLogger(__name__)

router = APIRouter()

# Seconds to wait for the next event before emitting a keepalive comment.
_KEEPALIVE_TIMEOUT = 30.0


@router.get("/changes/stream")
async def stream_library_changes(
    request: Request,
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
) -> StreamingResponse:
    """Subscribe to the per-library change-event stream.

    Library scope comes from the ``X-Fichero-Library-Path`` header (same as
    every other library route). A window opens one connection and receives a
    ``ChangeEvent`` for every mutation in its library, from any source.
    """
    queue = _change_hub.subscribe(x_fichero_library_path)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Open the stream immediately so the client knows it connected.
        yield ": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_TIMEOUT
                    )
                    yield format_change_sse(event)
                except asyncio.TimeoutError:
                    # Keepalive comment prevents idle-connection timeouts.
                    yield ": keepalive\n\n"
        finally:
            _change_hub.unsubscribe(x_fichero_library_path, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
