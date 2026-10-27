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


#: Undo held past this share of an instance's memory limit: a transaction or a result left open keeps old row
#: versions alive, and once they spill every row fetch reads them back from disk (#6236; no one statement is slow).
HELD_VERSIONS_SHARE = 0.25


def _all_stacks() -> str:
    names = {t.ident: t.name for t in threading.enumerate()}
    return "\n".join(f"--- {names.get(ident, ident)}\n{''.join(traceback.format_stack(frame))}"
                     for ident, frame in sys._current_frames().items())


def _check_held_versions(alarmed: set[str]) -> None:
    """Say once, per open instance, when its undo passes the share; again only after it fell back under it."""
    from fichero_server.core import duckdb_session

    with duckdb_session._instances_lock:
        instances = [(key, list(refs)) for key, refs in duckdb_session._instances.items()]
    for key, refs in instances:
        conn = duckdb_session._live(refs)
        if conn is None:
            continue
        held, limit = conn.cursor().execute(
            "SELECT (SELECT coalesce(sum(memory_usage_bytes), 0) FROM duckdb_memory() WHERE tag = 'TRANSACTION'), "
            "current_setting('memory_limit')").fetchall()[0]
        limit_bytes = duckdb_session.parse_size(limit.replace(" ", ""))
        if held < limit_bytes * HELD_VERSIONS_SHARE:
            alarmed.discard(key)
        elif key not in alarmed:
            alarmed.add(key)
            logger.warning("DuckDB holds %d MiB of old row versions for %s (memory limit %s, %d open instance(s)): "
                           "a transaction or a result left open keeps them\n%s",
                           held // 1024**2, key, limit, len(instances), _all_stacks())


def _watch() -> None:
    reported: set[int] = set()
    alarmed: set[str] = set()
    failed: set[str] = set()
    while True:
        time.sleep(min(1.0, SLOW_STATEMENT_SECONDS / 4))
        now = time.monotonic()
        reported &= _running.keys()
        for token, (started, sql, thread) in list(_running.items()):
            if token in reported or now - started < SLOW_STATEMENT_SECONDS:
                continue
            reported.add(token)
            logger.warning("slow DuckDB statement: %.1fs on %s: %s\n%s", now - started, thread, sql[:500], _all_stacks())
        try:
            _check_held_versions(alarmed)
        except Exception as exc:  # noqa: BLE001 -- a watchdog that dies says nothing ever again
            if str(exc) not in failed:  # said once per kind of failure, not every second
                failed.add(str(exc))
                logger.warning("The DuckDB held-versions check failed: %s", exc)
