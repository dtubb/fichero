"""Regression coverage for DuckDB ART-index invalidation in entity writes."""

from __future__ import annotations

import duckdb

from fichero_server.db import Database
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero_server.workflows.tools._entity_writer import upsert_entity


def _duckdb_index_names(db: Database, table_name: str = "knowledgeentitys") -> set[str]:
    rows = db.conn.execute(
        "SELECT index_name FROM duckdb_indexes() WHERE table_name = ?",
        [table_name],
    ).fetchall()
    return {row[0] for row in rows}


def _claim_index_names(db: Database) -> set[str]:
    return _duckdb_index_names(db, "knowledgeclaims")


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


def test_knowledge_claim_indices_are_removed(tmp_path):
    """Existing libraries drop the unsafe secondary ART indexes on knowledgeclaims.

    The claims ART indexes hit the same "Failed to delete all rows from index"
    corruption as ``idx_entities_name`` during real-data catalogue churn, so
    ``migrate_knowledge_indices`` drops them too (follow-up to #1596).
    """
    db = Database(tmp_path / "claims.duckdb")
    try:
        db.save(
            KnowledgeClaim(
                text="Don Alfonso served as alcalde.",
                source_document_id="page-000",
            )
        )
        # Recreate the indexes an old library would still carry.
        for ddl in (
            "CREATE INDEX IF NOT EXISTS idx_claims_source_doc "
            "ON knowledgeclaims(source_document_id)",
            "CREATE INDEX IF NOT EXISTS idx_claims_page "
            "ON knowledgeclaims(source_document_id, source_page_label)",
            "CREATE INDEX IF NOT EXISTS idx_claims_type "
            "ON knowledgeclaims(claim_type)",
            "CREATE INDEX IF NOT EXISTS idx_claims_status "
            "ON knowledgeclaims(epistemic_status)",
            "CREATE INDEX IF NOT EXISTS idx_claims_created "
            "ON knowledgeclaims(created_at)",
        ):
            db.conn.execute(ddl)
        present = _claim_index_names(db)
        assert {
            "idx_claims_source_doc",
            "idx_claims_page",
            "idx_claims_type",
            "idx_claims_status",
            "idx_claims_created",
        } <= present

        # Re-running the lazy table migration must shed every claims index.
        db._tables_created.clear()
        db.query(KnowledgeClaim, source_document_id="page-000")

        remaining = _claim_index_names(db)
        assert not any(name.startswith("idx_claims_") for name in remaining)
    finally:
        db.close()


def test_claim_churn_on_persistent_duckdb_stays_queryable(tmp_path):
    """Repeated claim upsert/delete churn does not invalidate an on-disk DuckDB.

    Mirrors the entity churn test for the ``knowledgeclaims`` table — the
    catalogue churns claims hardest of all (dedup/rewrite). With the corrupting
    ``idx_claims_*`` ART indexes dropped, sustained save/delete cycles complete
    without a FatalException and the library is still readable on reopen.
    """
    db_path = tmp_path / "claim_churn.duckdb"
    db = Database(db_path)
    try:
        # Many upserts (overwrite same ids) interleaved with deletes — the
        # exact churn pattern that poisoned the ART delete path on real data.
        for i in range(120):
            claim = KnowledgeClaim(
                id=f"claim-{i % 20:03d}",
                text=f"Churn claim {i}",
                source_document_id=f"page-{i % 5:03d}",
                source_page_label=f"p{i % 5}",
                claim_type=None,
            )
            db.save(claim)  # repeated ids → UPDATE path, churns the heap
            if i % 3 == 0:
                db.delete(claim)

        # No claims index should have been re-created by the churn.
        assert not any(
            name.startswith("idx_claims_") for name in _claim_index_names(db)
        )

        # The library is still queryable (no invalidated connection).
        rows = db.query(KnowledgeClaim, source_document_id="page-000")
        assert isinstance(rows, list)

        # A fresh connection can still read the library after the churn.
        db.close()
        reopened = Database(db_path)
        try:
            assert not any(
                name.startswith("idx_claims_")
                for name in _claim_index_names(reopened)
            )
            # At least one of the surviving claims is still retrievable.
            survivors = reopened.query(KnowledgeClaim, source_document_id="page-001")
            assert isinstance(survivors, list)
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


def test_closed_connection_reopens_and_retries_next_query(tmp_path):
    db = Database(tmp_path / "recover-closed.duckdb")
    try:
        entity = KnowledgeEntity(
            canonical_name="Recovered Closed Entity",
            entity_type=EntityType.person,
        )
        db.save(entity)

        class ClosedConnection:
            def execute(self, *_args, **_kwargs):
                raise duckdb.ConnectionException("Connection already closed!")

            def close(self):
                pass

        db.conn = ClosedConnection()
        db.duck = db.conn

        loaded = db.get(KnowledgeEntity, entity.id)

        assert loaded is not None
        assert loaded.id == entity.id
        assert not isinstance(db.conn, ClosedConnection)
    finally:
        db.close()
