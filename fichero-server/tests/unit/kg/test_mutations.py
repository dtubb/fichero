"""Tests for the KG mutation log + undo endpoint (#901).

In-process calls into the route handlers (bypasses the pre-existing
TestClient auth-loopback issue).
"""

from __future__ import annotations

import asyncio

import pytest

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
        result = asyncio.run(kg_mutations.undo_mutation(log.id, db=db, actor="test-undo-actor"))

        restored = db.get(KnowledgeEntity, entity.id)
        assert restored is not None
        assert restored.canonical_name == "Test"
        assert result.restored_entity_id == entity.id

        # #4415: the reversal names WHO undid it. An undo is itself an edit,
        # and a reversal recorded as an anonymous default "human" is the
        # attribution hole that lets a re-run treat curated work as
        # disposable.
        reversal = next(
            (
                m
                for m in db.all(MutationLog)
                if m.reversal_id == log.id
            ),
            None,
        )
        assert reversal is not None, "the undo wrote no reversal record"
        assert reversal.created_by == "test-undo-actor", (
            f"the reversal recorded created_by={reversal.created_by!r} rather "
            "than the actor who performed it"
        )

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
        asyncio.run(kg_mutations.undo_mutation(log.id, db=db, actor="test-undo-actor"))
        try:
            asyncio.run(kg_mutations.undo_mutation(log.id, db=db, actor="test-undo-actor"))
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

        asyncio.run(kg_mutations.undo_mutation(log.id, db=db, actor="test-undo-actor"))
        restored = db.get(KnowledgeClaim, claim.id)
        assert restored is not None
        assert restored.text == "Original text."


class TestOneOperationHasOneUndo:
    """audit.one-operation-has-one-undo (#4864): `undo_mutation` never
    performs a PARTIAL restore of an operation the action layer owns and
    can invert in full. Temp `db` fixture only (test_package), never a
    real library."""

    def test_refused_undo_changes_no_row_when_the_action_layer_owns_it(self, db):
        """`entity.delete`'s inverse (`entity.restore`) would restore the
        entity AND its claim's cleared entity link -- the OLD MutationLog
        row `delete_entity_impl` also wrote can only ever restore the
        entity row. The old route must refuse rather than do that half."""
        from fastapi import HTTPException
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.api.routes import kg_mutations

        entity = KnowledgeEntity(canonical_name="Owned", entity_type=EntityType.person)
        db.save(entity)
        claim = KnowledgeClaim(
            text="Owned witnessed a will.",
            source_document_id="doc-1",
            subject_entity_id=entity.id,
            entity_ids=[entity.id],
        )
        db.save(claim)

        ctx = ActionContext(actor="ui", library_path="/lib/test.fichero")
        registry.invoke(
            db, "entity.delete", {"entity_id": entity.id, "cascade_claims": False}, ctx
        )
        assert db.get(KnowledgeEntity, entity.id) is None

        # The MutationLog row delete_entity_impl ALSO wrote, independent of
        # the action layer's own ActionAudit.
        log = next(
            m
            for m in db.all(MutationLog)
            if m.entity_id == entity.id and m.operation == MutationOperationType.delete
        )

        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(kg_mutations.undo_mutation(log.id, db=db, actor="someone"))
        assert excinfo.value.status_code == 409
        assert "audited action" in excinfo.value.detail
        assert "entity.delete" in excinfo.value.detail
        assert "/api/actions/audit/" in excinfo.value.detail

        # Refused -- changes NO row. The entity stays deleted (not
        # half-restored), and the original MutationLog is untouched.
        assert db.get(KnowledgeEntity, entity.id) is None
        assert db.get(MutationLog, log.id).reversal_id is None
        # The claim's cleared link stays cleared -- a partial restore would
        # have left this claim in exactly the drift #4863 removed.
        untouched_claim = db.get(KnowledgeClaim, claim.id)
        assert untouched_claim.subject_entity_id is None
        assert entity.id not in (untouched_claim.entity_ids or [])

    def test_owned_operation_still_undoes_fully_through_the_action_layer_path(self, db):
        """The narrowing changes nothing about the REAL undo: the action
        layer's own inverse still restores the entity AND the claim's
        cleared link, in one operation."""
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models import ActionAudit

        entity = KnowledgeEntity(canonical_name="Owned2", entity_type=EntityType.person)
        db.save(entity)
        claim = KnowledgeClaim(
            text="Owned2 witnessed a sale.",
            source_document_id="doc-1",
            subject_entity_id=entity.id,
            entity_ids=[entity.id],
        )
        db.save(claim)

        ctx = ActionContext(actor="ui", library_path="/lib/test.fichero")
        delete_result = registry.invoke(
            db, "entity.delete", {"entity_id": entity.id, "cascade_claims": False}, ctx
        )
        assert db.get(KnowledgeEntity, entity.id) is None
        assert db.get(KnowledgeClaim, claim.id).subject_entity_id is None

        # Drive undo the way the generic undo endpoint does (matches
        # test_action_registry.py::TestEntityMergeAction::test_undo_reverses_merge):
        # read the audit, ask the action for its inverse, invoke it.
        audit = db.get(ActionAudit, delete_result.audit_id)
        reg = registry.get(audit.action_name)
        assert reg.undoable and reg.invert is not None
        inverse = reg.invert(audit.before, audit.after, ctx)
        assert inverse is not None
        inv_name, inv_params = inverse
        assert inv_name == "entity.restore"
        registry.invoke(db, inv_name, inv_params, ctx)

        restored_entity = db.get(KnowledgeEntity, entity.id)
        assert restored_entity is not None
        assert restored_entity.canonical_name == "Owned2"
        restored_claim = db.get(KnowledgeClaim, claim.id)
        assert restored_claim.subject_entity_id == entity.id
        assert entity.id in (restored_claim.entity_ids or [])

    def test_unowned_mutation_still_undoes_via_the_old_route(self, db):
        """A MutationLog row with no matching, undoable ActionAudit (the
        `_cascade_delete_kg_rows` shape: a claim deleted as a side effect
        of deleting its DOCUMENT, never through `claim.delete`) keeps
        today's behavior -- the old route is its only undo, and must still
        work."""
        from fichero_server.api.routes import kg_mutations

        claim = KnowledgeClaim(text="Orphaned by a document delete.", source_document_id="doc-1")
        db.save(claim)
        log = MutationLog(
            entity_type="KnowledgeClaim",
            entity_id=claim.id,
            operation=MutationOperationType.delete,
            before_state=claim.model_dump(mode="json"),
            after_state=None,
            created_by="cascade_delete_document",
        )
        db.save(log)
        db.delete(claim)
        assert db.get(KnowledgeClaim, claim.id) is None

        asyncio.run(kg_mutations.undo_mutation(log.id, db=db, actor="test-undo-actor"))

        restored = db.get(KnowledgeClaim, claim.id)
        assert restored is not None
        assert restored.text == "Orphaned by a document delete."
