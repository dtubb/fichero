"""Tests for the KG mutation log + undo endpoint (#901).

In-process calls into the route handlers (bypasses the pre-existing
TestClient auth-loopback issue).
"""

from __future__ import annotations

import asyncio

from fichero_server.models.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
)


class TestMutationLogList:
    def test_list_returns_recent_mutations_newest_first(self, db):
        from fichero_server.api.routes import kg_mutations

        old = MutationLog(
            entity_type="KnowledgeEntity",
            entity_id="e-1",
            operation=MutationOperationType.update,
            before_state={"canonical_name": "A"},
            after_state={"canonical_name": "B"},
            changed_fields=["canonical_name"],
        )
        db.save(old)
        new = MutationLog(
            entity_type="KnowledgeEntity",
            entity_id="e-1",
            operation=MutationOperationType.delete,
            before_state={"canonical_name": "B"},
            after_state=None,
        )
        db.save(new)

        response = asyncio.run(kg_mutations.list_mutations(limit=10, db=db))
        rows = response.items
        assert response.count == 2
        assert len(rows) == 2
        assert rows[0].id == new.id  # newest first
        assert rows[0].operation == "delete"


class TestUndo:
    def test_undo_restores_deleted_entity(self, db):
        from fichero_server.api.routes import kg_mutations
        from fichero_server.workflows.tools._entity_writer import upsert_entity

        # Direct save to bypass upsert fuzzy match.
        entity = KnowledgeEntity(
            canonical_name="Test",
            entity_type=EntityType.person,
        )
        db.save(entity)

        # Log a delete mutation.
        log = MutationLog(
            entity_type="KnowledgeEntity",
            entity_id=entity.id,
            operation=MutationOperationType.delete,
            before_state=entity.model_dump(mode="json"),
            after_state=None,
        )
        db.save(log)
        db.delete(entity)

        # Confirm gone, then undo.
        assert db.get(KnowledgeEntity, entity.id) is None
        result = asyncio.run(kg_mutations.undo_mutation(log.id, db=db))

        restored = db.get(KnowledgeEntity, entity.id)
        assert restored is not None
        assert restored.canonical_name == "Test"
        assert result.restored_entity_id == entity.id

        # The original log is marked reversed.
        reloaded = db.get(MutationLog, log.id)
        assert reloaded.reversal_id == result.reversal_mutation_id

        # The reversal log points back at the original.
        reversal = db.get(MutationLog, result.reversal_mutation_id)
        assert reversal.reversal_id == log.id
        assert reversal.operation == MutationOperationType.restore

        # Suppress unused-import warning — we keep upsert_entity in
        # scope so future tests in this class can grow without an
        # extra import.
        _ = upsert_entity

    def test_double_undo_is_blocked(self, db):
        from fastapi import HTTPException
        from fichero_server.api.routes import kg_mutations

        entity = KnowledgeEntity(canonical_name="X", entity_type=EntityType.person)
        db.save(entity)
        log = MutationLog(
            entity_type="KnowledgeEntity",
            entity_id=entity.id,
            operation=MutationOperationType.delete,
            before_state=entity.model_dump(mode="json"),
            after_state=None,
        )
        db.save(log)
        db.delete(entity)
        asyncio.run(kg_mutations.undo_mutation(log.id, db=db))
        try:
            asyncio.run(kg_mutations.undo_mutation(log.id, db=db))
            raise AssertionError("expected 409")
        except HTTPException as exc:
            assert exc.status_code == 409

    def test_undo_restores_claim(self, db):
        from fichero_server.api.routes import kg_mutations

        claim = KnowledgeClaim(
            text="Original text.",
            source_document_id="doc-1",
        )
        db.save(claim)
        log = MutationLog(
            entity_type="KnowledgeClaim",
            entity_id=claim.id,
            operation=MutationOperationType.delete,
            before_state=claim.model_dump(mode="json"),
            after_state=None,
        )
        db.save(log)
        db.delete(claim)

        asyncio.run(kg_mutations.undo_mutation(log.id, db=db))
        restored = db.get(KnowledgeClaim, claim.id)
        assert restored is not None
        assert restored.text == "Original text."
