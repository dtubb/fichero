"""Regression coverage for DuckDB ART-index invalidation in entity writes."""

from __future__ import annotations

import duckdb

from fichero.db import Database
from fichero.knowledge_models import EntityType, KnowledgeEntity
from fichero.workflows.tools._entity_writer import upsert_entity


def _duckdb_index_names(db: Database) -> set[str]:
    rows = db.conn.execute(
        "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'knowledgeentitys'"
    ).fetchall()
    return {row[0] for row in rows}


def test_knowledge_entity_name_index_is_removed(tmp_path):
    """Existing libraries drop the unsafe secondary ART index on open."""
    db = Database(tmp_path / "entities.duckdb")
    try:
        db.save(
            KnowledgeEntity(
                canonical_name="Don Alfonso",
                entity_type=EntityType.person,
            )
        )
        db.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entities_name "
            "ON knowledgeentitys(canonical_name)"
        )
        assert "idx_entities_name" in _duckdb_index_names(db)

        db._tables_created.clear()
        db.query(KnowledgeEntity, canonical_name="Don Alfonso")

        assert "idx_entities_name" not in _duckdb_index_names(db)
    finally:
        db.close()


def test_entity_upsert_churn_on_persistent_duckdb_stays_queryable(tmp_path):
    """Repeated entity updates do not leave an on-disk DuckDB invalidated."""
    db = Database(tmp_path / "churn.duckdb")
    try:
        entity_id = upsert_entity(
            db,
            canonical_name="Don Alfonso",
            entity_type=EntityType.concept,
            source_document_id="page-000",
        )

        promoted_id = upsert_entity(
            db,
            canonical_name="Don Alfonso",
            entity_type=EntityType.person,
            aliases=["Alfonso"],
            source_document_id="page-001",
        )
        assert promoted_id == entity_id

        for i in range(2, 80):
            returned_id = upsert_entity(
                db,
                canonical_name="Don Alfonso",
                entity_type=EntityType.person,
                aliases=[f"Don Alfonso alias {i}"],
                source_document_id=f"page-{i:03d}",
            )
            assert returned_id == entity_id

        alias_id = upsert_entity(
            db,
            canonical_name="el Don Alfonso",
            entity_type=EntityType.person,
            aliases=["Don A."],
            source_document_id="page-999",
        )
        assert alias_id == entity_id

        rows = db.query(
            KnowledgeEntity,
            canonical_name="Don Alfonso",
            entity_type=EntityType.person,
        )
        assert len(rows) == 1
        entity = rows[0]
        assert len(entity.source_document_ids) == 81
        assert "page-999" in entity.source_document_ids
        assert "idx_entities_name" not in _duckdb_index_names(db)

        # A fresh connection can still read the library after the churn.
        db.close()
        reopened = Database(tmp_path / "churn.duckdb")
        try:
            assert reopened.get(KnowledgeEntity, entity_id) is not None
        finally:
            reopened.close()
    finally:
        try:
            db.close()
        except Exception:
            pass


def test_invalidated_connection_reopens_and_retries_next_query(tmp_path):
    db = Database(tmp_path / "recover.duckdb")
    try:
        entity = KnowledgeEntity(
            canonical_name="Recovered Entity",
            entity_type=EntityType.person,
        )
        db.save(entity)

        class PoisonedConnection:
            def execute(self, *_args, **_kwargs):
                raise duckdb.FatalException("database has been invalidated")

            def close(self):
                pass

        db.conn = PoisonedConnection()
        db.duck = db.conn

        loaded = db.get(KnowledgeEntity, entity.id)

        assert loaded is not None
        assert loaded.id == entity.id
        assert not isinstance(db.conn, PoisonedConnection)
    finally:
        db.close()
