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
from pathlib import Path

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
        # The spill is read off the disk: duckdb_temporary_files() waits behind a running statement, which would
        # blind this watchdog to the very statement it is there to name.
        held, limit, temp_dir = conn.cursor().execute(
            "SELECT (SELECT coalesce(sum(memory_usage_bytes), 0) FROM duckdb_memory() WHERE tag = 'TRANSACTION'), "
            "current_setting('memory_limit'), current_setting('temp_directory')").fetchall()[0]
        spilled = sum(f.stat().st_size for f in Path(temp_dir).glob("*") if f.is_file()) if temp_dir else 0
        if spilled <= SPILL_ALARM_BYTES:
            alarmed.discard(f"spill:{key}")
        elif f"spill:{key}" not in alarmed:
            alarmed.add(f"spill:{key}")
            logger.warning("DuckDB spilled %d MiB to disk for %s (memory limit %s): every read of it now goes to disk",
                           spilled // 1024**2, key, limit)
        limit_bytes = duckdb_session.parse_size(limit.replace(" ", ""))
        if held < limit_bytes * HELD_VERSIONS_SHARE:
            alarmed.discard(key)
        elif key not in alarmed:
            alarmed.add(key)
            logger.warning("DuckDB holds %d MiB of old row versions for %s (memory limit %s, %d open instance(s)): "
                           "a transaction or a result left open keeps them\n%s",
                           held // 1024**2, key, limit, len(instances), _all_stacks())


#: DuckDB's temporary files past this: the work no longer fits its memory limit and reads come back from disk.
SPILL_ALARM_BYTES = 1024**3
#: The engine's peak RSS past each of these shares of this Mac's memory says so once.
RSS_SHARES = (0.25, 0.5, 0.75)


def _peak_rss_bytes() -> int:
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # bytes on macOS, KiB on Linux


def _check_rss(said: set[float]) -> None:
    """Say the highest share of this Mac's memory the engine's peak RSS newly passed (a model load, a growing cache)."""
    from fichero_server.core.duckdb_session import physical_memory_bytes

    total, peak = physical_memory_bytes(), _peak_rss_bytes()
    passed = [s for s in RSS_SHARES if total and peak > s * total and s not in said]
    if passed:
        said.update(passed)
        logger.warning("engine RSS reached %.1f GiB, past %d%% of this Mac's %.0f GiB: a model, a cache or a result "
                       "kept grows with the run", peak / 1024**3, max(passed) * 100, total / 1024**3)


def _watch() -> None:
    reported: set[int] = set()
    alarmed: set[str] = set()
    failed: set[str] = set()
    rss_said: set[float] = set()
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
            _check_rss(rss_said)
            _check_held_versions(alarmed)
        except Exception as exc:  # noqa: BLE001 -- a watchdog that dies says nothing ever again
            if str(exc) not in failed:  # said once per kind of failure, not every second
                failed.add(str(exc))
                logger.warning("The DuckDB held-versions check failed: %s", exc)
