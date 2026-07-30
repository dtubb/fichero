"""Unit tests for the GENERALIZED, registry-driven undo/redo (EPIC #1848 / #2015).

The undo endpoint (``POST /api/actions/audit/{id}/undo``) is fully
registry-driven: for ANY undoable registered action it loads the ActionAudit
row, asks the action's ``invert(before, after, ctx)`` for an inverse, invokes
that inverse through the SAME audited choke point, and marks the original
``undone``. The inverse invocation is tagged ``inverse_of=<original audit id>``
so that undoing IT (undo-of-undo / **redo**) replays the original forward action
— correct for any action regardless of how its inverse was written, with no
per-action redo code and no need for inverse actions (restore/unmerge) to be
independently ``undoable``.

Per the project test bar ([[would-more-tests-catch-more-issues]]) these assert
MORE than the happy path, across 3+ domains:

  * claim.delete   — delete → undo (restore) → redo (re-delete)
  * document.update — update → undo (restore old) → redo (RE-APPLIES the update,
    proving the shared ``document.restore`` inverse does NOT delete on redo)
  * entity.merge   — merge → undo (unmerge) → redo (re-merge)

plus the endpoint contract: 404 (unknown audit), 409 (already undone), 409
(non-undoable forward action), the inverse writing its OWN audit row tagged
``inverse_of``, and the ``GET /api/actions/audit`` log (newest-first, limit,
undoable/undone flags). ``emit_change`` is monkeypatched at its SOURCE module.

The MANAGER runs the full suite; this worker only writes the tests.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fastapi import HTTPException
from starlette.requests import Request

# Importing the route modules registers the relevant @action decorators AND the
# generic undo / audit-log endpoint handlers under test.
import fichero_server.api.routes.claim.claims  # noqa: F401
import fichero_server.api.routes.document.documents  # noqa: F401
import fichero_server.api.routes.entity.entities  # noqa: F401
import fichero_server.api.routes.kg_entity_curation  # noqa: F401
from fichero_server.api.routes.actions_registry import list_audit_log, undo_action
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.models import ActionAudit, DocType, Document

LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def spy_emit(monkeypatch):
    """Capture emit_change calls at the SOURCE module the registry imports."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


# --- thin wrappers that drive the real async route handlers directly ---------
# FastAPI's Depends/Header defaults are bypassed when the coroutine is called
# directly, so db + headers are passed explicitly. This exercises the actual
# endpoint logic (the two undo/redo branches + all the 404/409 guards).


def _undo(db, audit_id: str):
    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "scheme": "https",
            "server": ("testserver", 443),
            "path": f"/api/actions/audit/{audit_id}/undo",
            "query_string": b"",
        }
    )
    return asyncio.run(
        undo_action(
            audit_id,
            request=request,
            db=db,
            x_fichero_library_path=LIB,
            x_fichero_origin_window=None,
        )
    )


def _audit_log(db, limit: int = 50):
    return asyncio.run(
        list_audit_log(limit=limit, db=db, x_fichero_library_path=LIB)
    )


def _save_claim(db, text="A claim", **kwargs) -> KnowledgeClaim:
    kwargs.setdefault("source_document_id", "doc-claim-src")
    claim = KnowledgeClaim(text=text, **kwargs)
    db.save(claim)
    return claim


def _audit(db, audit_id: str) -> ActionAudit:
    row = db.get(ActionAudit, audit_id)
    assert row is not None
    return row


# ===========================================================================
# Domain 1 — claim.delete : delete -> undo(restore) -> redo(re-delete)
# ===========================================================================


class TestClaimDeleteUndoRedo:
    def test_delete_undo_restores_and_writes_inverse_audit(self, db, spy_emit):
        claim = _save_claim(db, text="condemned")
        forward = registry.invoke(db, "claim.delete", {"claim_id": claim.id}, _ctx())
        assert db.get(KnowledgeClaim, claim.id) is None

        resp = _undo(db, forward.audit_id)

        # (effect) the claim is back
        assert db.get(KnowledgeClaim, claim.id) is not None
        # (state) the original forward audit is marked undone
        assert _audit(db, forward.audit_id).undone is True
        # (inverse-as-action) the inverse wrote its OWN audit row, tagged with a
        # back-pointer to the original — this is what makes redo possible.
        inverse_audit = _audit(db, resp.audit_id)
        assert resp.audit_id != forward.audit_id
        assert inverse_audit.action_name == "claim.restore"
        assert inverse_audit.inverse_of == forward.audit_id
        assert inverse_audit.undone is False

    def test_undo_of_undo_redo_re_deletes(self, db, spy_emit):
        claim = _save_claim(db, text="condemned")
        forward = registry.invoke(db, "claim.delete", {"claim_id": claim.id}, _ctx())
        inverse = _undo(db, forward.audit_id)
        assert db.get(KnowledgeClaim, claim.id) is not None  # restored

        # Redo = undo the inverse (restore) audit. Generic path replays the
        # ORIGINAL forward (claim.delete) — the claim is removed again.
        redo = _undo(db, inverse.audit_id)
        assert db.get(KnowledgeClaim, claim.id) is None
        assert _audit(db, inverse.audit_id).undone is True
        redo_audit = _audit(db, redo.audit_id)
        assert redo_audit.action_name == "claim.delete"      # replayed forward
        assert redo_audit.inverse_of == inverse.audit_id

    def test_redo_chain_is_unbounded(self, db, spy_emit):
        """A 4th step (undo the redo) restores again — the chain never dead-ends."""
        claim = _save_claim(db, text="yo-yo")
        a = registry.invoke(db, "claim.delete", {"claim_id": claim.id}, _ctx())
        b = _undo(db, a.audit_id)   # restore
        c = _undo(db, b.audit_id)   # re-delete (redo)
        d = _undo(db, c.audit_id)   # restore again (undo of redo)
        assert db.get(KnowledgeClaim, claim.id) is not None
        assert _audit(db, c.audit_id).undone is True
        assert _audit(db, d.audit_id).inverse_of == c.audit_id


# ===========================================================================
# Domain 2 — document.update : update -> undo(restore old) -> redo(RE-APPLY)
# ===========================================================================


class TestDocumentUpdateUndoRedo:
    def _doc(self, db, name="old name") -> Document:
        doc = Document(name=name, doc_type=DocType.file)
        db.save(doc)
        return doc

    def test_update_undo_restores_old_value(self, db, spy_emit):
        doc = self._doc(db, name="old name")
        forward = registry.invoke(
            db, "document.update", {"doc_id": doc.id, "update": {"name": "new name"}}, _ctx()
        )
        assert db.get(Document, doc.id).name == "new name"

        inverse = _undo(db, forward.audit_id)
        assert db.get(Document, doc.id).name == "old name"  # reverted
        inv_audit = _audit(db, inverse.audit_id)
        assert inv_audit.action_name == "document.restore"
        assert inv_audit.inverse_of == forward.audit_id

    def test_redo_reapplies_update_does_not_delete(self, db, spy_emit):
        """Critical: document.update and document.delete BOTH invert to
        document.restore. A naive 'make restore undoable -> delete' redo would
        DELETE the document here. The generic replay re-applies the UPDATE."""
        doc = self._doc(db, name="old name")
        forward = registry.invoke(
            db, "document.update", {"doc_id": doc.id, "update": {"name": "new name"}}, _ctx()
        )
        inverse = _undo(db, forward.audit_id)   # name -> "old name"

        redo = _undo(db, inverse.audit_id)      # redo
        survivor = db.get(Document, doc.id)
        assert survivor is not None             # NOT deleted
        assert survivor.name == "new name"      # update re-applied
        redo_audit = _audit(db, redo.audit_id)
        assert redo_audit.action_name == "document.update"  # replayed forward
        assert redo_audit.inverse_of == inverse.audit_id


# ===========================================================================
# Domain 3 — entity.merge : merge -> undo(unmerge) -> redo(re-merge)
# ===========================================================================


class TestEntityMergeUndoRedo:
    def _entity(self, db, name) -> KnowledgeEntity:
        ent = KnowledgeEntity(
            canonical_name=name,
            aliases=[name.lower()],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.save(ent)
        return ent

    def test_merge_undo_unmerges_then_redo_remerges(self, db, spy_emit):
        absorber = self._entity(db, "Alexander")
        absorbed = self._entity(db, "Alex")

        forward = registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id == absorber.id

        # undo -> entity.unmerge clears the merge
        inverse = _undo(db, forward.audit_id)
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id is None
        inv_audit = _audit(db, inverse.audit_id)
        assert inv_audit.action_name == "entity.unmerge"
        assert inv_audit.inverse_of == forward.audit_id

        # redo -> replays entity.merge, absorbed is tombstoned again
        redo = _undo(db, inverse.audit_id)
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id == absorber.id
        assert _audit(db, redo.audit_id).action_name == "entity.merge"
        assert _audit(db, inverse.audit_id).undone is True


# ===========================================================================
# Domain 4 — entity.create : create -> undo(delete) -> redo(re-create)
# ===========================================================================


class TestEntityCreateUndoRedo:
    def test_create_undo_deletes_and_writes_inverse_audit(self, db, spy_emit):
        forward = registry.invoke(
            db,
            "entity.create",
            {"canonical_name": "Created Entity"},
            _ctx(),
        )
        entity_id = forward.result["id"]
        assert db.get(KnowledgeEntity, entity_id) is not None

        inverse = _undo(db, forward.audit_id)

        assert db.get(KnowledgeEntity, entity_id) is None
        assert _audit(db, forward.audit_id).undone is True
        inverse_audit = _audit(db, inverse.audit_id)
        assert inverse_audit.action_name == "entity.delete"
        assert inverse_audit.inverse_of == forward.audit_id

    def test_redo_recreates_entity(self, db, spy_emit):
        forward = registry.invoke(
            db,
            "entity.create",
            {"canonical_name": "Yo Yo Entity"},
            _ctx(),
        )
        entity_id = forward.result["id"]
        inverse = _undo(db, forward.audit_id)
        assert db.get(KnowledgeEntity, entity_id) is None

        redo = _undo(db, inverse.audit_id)

        restored = [row for row in db.all(KnowledgeEntity) if row.canonical_name == "Yo Yo Entity"]
        assert len(restored) == 1
        assert restored[0].id != entity_id
        redo_audit = _audit(db, redo.audit_id)
        assert redo_audit.action_name == "entity.create"
        assert redo_audit.inverse_of == inverse.audit_id


# ===========================================================================
# Domain 5 — entity.update : update -> undo(restore old) -> redo(re-apply)
# ===========================================================================


class TestEntityUpdateUndoRedo:
    def test_update_undo_restores_old_value(self, db, spy_emit):
        entity = KnowledgeEntity(canonical_name="Old Entity")
        db.save(entity)

        forward = registry.invoke(
            db,
            "entity.update",
            {"entity_id": entity.id, "canonical_name": "New Entity"},
            _ctx(),
        )
        assert db.get(KnowledgeEntity, entity.id).canonical_name == "New Entity"

        inverse = _undo(db, forward.audit_id)

        restored = db.get(KnowledgeEntity, entity.id)
        assert restored is not None
        assert restored.canonical_name == "Old Entity"
        inverse_audit = _audit(db, inverse.audit_id)
        assert inverse_audit.action_name == "entity.restore"
        assert inverse_audit.inverse_of == forward.audit_id

    def test_redo_reapplies_entity_update(self, db, spy_emit):
        entity = KnowledgeEntity(canonical_name="Old Entity")
        db.save(entity)

        forward = registry.invoke(
            db,
            "entity.update",
            {"entity_id": entity.id, "canonical_name": "New Entity"},
            _ctx(),
        )
        inverse = _undo(db, forward.audit_id)
        assert db.get(KnowledgeEntity, entity.id).canonical_name == "Old Entity"

        redo = _undo(db, inverse.audit_id)

        updated = db.get(KnowledgeEntity, entity.id)
        assert updated is not None
        assert updated.canonical_name == "New Entity"
        redo_audit = _audit(db, redo.audit_id)
        assert redo_audit.action_name == "entity.update"
        assert redo_audit.inverse_of == inverse.audit_id

    def test_update_undo_restores_snapshot_after_later_mutation(self, db, spy_emit):
        """Undo restores the captured pre-update snapshot even if the row was
        edited again before the undo runs."""
        entity = KnowledgeEntity(canonical_name="Old Entity")
        db.save(entity)

        forward = registry.invoke(
            db,
            "entity.update",
            {"entity_id": entity.id, "canonical_name": "Intermediate Entity"},
            _ctx(),
        )
        later = db.get(KnowledgeEntity, entity.id)
        assert later is not None
        later.canonical_name = "Later Entity"
        db.save(later)

        inverse = _undo(db, forward.audit_id)

        restored = db.get(KnowledgeEntity, entity.id)
        assert restored is not None
        assert restored.canonical_name == "Old Entity"
        assert _audit(db, inverse.audit_id).action_name == "entity.restore"


# ===========================================================================
# Domain 6 — entity.delete : delete -> undo(restore entity+claims) -> redo
# ===========================================================================


class TestEntityDeleteUndoRedo:
    def test_delete_undo_restores_entity_and_claim_links(self, db, spy_emit):
        entity = KnowledgeEntity(canonical_name="Delete Entity")
        db.save(entity)
        claim = _save_claim(db, text="linked", entity_ids=[entity.id])

        forward = registry.invoke(
            db,
            "entity.delete",
            {"entity_id": entity.id, "cascade_claims": False},
            _ctx(),
        )
        assert db.get(KnowledgeEntity, entity.id) is None
        assert db.get(KnowledgeClaim, claim.id) is not None
        assert entity.id not in (db.get(KnowledgeClaim, claim.id).entity_ids or [])

        inverse = _undo(db, forward.audit_id)

        restored_entity = db.get(KnowledgeEntity, entity.id)
        restored_claim = db.get(KnowledgeClaim, claim.id)
        assert restored_entity is not None
        assert restored_claim is not None
        assert entity.id in (restored_claim.entity_ids or [])
        inverse_audit = _audit(db, inverse.audit_id)
        assert inverse_audit.action_name == "entity.restore"
        assert inverse_audit.inverse_of == forward.audit_id

    def test_redo_redeletes_entity(self, db, spy_emit):
        entity = KnowledgeEntity(canonical_name="Delete Entity")
        db.save(entity)
        claim = _save_claim(db, text="linked", entity_ids=[entity.id])

        forward = registry.invoke(
            db,
            "entity.delete",
            {"entity_id": entity.id, "cascade_claims": False},
            _ctx(),
        )
        inverse = _undo(db, forward.audit_id)
        assert db.get(KnowledgeEntity, entity.id) is not None

        redo = _undo(db, inverse.audit_id)

        assert db.get(KnowledgeEntity, entity.id) is None
        persisted_claim = db.get(KnowledgeClaim, claim.id)
        assert persisted_claim is not None
        assert entity.id not in (persisted_claim.entity_ids or [])
        redo_audit = _audit(db, redo.audit_id)
        assert redo_audit.action_name == "entity.delete"
        assert redo_audit.inverse_of == inverse.audit_id

    def test_delete_undo_restores_all_touched_claim_snapshots(self, db, spy_emit):
        entity = KnowledgeEntity(canonical_name="Delete Entity")
        db.save(entity)
        claim_a = _save_claim(db, text="linked-a", entity_ids=[entity.id])
        claim_b = _save_claim(db, text="linked-b", entity_ids=[entity.id, "other-entity"])

        forward = registry.invoke(
            db,
            "entity.delete",
            {"entity_id": entity.id, "cascade_claims": False},
            _ctx(),
        )
        stripped_b = db.get(KnowledgeClaim, claim_b.id)
        assert stripped_b is not None
        assert entity.id not in (stripped_b.entity_ids or [])

        inverse = _undo(db, forward.audit_id)

        restored_a = db.get(KnowledgeClaim, claim_a.id)
        restored_b = db.get(KnowledgeClaim, claim_b.id)
        assert restored_a is not None
        assert restored_b is not None
        assert restored_a.entity_ids == [entity.id]
        assert restored_b.entity_ids == [entity.id, "other-entity"]
        assert _audit(db, inverse.audit_id).action_name == "entity.restore"

    def test_delete_undo_overwrites_later_claim_mutation_with_snapshot(self, db, spy_emit):
        entity = KnowledgeEntity(canonical_name="Delete Entity")
        db.save(entity)
        claim = _save_claim(db, text="linked", entity_ids=[entity.id])

        forward = registry.invoke(
            db,
            "entity.delete",
            {"entity_id": entity.id, "cascade_claims": False},
            _ctx(),
        )
        mutated = db.get(KnowledgeClaim, claim.id)
        assert mutated is not None
        mutated.text = "later edit"
        db.save(mutated)

        inverse = _undo(db, forward.audit_id)

        restored = db.get(KnowledgeClaim, claim.id)
        assert restored is not None
        assert restored.text == "linked"
        assert restored.entity_ids == [entity.id]
        assert _audit(db, inverse.audit_id).action_name == "entity.restore"


# ===========================================================================
# Endpoint contract — 404 / 409 guards
# ===========================================================================


class TestUndoEndpointGuards:
    def test_unknown_audit_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            _undo(db, "no-such-audit")
        assert exc.value.status_code == 404

    def test_already_undone_409(self, db, spy_emit):
        claim = _save_claim(db, text="x")
        forward = registry.invoke(db, "claim.delete", {"claim_id": claim.id}, _ctx())
        _undo(db, forward.audit_id)  # first undo succeeds
        with pytest.raises(HTTPException) as exc:
            _undo(db, forward.audit_id)  # second undo of the SAME row
        assert exc.value.status_code == 409

    def test_non_undoable_forward_action_409(self, db, spy_emit):
        """A forward action that is undoable=False (claim.restore invoked
        DIRECTLY, not as an inverse) cannot be undone -> 409. This is the
        by-design boundary: restore/unmerge are inverse-only."""
        claim = _save_claim(db, text="seed")
        snapshot = claim.model_dump(mode="json")
        # Invoke restore as a standalone forward action (inverse_of is None).
        restored = registry.invoke(db, "claim.restore", {"snapshot": snapshot}, _ctx())
        assert registry.get("claim.restore").undoable is False
        with pytest.raises(HTTPException) as exc:
            _undo(db, restored.audit_id)
        assert exc.value.status_code == 409
        assert "not undoable" in exc.value.detail


# ===========================================================================
# GET /api/actions/audit — the undo-stack history feed
# ===========================================================================


class TestAuditLogEndpoint:
    def test_log_is_newest_first_and_limited(self, db, spy_emit):
        ids = []
        for i in range(3):
            c = _save_claim(db, text=f"c{i}")
            r = registry.invoke(db, "claim.delete", {"claim_id": c.id}, _ctx())
            ids.append(r.audit_id)

        resp = _audit_log(db, limit=2)
        assert resp.count == 2                       # limit honoured
        # newest first: the last-created delete audit leads
        assert resp.items[0].id == ids[-1]
        assert resp.items[0].action_name == "claim.delete"
        assert resp.items[0].undone is False
        assert resp.items[0].undoable is True        # a fresh forward delete is reversible

    def test_log_reflects_undone_and_inverse_rows(self, db, spy_emit):
        claim = _save_claim(db, text="trace")
        forward = registry.invoke(db, "claim.delete", {"claim_id": claim.id}, _ctx())
        inverse = _undo(db, forward.audit_id)

        by_id = {e.id: e for e in _audit_log(db, limit=50).items}
        # the forward row now reads as undone (and therefore not re-undoable)
        assert by_id[forward.audit_id].undone is True
        assert by_id[forward.audit_id].undoable is False
        # the inverse row carries the back-pointer and is itself redoable
        assert by_id[inverse.audit_id].inverse_of == forward.audit_id
        assert by_id[inverse.audit_id].undoable is True

    def test_limit_is_clamped(self, db, spy_emit):
        c = _save_claim(db, text="one")
        registry.invoke(db, "claim.delete", {"claim_id": c.id}, _ctx())
        # absurd limits are clamped, not rejected
        assert _audit_log(db, limit=0).count >= 0
        assert _audit_log(db, limit=99999).count >= 1
