"""One query in flight per poll route (#5843).

The app polls Activity, the recipe run and the stats every second or two. A poll that takes longer than that was
answered by a second, third, tenth identical query, and a dozen DuckDB threads fought Kraken for the GIL. `@single_flight`
runs a route once per (library, arguments) at a time: a caller that arrives while it runs awaits the same answer.
It also logs a route that takes over `SLOW_MS`, with how many callers the one query served.

Goes directly above the route body (below `@router.get`). The body may be `async def` or plain `def` (run in a thread).
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

SLOW_MS = 200


def _key(route: str, kwargs: dict[str, Any]) -> tuple[Any, ...]:
    parts: list[Any] = [route]
    for name in sorted(kwargs):
        value = kwargs[name]
        path = getattr(value, "path", None)
        parts.append((name, str(path) if path is not None and hasattr(value, "execute") else repr(value)))
    return tuple(parts)


def _rows(result: Any) -> int | None:
    items = getattr(result, "items", result)
    try:
        return len(items) if not callable(items) else None
    except TypeError:
        return None


def single_flight(fn: Callable[..., Any]) -> Callable[..., Any]:
    route = f"{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}"
    flights: dict[tuple[Any, ...], asyncio.Future] = {}
    stats = {"served": 0}

    async def run(args: tuple[Any, ...], kwargs: dict[str, Any], key: tuple[Any, ...]) -> Any:
        started = time.monotonic()
        try:
            if inspect.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = await asyncio.to_thread(fn, *args, **kwargs)
        finally:
            flights.pop(key, None)
        ms = (time.monotonic() - started) * 1000
        if ms > SLOW_MS:
            logger.info("poll %s took %d ms (%s rows); %d callers were served from a running query so far",
                        route, ms, _rows(result), stats["served"])
        return result

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        key = _key(route, kwargs) if not args else None
        if key is None:  # called positionally (a test): no sharing
            return await run(args, kwargs, ("positional", id(args)))
        flight = flights.get(key)
        if flight is None:
            flight = flights[key] = asyncio.ensure_future(run(args, kwargs, key))
        else:
            stats["served"] += 1
        return await asyncio.shield(flight)

    wrapper.single_flight_stats = stats  # type: ignore[attr-defined]
    return wrapper
