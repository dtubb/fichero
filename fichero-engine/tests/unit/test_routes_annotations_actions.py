"""Unit tests for the annotation audited actions (EPIC #1848 / sweep #2014).

Domain: ANNOTATION. Covers, for every registered action:
  (a) the effect lands AND an ActionAudit row is written (actor / target_ids /
      before / after correct);
  (b) undo reverses it (for undoable actions) AND the redo / undo-of-undo chain
      is sane (the self-correcting ``annotation.restore`` inverse is exercised
      for both delete-undo and edit-undo);
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong — unknown id -> 404,
      exclude-unset patch leaves untouched fields, the page scope is folded into
      document_id, the both-page-and-folder scope is rejected, restore preserves
      the SAME id, create-undo deletes the new id, promote requires a document
      scope + uses the highlighted excerpt;
  (e) emit_change fires with the right type + scope document_ids (spy
      monkeypatched at the SOURCE ``fichero.api.change_stream.emit_change``).

These tests are MANAGER-run (workers don't run pytest). They mirror
``test_routes_notes_actions.py`` and reuse the shared ``db`` fixture (a real
Database on a temp .fichero package). Importing the route module below registers
the annotation.* actions via the ``@action`` decorator at import time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Importing the route module registers the annotation.* actions on the
# process-global registry via the @action decorator.
import fichero.api.routes.annotations  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.models import ActionAudit, Document, DocType
from fichero.models.knowledge import Annotation, AnnotationKind, KnowledgeClaim


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def emit_spy(monkeypatch):
    """Spy on emit_change at the SOURCE module (where registry._emit imports it)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _undo(db, audit_id, ctx):
    """Drive undo exactly as the generic undo endpoint would: read the audit,
    ask the action for its inverse, invoke the inverse. Returns (name, result)."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None, f"{audit.action_name} not undoable"
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    res = registry.invoke(db, inv_name, inv_params, ctx)
    return inv_name, res


def _mk_doc(db, name="Doc", page_content=None) -> Document:
    doc = Document(name=name, doc_type=DocType.file, page_content=page_content)
    db.save(doc)
    return doc


def _mk_page(db, name="Page") -> Document:
    doc = Document(name=name, doc_type=DocType.page)
    db.save(doc)
    return doc


def _mk_folder(db, name="Folder") -> Document:
    doc = Document(name=name, doc_type=DocType.folder)
    db.save(doc)
    return doc


def _mk_annotation(db, doc=None, **kw) -> Annotation:
    """Build + persist an annotation scoped to a file document (the default
    scope promote/delete tests need)."""
    if doc is None:
        doc = _mk_doc(db)
    kw.setdefault("kind", AnnotationKind.note)
    ann = Annotation(document_id=doc.id, **kw)
    db.save(ann)
    return ann


# ===========================================================================
# annotation.create — undo via delete
# ===========================================================================


class TestAnnotationCreateAction:
    def test_create_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        doc = _mk_doc(db)
        result = registry.invoke(
            db,
            "annotation.create",
            {
                "document_id": doc.id,
                "kind": "note",
                "text": "hello",
                "tags": ["t1"],
            },
            ctx,
        )
        assert result.ok and result.changed_domains == ["annotation"]
        new_id = result.result["id"]

        # effect: the annotation exists with the supplied fields
        ann = db.get(Annotation, new_id)
        assert ann is not None
        assert ann.text == "hello"
        assert ann.tags == ["t1"]
        assert ann.document_id == doc.id

        # an ActionAudit row was written
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "annotation.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.before is None
        assert audit.after["id"] == new_id
        assert audit.undone is False

        # (e) emit fired as annotation.created carrying the scope doc id
        assert emit_spy[-1][1]["type"] == "annotation.created"
        assert doc.id in emit_spy[-1][1]["document_ids"]

        # undo -> annotation.delete removes the new row
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "annotation.delete"
        assert db.get(Annotation, new_id) is None

    def test_create_folds_page_scope_into_document_id(self, db):
        """A page-scoped annotation must resolve document_id == page_id so it
        surfaces under that page — a naive impl that left document_id None would
        drop the anchor."""
        ctx = _ctx()
        page = _mk_page(db)
        result = registry.invoke(
            db, "annotation.create", {"page_id": page.id, "kind": "highlight"}, ctx
        )
        ann = db.get(Annotation, result.result["id"])
        assert ann.page_id == page.id
        assert ann.document_id == page.id

    def test_create_rejects_page_and_folder_both(self, db):
        """Scope must be page XOR folder — pinned to both is ambiguous (400)."""
        ctx = _ctx()
        page = _mk_page(db)
        folder = _mk_folder(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "annotation.create",
                {"page_id": page.id, "folder_id": folder.id, "kind": "note"},
                ctx,
            )
        assert exc.value.status_code == 400

    def test_create_unknown_document_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "annotation.create", {"document_id": "ghost", "kind": "note"}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_create_requires_scope(self, db):
        """No document/page/folder scope at all -> 400 (annotations must anchor)."""
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "annotation.create", {"kind": "note"}, _ctx())
        assert exc.value.status_code == 400

    def test_create_undo_then_redo_recreates(self, db):
        """create -> delete (undo) -> restore (redo) re-materializes the SAME id."""
        ctx = _ctx()
        doc = _mk_doc(db)
        res = registry.invoke(
            db, "annotation.create", {"document_id": doc.id, "kind": "note", "text": "x"}, ctx
        )
        aid = res.result["id"]
        del_name, del_res = _undo(db, res.audit_id, ctx)
        assert del_name == "annotation.delete"
        assert db.get(Annotation, aid) is None
        # redo = undo the delete -> annotation.restore re-creates same id
        inv, _ = _undo(db, del_res.audit_id, ctx)
        assert inv == "annotation.restore"
        back = db.get(Annotation, aid)
        assert back is not None and back.text == "x"

    def test_create_validation_rejects_bad_kind(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "annotation.create", {"document_id": "d", "kind": "bogus"}, _ctx()
            )

    def test_create_validation_rejects_missing_kind(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "annotation.create", {"document_id": "d"}, _ctx())


# ===========================================================================
# annotation.update — undo via restore (edit-family)
# ===========================================================================


class TestAnnotationUpdateAction:
    def test_update_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        ann = _mk_annotation(db, text="Before", rating=2)
        result = registry.invoke(
            db,
            "annotation.update",
            {"annotation_id": ann.id, "update": {"text": "After", "rating": 4}},
            ctx,
        )
        assert result.ok and result.changed_domains == ["annotation"]

        reloaded = db.get(Annotation, ann.id)
        assert reloaded.text == "After"
        assert reloaded.rating == 4

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "annotation.update"
        assert audit.target_ids == [ann.id]
        assert audit.before["text"] == "Before"
        assert audit.before["rating"] == 2
        assert audit.after["text"] == "After"
        assert audit.undone is False
        assert emit_spy[-1][1]["type"] == "annotation.updated"

        # undo restores the prior snapshot (via annotation.restore, same id)
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "annotation.restore"
        back = db.get(Annotation, ann.id)
        assert back.text == "Before"
        assert back.rating == 2

    def test_update_only_text_leaves_rating(self, db):
        """exclude_unset: a patch with only ``text`` must NOT clobber ``rating``.
        A naive impl that model_dumps without exclude_unset would reset rating to
        its None default."""
        ctx = _ctx()
        ann = _mk_annotation(db, text="t1", rating=5)
        registry.invoke(
            db, "annotation.update", {"annotation_id": ann.id, "update": {"text": "t2"}}, ctx
        )
        reloaded = db.get(Annotation, ann.id)
        assert reloaded.text == "t2"
        assert reloaded.rating == 5

    def test_update_undo_then_redo_reapplies_edit(self, db):
        """undo(update) restores the prior snapshot; undo-of-that-restore must
        RE-APPLY the edit (not delete)."""
        ctx = _ctx()
        ann = _mk_annotation(db, text="V1")
        upd = registry.invoke(
            db, "annotation.update", {"annotation_id": ann.id, "update": {"text": "V2"}}, ctx
        )
        _, restore_res = _undo(db, upd.audit_id, ctx)
        assert db.get(Annotation, ann.id).text == "V1"
        # redo = undo the restore -> must restore V2, NOT delete
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "annotation.restore"
        assert db.get(Annotation, ann.id).text == "V2"

    def test_update_rejects_page_and_folder_both(self, db):
        ctx = _ctx()
        page = _mk_page(db)
        folder = _mk_folder(db)
        ann = _mk_annotation(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "annotation.update",
                {
                    "annotation_id": ann.id,
                    "update": {"page_id": page.id, "folder_id": folder.id},
                },
                ctx,
            )
        assert exc.value.status_code == 400

    def test_update_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "annotation.update",
                {"annotation_id": "ghost", "update": {"text": "x"}},
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_update_validation_rejects_missing_annotation_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "annotation.update", {"update": {"text": "no id"}}, _ctx())


# ===========================================================================
# annotation.delete / annotation.restore — undo restores SAME id, redo sane
# ===========================================================================


class TestAnnotationDeleteRestoreActions:
    def test_delete_effect_audit_emit_and_undo_restores_same_id(self, db, emit_spy):
        ctx = _ctx()
        doc = _mk_doc(db)
        ann = _mk_annotation(db, doc=doc, text="ToDelete", rating=3)
        aid = ann.id
        result = registry.invoke(db, "annotation.delete", {"annotation_id": aid}, ctx)
        assert db.get(Annotation, aid) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "annotation.delete"
        assert audit.target_ids == [aid]
        assert audit.before and audit.before["id"] == aid
        assert audit.after is None
        # emit carries the deleted annotation's scope so the doc window refreshes
        assert emit_spy[-1][1]["type"] == "annotation.deleted"
        assert doc.id in emit_spy[-1][1]["document_ids"]

        # undo -> annotation.restore re-materializes the SAME id + full state
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "annotation.restore"
        back = db.get(Annotation, aid)
        assert back is not None
        assert back.text == "ToDelete"
        assert back.rating == 3
        assert back.document_id == doc.id

    def test_delete_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "annotation.delete", {"annotation_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_restore_redo_chain_deletes_again(self, db):
        """delete -> restore (undo) -> undo(restore) == delete again (redo is
        sane: the restore RE-CREATED a missing row, so its inverse is delete)."""
        ctx = _ctx()
        ann = _mk_annotation(db, text="Cycle")
        aid = ann.id
        del_res = registry.invoke(db, "annotation.delete", {"annotation_id": aid}, ctx)
        restore_name, restore_res = _undo(db, del_res.audit_id, ctx)
        assert restore_name == "annotation.restore"
        assert db.get(Annotation, aid) is not None

        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "annotation.delete"
        assert db.get(Annotation, aid) is None

    def test_restore_overwrite_then_undo_reverts(self, db):
        """restore over an existing row records the prior snapshot, so its undo
        restores that prior state (edit-style), not a delete."""
        ctx = _ctx()
        ann = _mk_annotation(db, text="Orig")
        snap = ann.model_dump(mode="json")
        snap["text"] = "Overwritten"
        res = registry.invoke(db, "annotation.restore", {"snapshot": snap}, ctx)
        assert db.get(Annotation, ann.id).text == "Overwritten"
        # undo the overwrite -> back to Orig
        inv, _ = _undo(db, res.audit_id, ctx)
        assert inv == "annotation.restore"
        assert db.get(Annotation, ann.id).text == "Orig"

    def test_restore_validation_rejects_bad_input(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "annotation.restore", {"snapshot": "not-a-dict"}, _ctx())


class TestAnnotationRoutesWriteActionAudit:
    def test_create_round_trips_ink_and_ocr_provenance(self, client, db):
        doc = _mk_doc(db)
        response = client.post(
            "/api/annotations",
            json={
                "document_id": doc.id,
                "kind": "note",
                "anchor_kind": "paragraph",
                "paragraph_index": 2,
                "ink_payload": "pencilkit-data",
                "ocr_text": "marginal note",
                "ocr_provider": "apple",
                "ocr_model": "vision",
                "ocr_confidence": 0.9,
            },
        )
        assert response.status_code == 200
        assert response.json()["ink_payload"] == "pencilkit-data"
        assert response.json()["ocr_text"] == "marginal note"

    def test_create_patch_delete_routes_write_action_audit(self, client, db):
        doc = _mk_doc(db)

        created = client.post(
            "/api/annotations",
            json={"document_id": doc.id, "kind": "note", "text": "route"},
        )
        assert created.status_code == 200
        annotation_id = created.json()["id"]
        assert db.all(ActionAudit)[-1].action_name == "annotation.create"
        assert db.all(ActionAudit)[-1].target_ids == [annotation_id]

        patched = client.patch(
            f"/api/annotations/{annotation_id}",
            json={"text": "updated route"},
        )
        assert patched.status_code == 200
        assert db.all(ActionAudit)[-1].action_name == "annotation.update"
        assert db.all(ActionAudit)[-1].target_ids == [annotation_id]

        deleted = client.delete(f"/api/annotations/{annotation_id}")
        assert deleted.status_code == 204
        assert db.all(ActionAudit)[-1].action_name == "annotation.delete"
        assert db.all(ActionAudit)[-1].target_ids == [annotation_id]


# ===========================================================================
# annotation.promote_to_claim — audited but NOT undoable
# ===========================================================================


class TestAnnotationPromoteToClaimAction:
    def test_promote_effect_audit_and_emit(self, db, emit_spy):
        ctx = _ctx()
        doc = _mk_doc(db, page_content="The quick brown fox jumps over the lazy dog")
        # char span selects "quick brown" -> source_excerpt; text drives claim.text
        ann = _mk_annotation(
            db, doc=doc, kind=AnnotationKind.highlight, text="A claim", char_start=4, char_end=15
        )
        result = registry.invoke(
            db, "annotation.promote_to_claim", {"annotation_id": ann.id}, ctx
        )
        assert result.ok
        assert set(result.changed_domains) == {"annotation", "claim"}
        claim_id = result.result["claim_id"]

        # effect: a claim exists, anchored to the document, with the highlighted
        # excerpt, and the annotation links back to it
        claim = db.get(KnowledgeClaim, claim_id)
        assert claim is not None
        assert claim.text == "A claim"
        assert claim.source_document_id == doc.id
        assert claim.source_excerpt == "quick brown"
        reloaded = db.get(Annotation, ann.id)
        assert claim_id in reloaded.linked_claim_ids

        # audit row carries both touched ids + the pre-mutation annotation snapshot
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "annotation.promote_to_claim"
        assert ann.id in audit.target_ids and claim_id in audit.target_ids
        assert audit.before["id"] == ann.id
        assert audit.after["claim_id"] == claim_id

        # emit announces the new claim
        assert emit_spy[-1][1]["type"] == "claim.created"
        assert claim_id in emit_spy[-1][1]["claim_ids"]

    def test_promote_falls_back_to_text_when_no_span(self, db):
        """No char span -> the excerpt falls back to the annotation text (a naive
        impl that demanded a span would 500)."""
        ctx = _ctx()
        ann = _mk_annotation(db, text="bare note", kind=AnnotationKind.note)
        result = registry.invoke(
            db, "annotation.promote_to_claim", {"annotation_id": ann.id}, ctx
        )
        claim = db.get(KnowledgeClaim, result.result["claim_id"])
        assert claim.text == "bare note"
        assert claim.source_excerpt == "bare note"

    def test_promote_folder_scoped_rejected(self, db):
        """Folder-scoped annotations have no document anchor -> 400."""
        ctx = _ctx()
        folder = _mk_folder(db)
        ann = Annotation(folder_id=folder.id, kind=AnnotationKind.note, text="x")
        db.save(ann)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "annotation.promote_to_claim", {"annotation_id": ann.id}, ctx)
        assert exc.value.status_code == 400

    def test_promote_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "annotation.promote_to_claim", {"annotation_id": "ghost"}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_promote_validation_rejects_missing_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "annotation.promote_to_claim", {}, _ctx())

    def test_promote_is_not_undoable(self, db):
        """Promote is audited but intentionally not auto-reversible (a single
        restore would orphan the created claim)."""
        reg = registry.get("annotation.promote_to_claim")
        assert reg.undoable is False
        assert reg.invert is None


# ===========================================================================
# Registry wiring — the annotation.* actions are discoverable + advertise flags
# ===========================================================================


class TestAnnotationActionsRegistered:
    def test_all_annotation_actions_registered(self):
        names = set(registry.names())
        assert {
            "annotation.create",
            "annotation.update",
            "annotation.delete",
            "annotation.restore",
            "annotation.promote_to_claim",
        } <= names

    def test_undoable_flags(self):
        assert registry.get("annotation.create").undoable is True
        assert registry.get("annotation.update").undoable is True
        assert registry.get("annotation.delete").undoable is True
        assert registry.get("annotation.restore").undoable is True
        assert registry.get("annotation.promote_to_claim").undoable is False
