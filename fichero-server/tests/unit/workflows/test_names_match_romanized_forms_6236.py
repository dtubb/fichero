"""Reviewer b22 (#6236): the names step's exact match reads stored names only (`Database.query_fields`), not whole
entities; `aliases` is derived by KnowledgeEntity's validator (every name's text and romanized form), so a stored row
whose aliases column lacks a romanized form must still match it exactly, as reading the entity whole did."""
from __future__ import annotations

from fichero_server.db import Database
from fichero_server.models.knowledge import EntityName, EntityType, KnowledgeEntity
from fichero_server.workflows.tools._entity_writer import upsert_entity


def test_a_romanized_form_only_the_validator_adds_still_matches(tmp_path):
    db = Database(tmp_path / "names.duckdb")
    try:
        ent = KnowledgeEntity(canonical_name="Λουτοκοτία", entity_type=EntityType.location,
                              names=[EntityName(text="Λουτοκοτία", romanized="Loutokotia")])
        db.save(ent)
        db.conn.execute(f"UPDATE {db._sql_table_name(KnowledgeEntity)} SET aliases = '[]' WHERE id = ?", [ent.id])  # an older row's column
        assert "Loutokotia" in db.get(KnowledgeEntity, ent.id).aliases  # the validator derives it on a whole read

        assert upsert_entity(db, "Loutokotia", EntityType.location) == ent.id
        assert len(db.query(KnowledgeEntity, entity_type=EntityType.location)) == 1
    finally:
        db.close()
