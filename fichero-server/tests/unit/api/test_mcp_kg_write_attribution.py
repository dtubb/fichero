"""#4485 / #4866: MCP KG writes — authenticated author, audited, undoable.

Who asserted a claim is the difference between evidence and hearsay. The
route used to honour a client-supplied ``created_by`` and save with no
audit trail at all beyond a best-effort ``MutationLog`` row that knew
nothing of linked claims, curation provenance, or the actor's identity.

#4866 (`audit.only-the-action-surface-reaches-capabilities`): the three MCP
write tools are now thin callers of the SAME registered actions
(`entity.create`, `entity.update`, `claim.create`) the typed HTTP routes
use — no second implementation, no bespoke `MutationLog` write, no manual
change-stream emit. Real `ActionAudit` rows (readable by
`audited_row_ids` in `curation_guard.py` regardless of `MutationLog`) plus
the registry's own emit cover what the old best-effort helpers did, and
undo now goes through `POST /api/actions/audit/{id}/undo` like every other
audited write.
"""

from __future__ import annotations

import asyncio

import fichero_server.api.routes.claim.claims  # noqa: F401 -- registers claim.* actions
import fichero_server.api.routes.entity.entities  # noqa: F401 -- registers entity.* actions
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.mcp.tools import (
    KnowledgeClaimCreateRequest,
    KnowledgeEntityUpsertRequest,
    mcp_knowledge_claim_create,
    mcp_knowledge_claim_delete,
    mcp_knowledge_entity_delete,
    mcp_knowledge_entity_upsert,
)
from fichero_server.models import ActionAudit, Document, DocType
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity


def _doc(db) -> Document:
    doc = Document(name="src", path="/tmp/src.pdf", doc_type=DocType.file)
    db.save(doc)
    return doc


class TestClaimAuthorCannotBeForged:
    def _create(self, db, *, body_created_by: str, actor: str):
        doc = _doc(db)
        request = KnowledgeClaimCreateRequest(
            text="Istmina is on the San Juan",
            source_document_id=doc.id,
            created_by=body_created_by,
        )
        result = asyncio.run(mcp_knowledge_claim_create(request, db=db, actor=actor))
        return result

    def test_body_created_by_is_ignored(self, db):
        """A client-supplied created_by must never reach the stored row --
        authorship derives exclusively from the authenticated actor."""
        result = self._create(db, body_created_by="Ann", actor="agent")
        assert result.claim["created_by"] == "agent", (
            "a client recorded that Ann asserted a claim she never asserted — "
            "authorship must derive from authenticated request state"
        )

    def test_claim_create_writes_an_action_audit_naming_the_agent(self, db):
        result = self._create(db, body_created_by="mcp", actor="agent")
        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "claim.create"
        ]
        assert len(audits) == 1
        assert audits[0].actor == "agent"
        assert audits[0].target_ids == [result.claim_id]

    def test_claim_create_undo_removes_it(self, db):
        result = self._create(db, body_created_by="mcp", actor="agent")
        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "claim.create"
        ]
        audit = audits[0]
        reg = registry.get("claim.create")
        inverse = reg.invert(audit.before, audit.after, None)
        assert inverse is not None
        registry.invoke(db, inverse[0], inverse[1], ActionContext(actor="agent", library_path=str(db.path.parent)))
        from fichero_server.models.knowledge import KnowledgeClaim

        assert db.get(KnowledgeClaim, result.claim_id) is None

    def test_source_document_must_exist(self, db):
        """#4866: the reconciled route validates `source_document_id`
        through the SAME action `create_claim_impl` uses -- the old inline
        implementation never checked this at all."""
        from fastapi import HTTPException
        import pytest

        request = KnowledgeClaimCreateRequest(
            text="t", source_document_id="ghost-doc"
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mcp_knowledge_claim_create(request, db=db, actor="agent"))
        assert exc.value.status_code == 404


class TestEntityCreateIsAccountable:
    def test_entity_create_writes_an_action_audit_naming_the_agent(self, db):
        request = KnowledgeEntityUpsertRequest(
            canonical_name="Chocó", entity_type="location"
        )
        result = asyncio.run(mcp_knowledge_entity_upsert(request, db=db, actor="agent"))

        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "entity.create"
        ]
        assert len(audits) == 1
        assert audits[0].actor == "agent"
        assert audits[0].target_ids == [result.entity_id]

    def test_entity_update_writes_an_action_audit_naming_the_agent(self, db):
        entity = KnowledgeEntity(canonical_name="Choco")
        db.save(entity)
        request = KnowledgeEntityUpsertRequest(
            id=entity.id, canonical_name="Chocó", entity_type="location"
        )
        result = asyncio.run(mcp_knowledge_entity_upsert(request, db=db, actor="agent"))
        assert result.operation == "updated"

        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "entity.update"
        ]
        assert len(audits) == 1
        assert audits[0].actor == "agent"

    def test_entity_update_undo_restores_the_prior_name(self, db):
        entity = KnowledgeEntity(canonical_name="Choco")
        db.save(entity)
        request = KnowledgeEntityUpsertRequest(
            id=entity.id, canonical_name="Chocó", entity_type="location"
        )
        asyncio.run(mcp_knowledge_entity_upsert(request, db=db, actor="agent"))

        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "entity.update"
        ]
        audit = audits[0]
        reg = registry.get("entity.update")
        inverse = reg.invert(audit.before, audit.after, ActionContext(actor="agent", library_path=str(db.path.parent)))
        assert inverse is not None
        registry.invoke(db, inverse[0], inverse[1], ActionContext(actor="agent", library_path=str(db.path.parent)))
        assert db.get(KnowledgeEntity, entity.id).canonical_name == "Choco"

    def test_update_with_unknown_id_404s_instead_of_silently_creating(self, db):
        """#4866: a deliberate behavior change. The old inline
        implementation silently created a NEW entity under a caller-chosen
        id when `id` named nothing -- no other surface in this codebase
        supports that, and `entity.update` (like `upsert_entity`'s own
        established pattern) 404s instead."""
        from fastapi import HTTPException
        import pytest

        request = KnowledgeEntityUpsertRequest(
            id="ghost-entity", canonical_name="Chocó", entity_type="location"
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mcp_knowledge_entity_upsert(request, db=db, actor="agent"))
        assert exc.value.status_code == 404


class TestEntityDeleteIsAccountable:
    """#4866 part 2: mcp_knowledge_entity_delete, thin caller of entity.delete."""

    def test_delete_writes_an_action_audit_naming_the_agent(self, db):
        entity = KnowledgeEntity(canonical_name="Choco")
        db.save(entity)

        result = asyncio.run(mcp_knowledge_entity_delete(entity.id, db=db, actor="agent"))
        assert result.success is True
        assert db.get(KnowledgeEntity, entity.id) is None

        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.delete"]
        assert len(audits) == 1
        assert audits[0].actor == "agent"
        assert audits[0].target_ids == [entity.id]

    def test_delete_clears_dependent_claim_links_not_leaves_them_dangling(self, db):
        """#4863: non-cascade delete clears every scalar entity-id link a
        claim carries, not only entity_ids -- the bare db.delete() this
        replaces did neither."""
        entity = KnowledgeEntity(canonical_name="Choco")
        db.save(entity)
        claim = KnowledgeClaim(
            text="Choco is a region.",
            source_document_id="doc-1",
            subject_entity_id=entity.id,
            entity_ids=[entity.id],
        )
        db.save(claim)

        asyncio.run(mcp_knowledge_entity_delete(entity.id, db=db, actor="agent"))

        reloaded = db.get(KnowledgeClaim, claim.id)
        assert reloaded is not None
        assert reloaded.subject_entity_id is None
        assert entity.id not in (reloaded.entity_ids or [])

    def test_delete_undo_restores_the_entity(self, db):
        entity = KnowledgeEntity(canonical_name="Choco")
        db.save(entity)

        asyncio.run(mcp_knowledge_entity_delete(entity.id, db=db, actor="agent"))
        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.delete"]
        audit = audits[0]
        reg = registry.get("entity.delete")
        ctx = ActionContext(actor="agent", library_path=str(db.path.parent))
        inverse = reg.invert(audit.before, audit.after, ctx)
        assert inverse is not None
        registry.invoke(db, inverse[0], inverse[1], ctx)

        restored = db.get(KnowledgeEntity, entity.id)
        assert restored is not None
        assert restored.canonical_name == "Choco"

    def test_delete_unknown_entity_404s(self, db):
        from fastapi import HTTPException
        import pytest

        with pytest.raises(HTTPException) as exc:
            asyncio.run(mcp_knowledge_entity_delete("ghost", db=db, actor="agent"))
        assert exc.value.status_code == 404


class TestClaimDeleteIsAccountable:
    """#4866 part 2: mcp_knowledge_claim_delete, thin caller of claim.delete."""

    def test_delete_writes_an_action_audit_naming_the_agent(self, db):
        claim = KnowledgeClaim(text="A claim.", source_document_id="doc-1")
        db.save(claim)

        result = asyncio.run(mcp_knowledge_claim_delete(claim.id, db=db, actor="agent"))
        assert result.success is True
        assert db.get(KnowledgeClaim, claim.id) is None

        audits = [row for row in db.all(ActionAudit) if row.action_name == "claim.delete"]
        assert len(audits) == 1
        assert audits[0].actor == "agent"
        assert audits[0].target_ids == [claim.id]

    def test_delete_undo_restores_the_claim(self, db):
        claim = KnowledgeClaim(text="A claim.", source_document_id="doc-1")
        db.save(claim)

        asyncio.run(mcp_knowledge_claim_delete(claim.id, db=db, actor="agent"))
        audits = [row for row in db.all(ActionAudit) if row.action_name == "claim.delete"]
        audit = audits[0]
        reg = registry.get("claim.delete")
        ctx = ActionContext(actor="agent", library_path=str(db.path.parent))
        inverse = reg.invert(audit.before, audit.after, ctx)
        assert inverse is not None
        registry.invoke(db, inverse[0], inverse[1], ctx)

        restored = db.get(KnowledgeClaim, claim.id)
        assert restored is not None
        assert restored.text == "A claim."

    def test_delete_unknown_claim_404s(self, db):
        from fastapi import HTTPException
        import pytest

        with pytest.raises(HTTPException) as exc:
            asyncio.run(mcp_knowledge_claim_delete("ghost", db=db, actor="agent"))
        assert exc.value.status_code == 404
