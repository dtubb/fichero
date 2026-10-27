"""#6236: a connection left idle on a one-row read holds no snapshot.

WHY: DuckDB keeps a statement's autocommit transaction open until its result is read to the end. A connection whose
last statement was a `fetchone()` and then sat idle (the read cursor after `get_committed`, a second Database such as
the embed worker after `execute_fetchone`) kept every later update's undo alive: on the M4 the names step's pages
went from 1 s to 300 s as those undo blocks spilled to disk and every row fetch read them back.
"""

from __future__ import annotations

import pytest

from fichero_server.db import Database
from fichero_server.models import DocType, Document


def _old_versions(db: Database) -> int:
    """What DuckDB holds for row versions a snapshot may still read: the undo, and the old strings it points at."""
    return db.execute_fetchall(
        "SELECT sum(memory_usage_bytes) FROM duckdb_memory() WHERE tag IN ('TRANSACTION', 'OVERFLOW_STRINGS')")[0][0]


def _update_many_times(db: Database, doc: Document) -> None:
    for i in range(3000):  # 60 MB of old page text if every version is kept
        doc.page_content = "x" * 20_000 + str(i)
        db.save(doc)


@pytest.mark.parametrize("idle_read", [
    "second_database_just_opened",  # the embed worker: opened, then never another statement (its open ends in a count)
    "second_database_execute_fetchone", "second_database_get", "get_committed"])
def test_a_one_row_read_left_idle_keeps_no_undo(tmp_path, idle_read):
    db = Database(tmp_path / "test.duckdb")
    doc = Document(name="page", doc_type=DocType.file)
    db.save(doc)  # a table with a row, before the second Database opens over it
    other = Database(tmp_path / "test.duckdb")  # the embed worker's shape: a second Database on the same file
    try:
        before = _old_versions(db)
        if idle_read == "second_database_just_opened":
            pass
        elif idle_read == "second_database_execute_fetchone":
            other.execute_fetchone("SELECT count(*) FROM documents")
        elif idle_read == "second_database_get":
            other.get(Document, doc.id)
        else:
            db.get_committed(Document, doc.id)  # the read cursor, then nothing reads through it again

        _update_many_times(db, doc)

        grown = _old_versions(db) - before
        assert grown < 30 * 1024**2, f"{grown / 1024**2:.0f} MB of undo held by an idle one-row read"
    finally:
        other.close()
        db.close()
