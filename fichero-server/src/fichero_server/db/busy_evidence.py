"""Who is inside a DuckDB call right now -- the evidence a busy refusal names (#5185).

Its own module, apart from `db/manager.py`, because this reads thread identity (to leave out the
calling thread) and the connection pool must never touch it: the #2508 guard
(`test_single_connection_guardrail.py`) forbids `get_ident` in the pool module outright, so a
diagnostic there would be indistinguishable from a per-thread pool key.
"""

from __future__ import annotations

import itertools
import logging
import sys
import threading
import time
import traceback
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def threads_in_a_database_call() -> list[str]:
    """Other threads executing a DuckDB statement right now, as "thread: engine frame" -- the
    evidence a busy refusal carries when the writer is a connection the manager does not own
    (#5185): which code, on which thread, is writing at that moment."""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    out = []
    for ident, frame in sys._current_frames().items():
        if ident == threading.get_ident():
            continue
        stack = traceback.extract_stack(frame)
        if not stack or "execute" not in (stack[-1].line or ""):
            continue
        ours = [f for f in stack if "/fichero_server/" in f.filename.replace("\\", "/")]
        where = ours[-1] if ours else stack[-1]
        path = where.filename.replace("\\", "/").rsplit("/fichero_server/", 1)[-1]
        out.append(f"{names.get(ident, ident)}: {path}:{where.lineno} {where.name}")
    return out


# #6236: a statement running past this names itself -- SQL, thread, every thread's stack -- in the
# engine log, once. py-spy needs root the test Macs do not give. The fast path is a dict set and pop.
SLOW_STATEMENT_SECONDS = 10.0
_running: dict[int, tuple[float, str, str]] = {}
_tokens = itertools.count()
_watchdog_lock = threading.Lock()
_watchdog: threading.Thread | None = None


@contextmanager
def watch_statement(sql: str):
    global _watchdog
    if _watchdog is None:
        with _watchdog_lock:
            if _watchdog is None:
                _watchdog = threading.Thread(target=_watch, name="duckdb-slow-statement-watchdog", daemon=True)
                _watchdog.start()
    token = next(_tokens)
    _running[token] = (time.monotonic(), sql, threading.current_thread().name)
    try:
        yield
    finally:
        _running.pop(token, None)


def _watch() -> None:
    reported: set[int] = set()
    while True:
        time.sleep(min(1.0, SLOW_STATEMENT_SECONDS / 4))
        now = time.monotonic()
        reported &= _running.keys()
        for token, (started, sql, thread) in list(_running.items()):
            if token in reported or now - started < SLOW_STATEMENT_SECONDS:
                continue
            reported.add(token)
            names = {t.ident: t.name for t in threading.enumerate()}
            stacks = "\n".join(f"--- {names.get(ident, ident)}\n{''.join(traceback.format_stack(frame))}"
                               for ident, frame in sys._current_frames().items())
            logger.warning("slow DuckDB statement: %.1fs on %s: %s\n%s", now - started, thread, sql[:500], stacks)
