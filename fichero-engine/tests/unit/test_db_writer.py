"""DBWriter — single-writer DB queue (#1000 Phase 2)."""

from __future__ import annotations

import os
import threading

import pytest

os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero.db import Database  # noqa: E402
from fichero.db_writer import DBWriter  # noqa: E402
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
