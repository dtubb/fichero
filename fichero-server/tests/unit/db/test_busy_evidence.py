"""A busy snapshot refusal names who is inside a database call right now, and never the thread
asking (#5185 evidence, moved out of the pool module for the #2508 guard).

WHY: when a snapshot is refused and no managed transaction is open, the writer is a connection the
manager does not own; the refusal's only lead is which thread, in which engine frame, is executing
a statement at that moment. If this regresses, the refusal says "no thread" while one is writing,
or names the snapshot's own thread -- evidence that points nowhere.

A real DuckDB statement runs on a named thread until it is interrupted.
"""

from __future__ import annotations

import threading
import time

import duckdb

from fichero_server.db.busy_evidence import threads_in_a_database_call


def _run_long_query(conn, started: threading.Event):
    started.set()
    try:
        conn.execute("SELECT count(*) FROM range(100000000000)").fetchall()
    except duckdb.InterruptException:
        pass


def test_a_thread_inside_a_statement_is_named_and_the_caller_is_not():
    conn = duckdb.connect()
    started = threading.Event()
    writer = threading.Thread(target=_run_long_query, args=(conn, started), name="a-long-writer")
    writer.start()
    try:
        started.wait(5)
        seen: list[str] = []
        for _ in range(50):                               # until the statement is under way
            seen = threads_in_a_database_call()
            if seen:
                break
            time.sleep(0.05)
        assert [s.split(":", 1)[0] for s in seen] == ["a-long-writer"], seen
        assert threading.current_thread().name not in {s.split(":", 1)[0] for s in seen}
    finally:
        conn.interrupt()
        writer.join(10)
        conn.close()
    assert not writer.is_alive()
    assert threads_in_a_database_call() == []           # nobody in a call: says so, names nothing
