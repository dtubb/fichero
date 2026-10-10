"""Saving new rows inside one transaction must not hold megabytes per row until commit.

Found 2026-10-10 through the deep-duplicate test: duplicating ~1,050 documents in one atomic
action ran DuckDB out of its 1.3 GiB cap. DuckDB 1.5 holds ~32 KB per column for each row an
ON CONFLICT statement inserts inside an open transaction -- 1.35 MB per Document -- so any
atomic action creating ~1,000 rows (a big folder duplicated, a large import step) failed.
`Database.save` now inserts a new row with a plain INSERT. Upstream: duckdb/duckdb#26830.
"""

from __future__ import annotations

from fichero_server.db import Database
from fichero_server.models import DocType, Document


def _held_mb(db: Database) -> float:
    sql = "SELECT coalesce(sum(memory_usage_bytes), 0) FROM duckdb_memory() WHERE tag = 'IN_MEMORY_TABLE'"
    return db.conn.execute(sql).fetchone()[0] / 2**20


def test_two_hundred_new_documents_in_one_transaction_hold_little_memory(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    top = Document(name="top", doc_type=DocType.folder)
    db.save(top)
    with db.transaction():
        before = _held_mb(db)
        for i in range(200):
            db.save(Document(name=f"p{i}", parent_id=top.id))
        held = _held_mb(db) - before
    db.close()
    # Measured: 0.013 MB a row with the plain INSERT, 1.36 MB with ON CONFLICT (270 MB here).
    assert held < 20, f"200 new documents held {held:.0f} MB until commit"


def test_saving_an_existing_row_still_updates_it(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    doc = Document(name="before")
    db.save(doc)
    with db.transaction():
        doc.name = "after"
        db.save(doc)
    assert db.get(Document, doc.id).name == "after"
    assert db.conn.execute("SELECT count(*) FROM documents WHERE id = ?", [doc.id]).fetchone()[0] == 1
    db.close()
