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

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from fichero_server.api.library_header import require_library_path
from fichero_server.api.auth import _is_loopback_request
from fichero_server.api.change_stream import ChangeEvent, _change_hub, format_change_sse, sse_shutdown_event
from fichero_server.api.main import assert_library_read_authorized
from fichero_server.security import revocation

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
        device_id=getattr(getattr(request.state, "device", None), "id", None),
    )
    queue = subscription.queue
    device_id = getattr(getattr(request.state, "device", None), "id", None)
    if device_id and revocation.is_revoked(device_id):  # revoked in the moment it connected: after subscribing, so none slips through (#5913)
        _change_hub.unsubscribe(x_fichero_library_path, queue)
        raise HTTPException(status_code=401, detail="this device was removed")

    async def event_generator() -> AsyncGenerator[str, None]:
        shutdown_event = sse_shutdown_event()
        # A guest (anything not loopback) is told once that the host stopped, before the stream ends
        # (sharing.off-closes-the-guest, #5731); the host's own windows just end.
        guest = not _is_loopback_request(request)

        def stopped_frame() -> str:
            return format_change_sse(ChangeEvent(type="sharing.stopped"))

        # Open the stream immediately so the client knows it connected.
        yield ": connected\n\n"
        try:
            if subscription.resync_event is not None:
                yield format_change_sse(subscription.resync_event)
            for replay_event in subscription.replay_events:
                yield format_change_sse(replay_event)
            while True:
                if shutdown_event.is_set():
                    if guest:
                        yield stopped_frame()
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
                        # A loop stall past the keepalive lets the queue read finish in the
                        # same tick the timeout fires; cancel() is then a no-op and the
                        # event would be dropped. Send it.
                        if queue_task.done() and not queue_task.cancelled():
                            late = queue_task.result()
                            yield format_change_sse(late)
                            if late.type == "sharing.revoked":
                                break
                        yield ": keepalive\n\n"
                        continue
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    if shutdown_task in done:
                        if guest:
                            yield stopped_frame()
                        break
                    event = queue_task.result()
                    yield format_change_sse(event)
                    if event.type == "sharing.revoked":  # this device was removed: the stream ends (#5913)
                        break
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
