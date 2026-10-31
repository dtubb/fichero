"""A library whose disk went away is said once, in words, and named by a typed 503 (`engine.silent.library-volume-dropped`, #6311).

DuckDB answers every statement on a vanished external drive with an `IOException` ("Input/output error"); each request then
failed as its own 500 with its own stack trace (93 in one log). `Database` hands that error to `outage()`, which raises
`LibraryVolumeNotReachable` for every failing request, writes ONE log line per library per outage (then a counter in the ledger, area
`library-volume`, one entry per library), and `recovered()` ends the outage when a later statement on that library succeeds.
The message names the library by its display name only, never a path.
"""

from __future__ import annotations

import logging
import os
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
        super().__init__(f"The engine can't reach the library's disk for \"{library}\" (an external drive may have disconnected). "
                         "Once the disk answers again the library will carry on.")


def is_volume_error(exc: BaseException) -> bool:
    return isinstance(exc, duckdb.Error) and "input/output error" in str(exc).lower()  # a failed CHECKPOINT is a FatalException


def reachable(db_path: str | Path) -> bool:
    """The library file answers a stat. A vanished mount point does not (a real unplug: the file is simply gone)."""
    try:
        os.stat(db_path)
        return True
    except OSError:
        return False


def classify(db_path: str | Path, exc: BaseException) -> LibraryVolumeNotReachable | None:
    """The typed outage for a DuckDB error that comes from a disk that is not answering, else None.

    A real unplug does not always say "Input/output error": the first failed commit says "Cannot open file ...wal: No such
    file", and later statements say the database was invalidated. So the evidence is the disk, not the message: the text
    EIO, or ANY DuckDB error while the library file cannot be stat-ed. Reads served from DuckDB's cache never get here.
    """
    if not isinstance(exc, duckdb.Error) or isinstance(exc, LibraryVolumeNotReachable):
        return None
    if not reachable(db_path):
        return outage(db_path, exc)
    if is_volume_error(exc) and "invalidated" not in str(exc).lower():  # an invalidated database on a disk that is back is reopened, not refused
        return outage(db_path, exc)
    return None


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
        logger.error('The engine can\'t reach the disk of the library "%s" (an external drive may have disconnected): %s',
                     name, str(exc).splitlines()[0][:200])
    failure_ledger.note(AREA, name, "IOException",
                        sentence=f'The engine can\'t reach the disk of the library "{name}"')
    return LibraryVolumeNotReachable(name)


def is_down(db_path: str | Path) -> bool:
    return str(db_path) in _DOWN


def recovered(db_path: str | Path) -> None:
    if not reachable(db_path):  # a read answered from cache while the disk is still gone does not end the outage
        return
    key = str(db_path)
    with _LOCK:
        was_down = key in _DOWN
        _DOWN.discard(key)
    if was_down:
        logger.warning('The disk of the library "%s" answers again.', library_name(db_path))


def reset() -> None:
    with _LOCK:
        _DOWN.clear()
