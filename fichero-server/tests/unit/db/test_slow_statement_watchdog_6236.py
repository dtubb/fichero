"""#6236: a statement that runs past the threshold names itself in the engine log -- its SQL, its
thread, and every thread's Python stack -- so the next stall needs no py-spy (no root on the test
Macs). A fast statement logs nothing."""

from __future__ import annotations

import logging
import time

import pytest

from fichero_server.db import Database
from fichero_server.db import busy_evidence


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(busy_evidence, "SLOW_STATEMENT_SECONDS", 0.2)
    database = Database(tmp_path / "test.duckdb")
    database.conn.create_function("slow_sleep", lambda s: time.sleep(s) or s, ["DOUBLE"], "DOUBLE")
    yield database
    database.close()


def _slow_records(caplog):
    return [r for r in caplog.records if "slow DuckDB statement" in r.getMessage()]


def test_a_statement_past_the_threshold_logs_its_sql_thread_and_every_stack(db, caplog):
    caplog.set_level(logging.WARNING, logger=busy_evidence.__name__)
    db.execute_fetchone("SELECT slow_sleep(0.8) AS waited_6236")
    [record] = _slow_records(caplog)
    message = record.getMessage()
    assert "waited_6236" in message
    assert "MainThread" in message
    assert "test_a_statement_past_the_threshold" in message  # the blocked thread's own stack


def test_a_fast_statement_logs_nothing(db, caplog):
    caplog.set_level(logging.WARNING, logger=busy_evidence.__name__)
    db.execute_fetchone("SELECT slow_sleep(0.01)")
    time.sleep(0.3)
    assert _slow_records(caplog) == []


def _held_records(caplog):
    return [r for r in caplog.records if "old row versions" in r.getMessage()]


def _limit_bytes(db) -> int:
    from fichero_server.core.duckdb_session import parse_size

    return parse_size(db.execute_fetchone("SELECT current_setting('memory_limit')")[0].replace(" ", ""))


def test_undo_held_by_an_open_transaction_is_said_once_though_no_statement_is_slow(db, caplog, monkeypatch):
    """WHY: on the M4 the names pages went from 1 s to 300 s while no single statement ran 10 s: an open snapshot kept
    every update's undo, which spilled. The watchdog says so, with every thread's stack, once."""
    caplog.set_level(logging.WARNING, logger=busy_evidence.__name__)
    monkeypatch.setattr(busy_evidence, "HELD_VERSIONS_SHARE", 4 * 1024**2 / _limit_bytes(db))  # 4 MiB
    db.execute("CREATE TABLE held (id INTEGER PRIMARY KEY, body VARCHAR)")
    db.execute("INSERT INTO held VALUES (1, '')")
    snapshot = db.conn.cursor()
    snapshot.execute("BEGIN TRANSACTION")
    snapshot.execute("SELECT count(*) FROM held").fetchall()  # an old snapshot, held open
    try:
        for i in range(400):
            db.execute("UPDATE held SET body = ? WHERE id = 1", ["x" * 20_000 + str(i)])
        time.sleep(1.0)
        [record] = _held_records(caplog)
        assert "a transaction or a result left open" in record.getMessage()
        assert "MainThread" in record.getMessage()
    finally:
        snapshot.execute("ROLLBACK")


def test_undo_under_the_share_says_nothing(db, caplog):
    caplog.set_level(logging.WARNING, logger=busy_evidence.__name__)
    db.execute("CREATE TABLE held (id INTEGER PRIMARY KEY, body VARCHAR)")
    db.execute("INSERT INTO held VALUES (1, '')")
    for i in range(400):
        db.execute("UPDATE held SET body = ? WHERE id = 1", ["x" * 20_000 + str(i)])
    db.execute_fetchone("SELECT slow_sleep(0.01)")  # the watchdog runs
    time.sleep(1.0)
    assert _held_records(caplog) == []
