"""Closing a library closes its embedding worker's connection too (#6238): `_embed_worker` opens a second Database on the
library's file, and `Database.close` left it open, so a closed library that had embedded kept a live connection to its
file (60 of them after one tests/unit/recipes run)."""
from __future__ import annotations

import duckdb
import pytest

from fichero_server.db import Database


def test_closing_a_library_closes_the_embed_worker_it_opened(tmp_path):
    db = Database(tmp_path / "lib" / "fichero.duckdb")
    worker = db._embed_worker()
    assert worker is not db
    db.close()
    with pytest.raises(duckdb.ConnectionException):
        worker.conn.execute("SELECT 1")


def test_a_close_while_an_embed_is_mid_statement_waits_for_it_and_its_next_statement_fails_cleanly(tmp_path):
    """The embed's statement in flight finishes (close waits for the worker's lock, as every statement holds it); the
    embed's next statement raises DuckDB's own closed-connection error, which its caller logs, never a crash."""
    import threading
    import time

    db = Database(tmp_path / "lib" / "fichero.duckdb")
    worker = db._embed_worker()
    inside, closed, results = threading.Event(), threading.Event(), []

    def embed():
        with worker._transaction_gate, worker._lock:
            inside.set()
            time.sleep(0.3)  # the close is asked now
            results.append(worker.conn.execute("SELECT 41 + 1").fetchone()[0])
        closed.wait(5)  # the embed's next statement comes after the close
        try:
            worker.conn.execute("SELECT 1")
        except duckdb.ConnectionException as exc:
            results.append(type(exc).__name__)

    thread = threading.Thread(target=embed)
    thread.start()
    assert inside.wait(5)
    db.close()
    closed.set()
    thread.join(5)
    assert results == [42, "ConnectionException"]


def test_closing_twice_is_safe(tmp_path):
    db = Database(tmp_path / "lib" / "fichero.duckdb")
    db._embed_worker()
    db.close()
    db.close()
