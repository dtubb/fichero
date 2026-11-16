"""A polled result kept until the library changes (#6446).

The app and a paired Mac poll `/api/stats` and the Start plan every second or two; each took 2-5 s on a large library.
The result is kept under the library's change generation (one tick per announced change), so a poll with nothing
changed is a dictionary read. `MAX_AGE_S` bounds a write that announced nothing. `etag` is the same key for ETag/304.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from fichero_server.api.change_stream import library_generation

MAX_AGE_S = 15.0
_CAP = 256
_BOOT = uuid.uuid4().hex[:8]  # a restarted engine counts generations from 0 again: its tags must not repeat the old ones
_held: dict[tuple[str, Any], tuple[int, float, Any]] = {}


def etag(library_path: str, key: Any = "") -> str:
    """Changes with the library's generation, with the engine's run, and every MAX_AGE_S: a 304 never outlives the age ceiling."""
    return f'W/"{_BOOT}-{library_generation(library_path)}-{abs(hash(repr(key))) % 10**8}-{int(time.time() // MAX_AGE_S)}"'


def get(library_path: str, key: Any) -> Any | None:
    held = _held.get((library_path, key))
    if held and held[0] == library_generation(library_path) and time.monotonic() - held[1] < MAX_AGE_S:
        return held[2]
    return None


def put(library_path: str, key: Any, generation: int, value: Any) -> None:
    """`generation` is the one read BEFORE computing: a change during the compute leaves the entry stale, not wrong."""
    if len(_held) >= _CAP:
        _held.pop(next(iter(_held)))
    _held[(library_path, key)] = (generation, time.monotonic(), value)
