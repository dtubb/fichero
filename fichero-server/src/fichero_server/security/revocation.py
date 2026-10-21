"""Who is told when a paired device is revoked (`sharing.revoke-closes-the-stream`, #5913).

The app database cannot import the API layer, so the API registers what to do and `revoke_device` only says which devices.
`end_on_revoke` is the one wrapper every long-lived stream (SSE or NDJSON) of a paired device goes through, so a revoked
guest's stream ends at once whatever route it is on.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterable
from typing import Any

logger = logging.getLogger(__name__)

_listeners: list[Callable[[list[str]], None]] = []


def on_revoked(listener: Callable[[list[str]], None]) -> None:
    if listener not in _listeners:
        _listeners.append(listener)


def off_revoked(listener: Callable[[list[str]], None]) -> None:
    if listener in _listeners:
        _listeners.remove(listener)


def notify(device_ids: Iterable[str]) -> list[Callable[[list[str]], None]]:
    """Tell every listener; one failing listener never undoes a revoke or stops the others. Returns those that failed."""
    ids = list(device_ids)
    failed = []
    for listener in list(_listeners):
        try:
            listener(ids)
        except Exception:  # noqa: BLE001 -- a listener is any stream's callback; the revoke stands either way
            failed.append(listener)
            logger.warning("a revoke listener failed", exc_info=True)
    return failed


def is_revoked(device_id: str) -> bool:
    """Whether the app database says this device is revoked (or gone)."""
    from fichero_server.db.app import get_app_db

    device = get_app_db().get_device(device_id)
    return device is None or bool(device.revoked)


async def end_on_revoke(request: Any, events: AsyncIterator[Any]) -> AsyncIterator[Any]:
    """Yield `events` until the caller's paired device is revoked, then stop (closing `events`). A caller that is not a
    paired device (the host's own window) is passed through untouched. The device is checked again AFTER the listener is
    registered, so a stream that connects in the moment of the revoke cannot slip through."""
    device = getattr(getattr(request, "state", None), "device", None)
    if device is None:
        try:
            async for item in events:
                yield item
        finally:  # a closed stream must close the one under it, or its unsubscribe never runs
            await events.aclose()
        return
    gone = asyncio.Event()
    loop = asyncio.get_running_loop()

    def listener(ids: list[str]) -> None:
        if device.id in ids:
            loop.call_soon_threadsafe(gone.set)

    on_revoked(listener)
    waiter = asyncio.ensure_future(gone.wait())
    pending: asyncio.Future | None = None
    try:
        if is_revoked(device.id):
            return
        while True:
            pending = asyncio.ensure_future(events.__anext__())
            await asyncio.wait({pending, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if gone.is_set():
                return
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield item
    finally:
        off_revoked(listener)
        for task in (waiter, pending):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (waiter, pending) if t is not None), return_exceptions=True)
        await events.aclose()
