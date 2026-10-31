"""Counts what keeps failing, by what it says, and names it in `GET /api/health` (`engine.silent.ledger-*`).

One embedding warning was written 380,611 times while every page was saved without a search vector and the engine
looked healthy. A signature (`area|site|kind`, or `logger|message template` for a record the handler sees) that
crosses a rate (RATE_COUNT in RATE_WINDOW_S) or a total (TOTAL) is DEGRADED, and stays listed until QUIET_S pass with
no new hit. The reason is a sentence with a class name and a count: health is unauthenticated, so never a path or id.
Spec: docs/contributor_manual/specs/source/engine-silent-failures.md. No I/O, no thread, never raises, never logs.

ponytail: defaults only (no per-area thresholds, no `ok()` on success), and `LedgerHandler` is not installed
anywhere yet: the handler will be installed by `lifespan` on the root logger (core/logging.py is not the engine's log
set-up; `__main__.py`'s basicConfig is), which is another change's file.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

RATE_COUNT = 20
RATE_WINDOW_S = 60.0
TOTAL = 200
QUIET_S = 300.0
MAX_SIGNATURES = 500

_LOCK = threading.RLock()  # re-entrant: a finalizer that logs a warning while _count holds it must not deadlock the thread
#: What core/log_throttle.py writes for the repeats it held back (template, count): the count is added, not the line.
_COLLAPSED = "%s — repeated %d times in the last minute"
_VARIABLE = re.compile(r"[0-9a-fA-F]{12,}|\d+")


@dataclass
class _Entry:
    area: str
    kind: str
    sentence: str | None
    count: int = 0
    first_at: float = 0.0
    last_at: float = 0.0
    tripped: bool = False
    recent: deque = field(default_factory=lambda: deque(maxlen=RATE_COUNT))


@dataclass(frozen=True)
class Degraded:
    id: str  # a hash of the signature: the signature can hold message text, and health is unauthenticated
    area: str
    reason: str
    count: int
    since: str


_ENTRIES: dict[str, _Entry] = {}


def reset() -> None:
    with _LOCK:
        _ENTRIES.clear()


def note(area: str, site: str, kind: str, *, sentence: str | None = None, now: float | None = None, count: int = 1) -> None:
    """One failure (or `count` of them) at `site` in `area`; `kind` is the exception class name."""
    try:
        _count(f"{area}|{site}|{kind}", area, kind, sentence, time.time() if now is None else now, count)
    except Exception:  # noqa: BLE001 -- a ledger that can fail the work it watches is worse than none
        return


def _count(key: str, area: str, kind: str, sentence: str | None, now: float, count: int) -> None:
    with _LOCK:
        entry = _ENTRIES.get(key)
        if entry is None:
            if len(_ENTRIES) >= MAX_SIGNATURES:
                return
            entry = _ENTRIES[key] = _Entry(area, kind, sentence, first_at=now)
        entry.count += count
        entry.last_at = now
        entry.recent.append(now)
        if entry.count >= TOTAL or (len(entry.recent) == RATE_COUNT and now - entry.recent[0] <= RATE_WINDOW_S):
            entry.tripped = True


def counts() -> dict[str, int]:
    with _LOCK:
        return {key: entry.count for key, entry in list(_ENTRIES.items())}


def degraded(now: float | None = None) -> list[Degraded]:
    now = time.time() if now is None else now
    with _LOCK:
        return [
            Degraded(hashlib.sha1(key.encode()).hexdigest()[:12], e.area, _reason(e), e.count, time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(e.first_at)))
            for key, e in list(_ENTRIES.items())  # a snapshot: a re-entrant note() may add a key mid-loop
            if e.tripped and now - e.last_at <= QUIET_S
        ]


def _reason(entry: _Entry) -> str:
    since = time.strftime("%H:%M", time.localtime(entry.first_at))
    if entry.sentence:
        return f"{entry.sentence} ({entry.kind}). {entry.count} failures since {since}."
    return f"{entry.area} keeps reporting the same problem: {entry.count} times since {since}."


class LedgerHandler(logging.Handler):
    """Counts every WARNING-or-worse record by logger and message template; a collapsed "repeated N times" line adds N."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno < logging.WARNING or getattr(record, "ledgered", False):
                return
            msg, added = str(record.msg), 1
            if msg == _COLLAPSED and len(record.args) == 2:  # type: ignore[arg-type]
                msg, added = str(record.args[0]), int(record.args[1])  # type: ignore[index,arg-type]
            elif not record.args:  # an f-string message: its variable parts are part of the text
                msg = _VARIABLE.sub("N", msg)
            template = msg[:300]
            _count(f"{record.name}|{template}", record.name.rsplit(".", 1)[-1], "", None, record.created, added)
        except Exception:  # noqa: BLE001
            return
