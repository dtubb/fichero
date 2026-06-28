"""Unit tests for the note audited actions (EPIC #1848 / sweep #2014).

Domain: NOTE. Covers, for every registered action:
  (a) the effect lands AND an ActionAudit row is written (actor / target_ids /
      before / after correct);
  (b) undo reverses it (for undoable actions) AND the redo / undo-of-undo chain
      is sane (the self-correcting ``note.restore`` inverse is exercised for
      both delete-undo and edit-undo);
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong — unknown id -> 404,
      exclude-unset patch leaves untouched fields, the page/folder scope is
      folded into linked_document_ids, the both-page-and-folder scope is
      rejected, restore preserves the SAME id, create-undo deletes the new id;
  (e) emit_change fires with the right type + scope document_ids (spy
      monkeypatched at the SOURCE ``fichero.api.change_stream.emit_change``).

These tests are MANAGER-run (workers don't run pytest). They mirror
``test_routes_conversation_actions.py`` and reuse the shared ``db`` fixture (a
real Database on a temp .fichero package). Importing the route module below
registers the note.* actions via the ``@action`` decorator at import time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Importing the route module registers the note.* actions on the
# process-global registry via the @action decorator.
import fichero.api.routes.notes  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.models import ActionAudit, Document, DocType
from fichero.knowledge_models import Note


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def emit_spy(monkeypatch):
    """Spy on the note route module's emit_change symbol."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero.api.routes.notes.emit_change",
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


def _mk_note(db, title="N", body="b", **kw) -> Note:
    note = Note(title=title, body=body, **kw)
    db.save(note)
    return note


def _mk_page(db, name="Page") -> Document:
    doc = Document(name=name, doc_type=DocType.page)
    db.save(doc)
    return doc


def _mk_folder(db, name="Folder") -> Document:
    doc = Document(name=name, doc_type=DocType.folder)
    db.save(doc)
    return doc


# ===========================================================================
# note.create — undo via delete
# ===========================================================================


class TestNoteCreateAction:
    def test_create_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        result = registry.invoke(
            db,
            "note.create",
            {"title": "Hello", "body": "world", "tags": ["t1"]},
            ctx,
        )
        assert result.ok and result.changed_domains == ["note"]
        new_id = result.result["id"]

        # effect: the note exists with the supplied fields
        note = db.get(Note, new_id)
        assert note is not None
        assert note.title == "Hello"
        assert note.body == "world"
        assert note.tags == ["t1"]

        # an ActionAudit row was written
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "note.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.before is None
        assert audit.after["id"] == new_id
        assert audit.undone is False

        # (e) emit fired as note.created
        assert emit_spy[-1][1]["type"] == "note.created"

        # undo -> note.delete removes the new row
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "note.delete"
        assert db.get(Note, new_id) is None

    def test_create_folds_page_scope_into_linked_documents(self, db):
        """A naive impl that stores only the explicit linked_document_ids would
        drop the page scope — create must fold page_id into the doc links so the
        note surfaces under that page."""
        ctx = _ctx()
        page = _mk_page(db)
        result = registry.invoke(
            db, "note.create", {"title": "Scoped", "page_id": page.id}, ctx
        )
        note = db.get(Note, result.result["id"])
        assert note.page_id == page.id
        assert page.id in note.linked_document_ids

    def test_create_emits_scope_document_ids(self, db, emit_spy):
        ctx = _ctx()
        page = _mk_page(db)
        registry.invoke(db, "note.create", {"title": "S", "page_id": page.id}, ctx)
        assert emit_spy[-1][1]["type"] == "note.created"
        assert page.id in emit_spy[-1][1]["document_ids"]

    def test_create_rejects_page_and_folder_both(self, db):
        """Scope must be page XOR folder — a note pinned to both is ambiguous."""
        ctx = _ctx()
        page = _mk_page(db)
        folder = _mk_folder(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "note.create",
                {"title": "Bad", "page_id": page.id, "folder_id": folder.id},
                ctx,
            )
        assert exc.value.status_code == 400

    def test_create_unknown_page_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "note.create", {"page_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_create_undo_then_redo_recreates(self, db):
        """create -> delete (undo) -> restore (redo) re-materializes the SAME id."""
        ctx = _ctx()
        res = registry.invoke(db, "note.create", {"title": "Cycle"}, ctx)
        nid = res.result["id"]
        del_name, del_res = _undo(db, res.audit_id, ctx)
        assert del_name == "note.delete"
        assert db.get(Note, nid) is None
        # redo = undo the delete -> note.restore re-creates same id
        inv, _ = _undo(db, del_res.audit_id, ctx)
        assert inv == "note.restore"
        assert db.get(Note, nid) is not None
        assert db.get(Note, nid).title == "Cycle"

    def test_create_validation_rejects_bad_tags(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "note.create", {"tags": "not-a-list"}, _ctx())


# ===========================================================================
# note.update — undo via restore (edit-family)
# ===========================================================================


class TestNoteUpdateAction:
    def test_update_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        note = _mk_note(db, title="Before", body="b0")
        result = registry.invoke(
            db,
            "note.update",
            {"note_id": note.id, "update": {"title": "After", "body": "b1"}},
            ctx,
        )
        assert result.ok and result.changed_domains == ["note"]

        reloaded = db.get(Note, note.id)
        assert reloaded.title == "After"
        assert reloaded.body == "b1"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "note.update"
        assert audit.target_ids == [note.id]
        assert audit.before["title"] == "Before"
        assert audit.before["body"] == "b0"
        assert audit.after["title"] == "After"
        assert audit.undone is False
        assert emit_spy[-1][1]["type"] == "note.updated"

        # undo restores the prior snapshot (via note.restore, same id)
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "note.restore"
        back = db.get(Note, note.id)
        assert back.title == "Before"
        assert back.body == "b0"

    def test_update_only_title_leaves_body(self, db):
        """exclude_unset: a patch with only ``title`` must NOT clobber ``body``.
        A naive impl that model_dumps without exclude_unset would reset body to
        its default ''."""
        ctx = _ctx()
        note = _mk_note(db, title="T1", body="keep-me")
        registry.invoke(
            db, "note.update", {"note_id": note.id, "update": {"title": "T2"}}, ctx
        )
        reloaded = db.get(Note, note.id)
        assert reloaded.title == "T2"
        assert reloaded.body == "keep-me"

    def test_update_undo_then_redo_reapplies_edit(self, db):
        """undo(update) restores the prior snapshot; undo-of-that-restore must
        RE-APPLY the edit (not delete)."""
        ctx = _ctx()
        note = _mk_note(db, title="V1")
        upd = registry.invoke(
            db, "note.update", {"note_id": note.id, "update": {"title": "V2"}}, ctx
        )
        _, restore_res = _undo(db, upd.audit_id, ctx)
        assert db.get(Note, note.id).title == "V1"
        # redo = undo the restore -> must restore V2, NOT delete
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "note.restore"
        assert db.get(Note, note.id) is not None
        assert db.get(Note, note.id).title == "V2"

    def test_update_rejects_page_and_folder_both(self, db):
        ctx = _ctx()
        page = _mk_page(db)
        folder = _mk_folder(db)
        note = _mk_note(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "note.update",
                {
                    "note_id": note.id,
                    "update": {"page_id": page.id, "folder_id": folder.id},
                },
                ctx,
            )
        assert exc.value.status_code == 400

    def test_update_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "note.update", {"note_id": "ghost", "update": {"title": "X"}}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_update_validation_rejects_missing_note_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "note.update", {"update": {"title": "no id"}}, _ctx())


# ===========================================================================
# note.delete / note.restore — undo restores SAME id, redo sane
# ===========================================================================


class TestNoteDeleteRestoreActions:
    def test_delete_effect_audit_emit_and_undo_restores_same_id(self, db, emit_spy):
        ctx = _ctx()
        page = _mk_page(db)
        note = _mk_note(
            db, title="ToDelete", body="keep", linked_document_ids=[page.id]
        )
        nid = note.id
        result = registry.invoke(db, "note.delete", {"note_id": nid}, ctx)
        assert db.get(Note, nid) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "note.delete"
        assert audit.target_ids == [nid]
        assert audit.before and audit.before["id"] == nid
        assert audit.after is None
        # emit carries the deleted note's scope so the page window refreshes
        assert emit_spy[-1][1]["type"] == "note.deleted"
        assert page.id in emit_spy[-1][1]["document_ids"]

        # undo -> note.restore re-materializes the SAME id + full state
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "note.restore"
        back = db.get(Note, nid)
        assert back is not None
        assert back.title == "ToDelete"
        assert back.body == "keep"
        assert back.linked_document_ids == [page.id]

    def test_delete_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "note.delete", {"note_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_restore_redo_chain_deletes_again(self, db):
        """delete -> restore (undo) -> undo(restore) == delete again (redo is
        sane: the restore RE-CREATED a missing row, so its inverse is delete)."""
        ctx = _ctx()
        note = _mk_note(db, title="Cycle")
        nid = note.id
        del_res = registry.invoke(db, "note.delete", {"note_id": nid}, ctx)
        restore_name, restore_res = _undo(db, del_res.audit_id, ctx)
        assert restore_name == "note.restore"
        assert db.get(Note, nid) is not None

        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "note.delete"
        assert db.get(Note, nid) is None

    def test_restore_overwrite_then_undo_reverts(self, db):
        """restore over an existing row records the prior snapshot, so its undo
        restores that prior state (edit-style), not a delete."""
        ctx = _ctx()
        note = _mk_note(db, title="Orig")
        snap = note.model_dump(mode="json")
        snap["title"] = "Overwritten"
        res = registry.invoke(db, "note.restore", {"snapshot": snap}, ctx)
        assert db.get(Note, note.id).title == "Overwritten"
        # undo the overwrite -> back to Orig
        inv, _ = _undo(db, res.audit_id, ctx)
        assert inv == "note.restore"
        assert db.get(Note, note.id).title == "Orig"

    def test_restore_validation_rejects_bad_input(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "note.restore", {"snapshot": "not-a-dict"}, _ctx())


# ===========================================================================
# Registry wiring — the note.* actions are discoverable + advertise undoable
# ===========================================================================


class TestNoteActionsRegistered:
    def test_all_note_actions_registered(self):
        names = set(registry.names())
        assert {"note.create", "note.update", "note.delete", "note.restore"} <= names

    def test_undoable_flags(self):
        assert registry.get("note.create").undoable is True
        assert registry.get("note.update").undoable is True
        assert registry.get("note.delete").undoable is True
        assert registry.get("note.restore").undoable is True
