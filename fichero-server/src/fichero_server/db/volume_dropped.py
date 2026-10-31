"""A library whose disk went away is said once, in words, and named by a typed 503 (`engine.silent.library-volume-dropped`, #6311).

DuckDB answers every statement on a vanished external drive with an `IOException` ("Input/output error"); each request then
failed as its own 500 with its own stack trace (93 in one log). `Database` hands that error to `outage()`, which raises
`LibraryVolumeNotReachable` for every request, writes ONE log line per library per outage (then a counter in the ledger, area
`library-volume`, one entry per library), and `recovered()` ends the outage when a later statement on that library succeeds.
The message names the library by its display name only, never a path.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import duckdb

from fichero_server.core import failure_ledger

logger = logging.getLogger(__name__)

REASON = "library_volume_not_reachable"
AREA = "library-volume"

_LOCK = threading.Lock()
_DOWN: set[str] = set()


class LibraryVolumeNotReachable(duckdb.IOException):
    """The disk holding this library is not reachable (an external drive that disconnected)."""

    reason = REASON

    def __init__(self, library: str):
        self.library = library
        super().__init__(f'The volume holding the library "{library}" is not reachable (volume disconnected). '
                         "Reconnect it and the library will carry on.")


def is_volume_error(exc: BaseException) -> bool:
    return isinstance(exc, duckdb.IOException) and "input/output error" in str(exc).lower()


def library_name(db_path: str | Path) -> str:
    folder = Path(db_path).parent.name or "library"
    return folder[: -len(".fichero")] if folder.lower().endswith(".fichero") else folder


def outage(db_path: str | Path, exc: BaseException) -> LibraryVolumeNotReachable:
    """The typed error for this request; the first one of an outage writes the log line, every one is counted."""
    name = library_name(db_path)
    key = str(db_path)
    with _LOCK:
        first = key not in _DOWN
        _DOWN.add(key)
    if first:
        logger.error('The volume holding the library "%s" is not reachable (volume disconnected): %s',
                     name, str(exc).splitlines()[0][:200])
    failure_ledger.note(AREA, name, "IOException",
                        sentence=f'The volume holding the library "{name}" is not reachable (volume disconnected)')
    return LibraryVolumeNotReachable(name)


def is_down(db_path: str | Path) -> bool:
    return str(db_path) in _DOWN


def recovered(db_path: str | Path) -> None:
    key = str(db_path)
    with _LOCK:
        was_down = key in _DOWN
        _DOWN.discard(key)
    if was_down:
        logger.warning('The volume holding the library "%s" is back; the library is reachable again.', library_name(db_path))


def reset() -> None:
    with _LOCK:
        _DOWN.clear()
