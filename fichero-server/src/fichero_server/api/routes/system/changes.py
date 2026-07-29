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

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from fichero_server.api.library_header import require_library_path
from fichero_server.api.change_stream import _change_hub, format_change_sse, sse_shutdown_event
from fichero_server.api.main import assert_library_read_authorized

logger = logging.getLogger(__name__)

router = APIRouter()

# Seconds to wait for the next event before emitting a keepalive comment.
_KEEPALIVE_TIMEOUT = 10.0


@router.get("/changes/stream")
async def stream_library_changes(
    request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Subscribe to the per-library change-event stream.

    Library scope comes from the ``X-Fichero-Library-Path`` header (same as
    every other library route). A window opens one connection and receives a
    ``ChangeEvent`` for every mutation in its library, from any source.
    """
    if not isinstance(last_event_id, str):
        last_event_id = None
    assert_library_read_authorized(request, x_fichero_library_path)
    subscription = _change_hub.connect(
        x_fichero_library_path,
        last_event_id=last_event_id,
    )
    queue = subscription.queue

    async def event_generator() -> AsyncGenerator[str, None]:
        shutdown_event = sse_shutdown_event()
        # Open the stream immediately so the client knows it connected.
        yield ": connected\n\n"
        try:
            if subscription.resync_event is not None:
                yield format_change_sse(subscription.resync_event)
            for replay_event in subscription.replay_events:
                yield format_change_sse(replay_event)
            while True:
                if shutdown_event.is_set():
                    break
                if await request.is_disconnected():
                    logger.info(
                        "change-stream: client disconnected cleanly lib=%s",
                        x_fichero_library_path,
                    )
                    break
                try:
                    queue_task = asyncio.create_task(queue.get())
                    shutdown_task = asyncio.create_task(shutdown_event.wait())
                    try:
                        done, pending = await asyncio.wait_for(
                            asyncio.wait(
                                {queue_task, shutdown_task},
                                return_when=asyncio.FIRST_COMPLETED,
                            ),
                            timeout=_KEEPALIVE_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        queue_task.cancel()
                        shutdown_task.cancel()
                        await asyncio.gather(queue_task, shutdown_task, return_exceptions=True)
                        yield ": keepalive\n\n"
                        continue
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    if shutdown_task in done:
                        break
                    event = queue_task.result()
                    yield format_change_sse(event)
                except asyncio.TimeoutError:
                    # Keepalive comment prevents idle-connection timeouts.
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            logger.info(
                "change-stream: client cancelled cleanly lib=%s",
                x_fichero_library_path,
            )
            raise
        except GeneratorExit:
            logger.info(
                "change-stream: client closed cleanly lib=%s",
                x_fichero_library_path,
            )
            raise
        except Exception:
            logger.exception("change-stream: SSE failed lib=%s", x_fichero_library_path)
            raise
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
