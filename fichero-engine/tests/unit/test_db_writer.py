"""DBWriter — single-writer DB queue (#1000 Phase 2)."""

from __future__ import annotations

import os
import threading
import time

import pytest

os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero.db import Database  # noqa: E402
from fichero.db_manager import DatabaseManager  # noqa: E402
from fichero.db_writer import DBWriter, DBWriterError  # noqa: E402
from fichero.models import Document, DocType  # noqa: E402


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "writer.duckdb")
    yield database
    database.conn.close()


def _doc(name: str) -> Document:
    return Document(name=name, doc_type=DocType.file)


def test_save_persists_and_future_resolves(db):
    writer = DBWriter(db)
    writer.start()
    try:
        doc = _doc("alpha")
        future = writer.save(doc)
        assert future.result(timeout=5) is None  # resolves to None on success
        assert db.get(Document, doc.id) is not None
    finally:
        writer.stop()


def test_delete_removes_row(db):
    doc = _doc("to-delete")
    db.save(doc)
    with DBWriter(db) as writer:
        writer.delete(doc).result(timeout=5)
    assert db.get(Document, doc.id) is None


def test_flush_blocks_until_all_applied(db):
    with DBWriter(db) as writer:
        for i in range(50):
            writer.save(_doc(f"doc-{i}"))
        writer.flush()
        # Every enqueued write is applied by the time flush() returns.
        assert len(db.query(Document)) == 50


def test_failed_write_surfaces_on_the_future(db):
    """A write that raises sets the exception on its Future — the
    failure is observable, not silently swallowed."""
    from unittest.mock import MagicMock

    failing_db = MagicMock()
    failing_db.save.side_effect = RuntimeError("boom")
    with DBWriter(failing_db) as writer:
        future = writer.save(_doc("doomed"))
        with pytest.raises(RuntimeError, match="boom"):
            future.result(timeout=5)


def test_concurrent_producers_all_land(db):
    """Many threads enqueueing at once — every write still lands,
    because the single writer thread serialises them."""
    with DBWriter(db) as writer:
        def producer(start: int) -> None:
            for i in range(start, start + 20):
                writer.save(_doc(f"p-{i}"))

        threads = [threading.Thread(target=producer, args=(n * 20,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        writer.flush()

    assert len(db.query(Document)) == 100


def test_enqueue_before_start_raises(db):
    writer = DBWriter(db)
    with pytest.raises(RuntimeError, match="not running"):
        writer.save(_doc("too-early"))


def test_stop_is_idempotent(db):
    writer = DBWriter(db)
    writer.start()
    writer.stop()
    writer.stop()  # second stop is a no-op, not an error


# -- #1000: bounded drain — flush()/stop() must fail loud, never hang ------

def test_flush_returns_when_queue_drains(db):
    writer = DBWriter(db)
    writer.start()
    try:
        for i in range(5):
            writer.save(_doc(f"drain-{i}"))
        writer.flush(timeout=10)  # must not raise
        assert writer.pending == 0
    finally:
        writer.stop()


def test_flush_raises_when_writer_thread_dead(db):
    """A dead writer thread with a write still queued must raise
    DBWriterError, not block forever on queue.join() (#1000)."""
    writer = DBWriter(db)
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()  # thread is now dead
    writer._thread = dead
    writer._started = True
    writer._queue.put(object())  # unfinished_tasks == 1, never drained
    with pytest.raises(DBWriterError, match="thread died"):
        writer.flush(timeout=5)


def test_flush_times_out_when_queue_never_drains(db):
    """A live-but-stuck writer must make flush() time out and raise,
    not hang the caller forever (#1000)."""
    writer = DBWriter(db)
    alive = threading.Thread(target=lambda: time.sleep(30), daemon=True)
    alive.start()
    writer._thread = alive
    writer._started = True
    writer._queue.put(object())  # never processed
    started = time.monotonic()
    with pytest.raises(DBWriterError, match="exceeded"):
        writer.flush(timeout=1)
    assert time.monotonic() - started < 5  # bounded, not hung


def test_stop_returns_even_when_writer_wedged(db):
    """stop() is called under the db_manager lock — it must always
    return, logging loud rather than hanging on a wedged writer (#1000)."""
    writer = DBWriter(db)
    alive = threading.Thread(target=lambda: time.sleep(30), daemon=True)
    alive.start()
    writer._thread = alive
    writer._started = True
    writer._queue.put(object())  # never drained
    started = time.monotonic()
    writer.stop(timeout=1)  # must not raise, must not hang
    assert time.monotonic() - started < 15
    assert writer._started is False


def test_flush_on_unstarted_writer_raises(db):
    writer = DBWriter(db)
    with pytest.raises(DBWriterError, match="not running"):
        writer.flush(timeout=1)


def test_db_manager_quiesce_flushes_checkpoints_and_closes(tmp_path):
    manager = DatabaseManager()
    package_path = tmp_path / "Managed.fichero"
    writer = manager.get_db_writer(package_path)
    doc = _doc("queued")
    writer.save(doc)

    manager.quiesce_database(package_path, checkpoint=True, close=True, timeout=5)

    reopened = Database(package_path / "fichero.duckdb")
    try:
        assert reopened.get(Document, doc.id) is not None
        assert manager.active_count == 0
    finally:
        reopened.close()
