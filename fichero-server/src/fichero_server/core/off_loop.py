"""Run a route's synchronous body on a worker thread, still awaitable (#5843).

`async def` routes that read the database run on the event loop; one that waits on the database's transaction gate
behind a long write (Kraken, derivatives) holds `/api/health` with it. `@off_loop` goes directly above a plain `def`
route: FastAPI sees an async function with the same signature, a test can still `await` it, and the body runs in a
thread (with the request's context variables).
"""
from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


def off_loop(fn: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(fn, *args, **kwargs)

    return wrapper
