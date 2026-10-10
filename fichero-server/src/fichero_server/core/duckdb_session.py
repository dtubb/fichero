"""DuckDB connection factory that pins the session clock to UTC (#4347).

DuckDB's ``TIMESTAMP`` type is naive. Binding a timezone-aware datetime to a
``TIMESTAMP`` column makes DuckDB first shift the instant into the *session*
timezone and then drop the offset — so on a UTC-3 machine an aware
``12:01Z`` lands on disk as ``09:01``, indistinguishable from the old naive
local writes this issue set out to remove.

Pinning ``TimeZone='UTC'`` makes that shift a no-op: the wall clock stored in
every ``TIMESTAMP`` column is UTC, matching the read-side contract that a naive
stored value *is* UTC (see ``fichero_server.core.timeutil.ensure_utc``). It also
makes SQL ``CURRENT_TIMESTAMP`` and any ``TIMESTAMPTZ`` casts agree with the
Python writes.

Every ``duckdb.connect`` in server source goes through here.
"""

from __future__ import annotations

import contextvars
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

__all__ = [
    "connect_utc",
    "rebuild_secondary_indexes",
    "rebuilt_after_replay",
    "wal_left_behind",
    "pin_utc_session",
    "get_query_count",
    "reset_query_count",
    "self_test_counting",
]

# Per-request SQL query counter (#4443). A context var, not a plain module
# global, because a var written in one asyncio task/thread must not leak into
# a concurrent request's count.
#
# It holds a MUTABLE one-item list, not a bare int, on purpose: most DB work
# in this codebase is synchronous and runs via Starlette's `run_in_threadpool`
# (anyio `to_thread.run_sync`), which executes it inside a *copy* of the
# current context — `ContextVar.set()` there rebinds the variable only in
# that copy, and the increment would be lost the moment the thread returns.
# Mutating the boxed list in place instead changes the same object the outer
# context's copy of the var still points at (contexts copy the var->object
# mapping, not the object's contents), so the count survives the hop back.
_query_count: contextvars.ContextVar[list[int]] = contextvars.ContextVar(
    "fichero_duckdb_query_count"
)


def _counting_enabled() -> bool:
    # Same opt-in as the timing ratchet (tests/perf_ratchet.py): off on a
    # developer's laptop, on under the gate. Checked per-connect, not per
    # query, so there is zero overhead when off — no wrapping happens at all.
    return os.environ.get("FICHERO_PERF_RATCHET") == "1"


def reset_query_count() -> None:
    """Start a fresh query counter, e.g. at the start of a request.

    A NEW box each time — reusing one across requests would let a threadpool
    call from a previous request's (already-returned) copied context keep
    mutating a box a later request is also reading.
    """
    _query_count.set([0])


def get_query_count() -> int:
    """Queries issued (via `execute`/`executemany`) since the last reset."""
    box = _query_count.get(None)
    return box[0] if box is not None else 0


def _bump_query_count() -> None:
    # No box means a connection was used with no `reset_query_count()` ever
    # called in this context (e.g. a background task, not a tracked request)
    # — nothing to add to, so this is a no-op rather than an error.
    box = _query_count.get(None)
    if box is not None:
        box[0] += 1


class _QueryCountingConnection:
    """Proxies a DuckDB connection, counting `execute`/`executemany` calls.

    `duckdb.DuckDBPyConnection` is a C extension type — its attributes are
    read-only, so a query cannot be counted by monkeypatching `conn.execute`
    directly (tried; raises `AttributeError: attribute 'execute' is
    read-only`). This wraps the connection instead and forwards everything
    else via `__getattr__`, including the common `conn.execute(...).fetchall()`
    chain: `execute` returns the *real* connection, so the trailing
    `.fetchall()` runs on it directly and needs no wrapping of its own.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        object.__setattr__(self, "_conn", conn)

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        _bump_query_count()
        return self._conn.execute(*args, **kwargs)

    def executemany(self, *args: Any, **kwargs: Any) -> Any:
        _bump_query_count()
        return self._conn.executemany(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def self_test_counting() -> int:
    """Run one known query through `connect_utc` and report how many were counted.

    Returns 0 whenever counting isn't armed (`FICHERO_PERF_RATCHET` unset) —
    that is correct, not blind: "off" and "broken" must stay distinguishable,
    which is why the caller (the query-count ratchet's session-start check,
    tests/conftest.py) only calls this once it has confirmed the ratchet is
    enabled. With it enabled, any answer other than 1 means the wrap in this
    module stopped counting, and the ratchet's "no regression" would be a lie.
    """
    reset_query_count()
    conn = connect_utc(":memory:")
    try:
        conn.execute("SELECT 1")
    finally:
        conn.close()
    return get_query_count()


def pin_utc_session(conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Set ``TimeZone='UTC'`` on an existing connection and return it.

    A DuckDB build without the ICU extension has no ``TimeZone`` setting at all;
    such a build also performs no timezone conversion on bind, so the UTC
    contract already holds and the failure is logged rather than raised.
    """
    try:
        conn.execute("SET TimeZone='UTC'")
    except Exception as exc:  # pragma: no cover - build without ICU
        logger.debug("Could not pin DuckDB session timezone to UTC: %s", exc)
    return conn


# Per-connection buffer-pool cap (the 2026-08-22 Air OOM): DuckDB's default is
# 80% OF PHYSICAL RAM PER DATABASE, and the app routinely holds 4+ open at
# once (per-library packages + global + app.duckdb) — a structural overcommit
# on any machine. Spills go to disk instead. Override for a beefy box via env.
DUCKDB_MEMORY_LIMIT_ENV = "FICHERO_DUCKDB_MEMORY_LIMIT"
DEFAULT_DUCKDB_MEMORY_LIMIT = "1.5GB"


def apply_memory_limit(conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Cap this connection's memory and point its spill at the temp dir.

    The cap IS the Air-OOM guard (2026-08-24): an uncapped DuckDB claims 80%
    of RAM per open database. A cap that silently fails to apply is the
    #4395 shape — a protection that reads as present and does nothing — so
    an EXPLICIT limit that cannot be applied raises (the user asked for a
    bound; running unbounded instead is a substitution). Only the DEFAULT
    cap degrades to a loud warning, because refusing every connect on an
    exotic DuckDB build would trade a memory risk for a broken app.
    """
    explicit = os.environ.get(DUCKDB_MEMORY_LIMIT_ENV)
    limit = explicit or DEFAULT_DUCKDB_MEMORY_LIMIT
    try:
        conn.execute(f"SET memory_limit='{limit}'")
        conn.execute(
            "SET temp_directory=?", [str(Path(tempfile.gettempdir()) / "fichero-duckdb-spill")]
        )
    except Exception as exc:  # pragma: no cover - setting unsupported
        if explicit:
            raise RuntimeError(
                f"{DUCKDB_MEMORY_LIMIT_ENV}={explicit!r} could not be applied — "
                f"refusing to run this connection unbounded: {exc}"
            ) from exc
        logger.warning("Could not cap DuckDB memory (%s): %s", limit, exc)
    return conn


def connect_utc(database: Any = ":memory:", **kwargs: Any) -> duckdb.DuckDBPyConnection:
    """``duckdb.connect`` with the session timezone pinned to UTC.

    When the query-count ratchet is armed (``FICHERO_PERF_RATCHET=1``), the
    returned connection is wrapped to count `execute`/`executemany` calls —
    this is the one chokepoint every server connection is created through, so
    wrapping it here counts every query the app issues without touching any
    of the ~100 call sites that use `self.conn.execute(...)`.

    The first time this process opens a file the last session did not close cleanly, the
    indexes are rebuilt before the connection is handed out (#5644, the note at the end of this
    module) -- whichever caller opens it first: the library, the activity store, the scheduler.
    """
    key = _file_key(database, kwargs)
    if key is None:
        conn = apply_memory_limit(pin_utc_session(duckdb.connect(database, **kwargs)))
    else:
        # One lock per FILE: opens of different files never wait on each other (review, #5644).
        with _registry_lock:
            first_open_lock = _first_open_locks.setdefault(key, threading.Lock())
        with first_open_lock:
            replaying = key not in _opened_in_this_process and wal_left_behind(key)
            conn = apply_memory_limit(pin_utc_session(duckdb.connect(database, **kwargs)))
            _opened_in_this_process.add(key)
            if replaying:
                rebuilt, failed = rebuild_secondary_indexes(conn)
                if not failed:
                    _rebuilt_after_replay.add(key)
                logger.warning(
                    "rebuilt %d secondary indexes on %s: the last session ended without a clean close (#5644)",
                    rebuilt, key,
                )
    if _counting_enabled():
        return _QueryCountingConnection(conn)  # type: ignore[return-value]
    return conn


# ---------------------------------------------------------------------------
# DuckDB 1.4+ writes wrong secondary indexes after replaying a WAL (#5644)
# ---------------------------------------------------------------------------
#
# Measured 2026-10-09 (`scripts/repro_duckdb_wal_index.py`): a process that dies with a WAL
# leaves its rows safe, and the next open replays them correctly -- but the FIRST checkpoint
# after that replay writes every secondary (ART) index without the replayed rows. From then on
# a lookup through the index misses rows that are there (a page's segments, a run's activity),
# and an UPDATE or DELETE of such a row raises FATAL "Failed to delete all rows from index",
# invalidating the database. DuckDB 1.3.2 is clean; 1.4.4 through 1.5.6 all do it. Primary
# keys are not affected (measured), so they are left alone.
#
# The engine dies with a WAL whenever the app quits or crashes mid-write, so this is the
# ordinary case, not an edge. Rebuilding the indexes from their tables right after the replay,
# before anything can checkpoint, writes correct ones.


#: Files this process has opened. Only a file's FIRST open here can replay a WAL left by a session
#: that died; later ones join the instance already open (or, after a FATAL, the library's own
#: reconnect handles it: `Database._reconnect_after_invalidated`).
_opened_in_this_process: set[str] = set()
#: Files whose every index was rebuilt at their first open here (the library's one-time repair
#: then has nothing left to do: `rebuilt_after_replay`).
_rebuilt_after_replay: set[str] = set()
_first_open_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def rebuilt_after_replay(database: str | Path) -> bool:
    """Whether this process rebuilt every index of `database` when it first opened it."""
    return os.path.realpath(str(database)) in _rebuilt_after_replay


def _file_key(database: Any, kwargs: dict) -> str | None:
    """The file a connect opens, or None for an in-memory or read-only one (it never checkpoints)."""
    if kwargs.get("read_only") or not isinstance(database, (str, Path)):
        return None
    if str(database) in ("", ":memory:") or str(database).startswith(":memory:"):
        return None
    return os.path.realpath(str(database))


def wal_left_behind(database: str | Path) -> bool:
    """Whether the last session on this file ended without a clean close.

    A clean close checkpoints and removes the ``.wal``; one still there at open means DuckDB is
    about to replay it. Ask BEFORE connecting -- the connection itself starts the replay.
    """
    return Path(f"{database}.wal").exists()


def rebuild_secondary_indexes(conn: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    """Drop and recreate every non-unique, non-primary index from the SQL DuckDB recorded (#5644).

    An index is a speed-up, never data, so this cannot lose a row. Each index is rebuilt on its
    own: one that fails to come back is logged as an ERROR and its queries fall back to a scan,
    never a wrong answer. Returns (rebuilt, failed).
    """
    indexes = conn.execute(
        "SELECT index_name, sql FROM duckdb_indexes() "
        "WHERE database_name = current_database() AND NOT is_unique AND NOT is_primary "
        "AND sql IS NOT NULL"
    ).fetchall()
    rebuilt = failed = 0
    for name, sql in indexes:
        try:
            conn.execute(f'DROP INDEX "{name}"')
            conn.execute(sql)
            rebuilt += 1
        except duckdb.Error as exc:
            failed += 1
            logger.error("index %s could not be rebuilt (#5644); its lookups fall back to a scan: %s", name, exc)
    return rebuilt, failed
