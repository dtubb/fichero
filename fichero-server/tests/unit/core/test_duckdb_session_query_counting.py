"""The query-count ratchet's counting wrap must actually count (#4443).

A count is only useful if it is trustworthy. These tests drive the wrap in
`fichero_server.core.duckdb_session` directly: it must count real queries
while armed, stay a no-op while unarmed, and its own self-check
(`self_test_counting`, used by the ratchet's session-start blindness guard in
tests/conftest.py) must be able to tell "counting" from "silently broken" —
by breaking it for real, not by pointing at an empty baseline.
"""

from __future__ import annotations

import pytest

from fichero_server.core import duckdb_session


@pytest.fixture(autouse=True)
def _reset_counter():
    duckdb_session.reset_query_count()
    yield
    duckdb_session.reset_query_count()


class TestCountingWhenArmed:
    def test_execute_is_counted(self, monkeypatch):
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        conn = duckdb_session.connect_utc(":memory:")
        conn.execute("SELECT 1")
        conn.execute("SELECT 2")
        assert duckdb_session.get_query_count() == 2
        conn.close()

    def test_executemany_is_counted(self, monkeypatch):
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        conn = duckdb_session.connect_utc(":memory:")
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.executemany("INSERT INTO t VALUES (?)", [[1], [2], [3]])
        # CREATE TABLE + one executemany call = 2, not 4 — one call, one count,
        # regardless of how many rows it inserts.
        assert duckdb_session.get_query_count() == 2
        conn.close()

    def test_chained_execute_fetchall_is_counted_once(self, monkeypatch):
        """`conn.execute(...).fetchall()` must not double-count.

        `execute` returns the real (unwrapped) connection, so the chained
        `.fetchall()` runs straight on it — no second wrap, no second count.
        """
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        conn = duckdb_session.connect_utc(":memory:")
        rows = conn.execute("SELECT 1").fetchall()
        assert rows == [(1,)]
        assert duckdb_session.get_query_count() == 1
        conn.close()

    def test_a_reset_zeroes_the_counter(self, monkeypatch):
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        conn = duckdb_session.connect_utc(":memory:")
        conn.execute("SELECT 1")
        duckdb_session.reset_query_count()
        assert duckdb_session.get_query_count() == 0
        conn.close()

    def test_pin_utc_session_itself_is_not_counted(self, monkeypatch):
        """The UTC-pin SET happens before wrapping — it's setup, not a query
        the caller issued, and must not inflate every connection's count by 1."""
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        conn = duckdb_session.connect_utc(":memory:")
        assert duckdb_session.get_query_count() == 0
        conn.close()


class TestCountingWhenUnarmed:
    def test_execute_is_not_counted_by_default(self, monkeypatch):
        monkeypatch.delenv("FICHERO_PERF_RATCHET", raising=False)
        conn = duckdb_session.connect_utc(":memory:")
        conn.execute("SELECT 1")
        assert duckdb_session.get_query_count() == 0
        conn.close()

    def test_the_connection_is_not_wrapped_at_all(self, monkeypatch):
        """Unarmed, `connect_utc` returns the raw duckdb connection — no proxy,
        no per-call overhead for the machines that never opted in."""
        monkeypatch.delenv("FICHERO_PERF_RATCHET", raising=False)
        conn = duckdb_session.connect_utc(":memory:")
        assert not isinstance(conn, duckdb_session._QueryCountingConnection)
        conn.close()


class TestTheBlindnessSelfCheck:
    """`self_test_counting()` backs the ratchet's session-start guard: before
    trusting a session's "0 regressions", prove a known query was counted."""

    def test_a_working_wrap_reports_one(self, monkeypatch):
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        assert duckdb_session.self_test_counting() == 1

    def test_unarmed_reports_zero_and_that_is_correct_not_blind(self, monkeypatch):
        monkeypatch.delenv("FICHERO_PERF_RATCHET", raising=False)
        assert duckdb_session.self_test_counting() == 0

    def test_a_broken_wrap_is_caught(self, monkeypatch):
        """Synthesise the violation directly: make `connect_utc` skip wrapping
        even while armed (the actual failure mode this guards against — a
        future refactor of connect_utc that forgets the wrap), and confirm
        the self-check reports 0 rather than quietly passing."""
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        monkeypatch.setattr(duckdb_session, "_counting_enabled", lambda: False)
        assert duckdb_session.self_test_counting() == 0
