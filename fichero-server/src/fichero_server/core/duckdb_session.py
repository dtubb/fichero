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

import logging
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

__all__ = ["connect_utc", "pin_utc_session"]


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


def connect_utc(database: Any = ":memory:", **kwargs: Any) -> duckdb.DuckDBPyConnection:
    """``duckdb.connect`` with the session timezone pinned to UTC."""
    return pin_utc_session(duckdb.connect(database, **kwargs))
