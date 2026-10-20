"""Model calls for several pages at once, results back in page order (`runtime.cloud-extractors.pages-together`, #5955).

A step that reads each page's text with a model (names, claims) used to ask for one page, wait, write it, and ask for the
next. `ahead` starts the calls of the next pages while the one in front is written: at most `width` in flight, the loop that
writes still sees the pages one by one in their own order, so what is written and in what order does not change."""

from __future__ import annotations

import asyncio
import os
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from typing import Any, TypeVar

T = TypeVar("T")
R = TypeVar("R")

#: How many pages a step asks a model about at once when the model is hosted (about the step's cloud width), and when it
#: is served on this Mac (where the engine's own slots bound it again).
CLOUD_WIDTH = 10
LOCAL_WIDTH = 3


def extract_width(llm_config: Any) -> int:
    """`FICHERO_EXTRACT_MAX_IN_FLIGHT` if set, else the cloud width for a hosted model and the local width otherwise."""
    raw = os.environ.get("FICHERO_EXTRACT_MAX_IN_FLIGHT")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    from fichero_server.workflows.builder import _is_remote_model

    return CLOUD_WIDTH if _is_remote_model(llm_config) else LOCAL_WIDTH


async def ahead(items: Iterable[T], start: Callable[[T], Awaitable[R]], width: int) -> AsyncIterator[tuple[T, R]]:
    """Yield (item, start(item)'s result) in the order of `items`, with up to `width` calls in flight. `items` is read lazily,
    only as far as the window needs. A call that raises raises here, at its own page, as an inline call did; calls still
    running when the consumer stops (or one raises) are cancelled."""
    window: deque[tuple[T, asyncio.Future[R]]] = deque()
    try:
        for item in items:
            window.append((item, asyncio.ensure_future(start(item))))
            if len(window) >= max(1, width):
                first, call = window.popleft()
                yield first, await call
        while window:
            first, call = window.popleft()
            yield first, await call
    finally:
        for _item, call in window:
            call.cancel()
            call.add_done_callback(lambda done: done.cancelled() or done.exception())  # a call nobody awaits is not reported
