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
