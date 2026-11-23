"""The knowledge rebuild remakes `kg_mentions` from the statements table (#6755)."""

from __future__ import annotations

from fichero_server.db import Database
from fichero_server.knowledge.rebuild import rebuild_kg
from fichero_server.models.knowledge import KnowledgeClaim


def _all(db: Database) -> set[tuple]:
    return set(db.conn.execute("SELECT entity_id, claim_id, page, role FROM kg_mentions").fetchall())


def test_rebuild_remakes_a_dropped_and_a_damaged_table_to_the_written_rows(tmp_path):
    db = Database(tmp_path / "t.duckdb")
    claims = [
        KnowledgeClaim(text="1", entity_ids=["a", "b"], subject_entity_id="a", source_page_label="3"),
        KnowledgeClaim(text="2", entity_ids=["b"]),
        KnowledgeClaim(text="3", entity_ids=[]),
    ]
    db.save_many(claims, new=True)
    written = _all(db)
    assert len(written) == 3

    db.conn.execute("DELETE FROM kg_mentions")
    db.conn.execute("INSERT INTO kg_mentions VALUES ('stray', 'nope', NULL, 'named')")
    stats = rebuild_kg(db, vectors=False, triples=False)

    assert _all(db) == written
    assert stats["kg_mentions"] == 3
    db.close()
