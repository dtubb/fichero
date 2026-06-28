"""Unit tests for the conversation audited actions (EPIC #1848 / sweep #2014).

Domain: CONVERSATION. Covers, for every registered action:
  (a) the effect lands AND an ActionAudit row is written (actor / target_ids /
      before / after correct);
  (b) undo reverses it (for undoable actions) AND the redo / undo-of-undo chain
      is sane (the self-correcting ``conversation.restore`` inverse is exercised
      for both delete-undo and edit-undo);
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id -> 404,
      duplicate copies messages without aliasing the original, restore preserves
      the SAME id, delete-undo round-trips full state);
  (e) emit_change fires with the right type (spy monkeypatched at the SOURCE
      ``fichero.api.change_stream.emit_change``).

These tests are MANAGER-run (workers don't run pytest). They mirror
``test_routes_workflow_actions.py`` and reuse the shared ``db`` fixture (a real
Database on a temp .fichero package). Importing the route module below registers
the actions via the ``@action`` decorator at import time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Importing the route module registers the conversation.* actions on the
# process-global registry via the @action decorator.
import fichero.api.routes.chat  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.models import ActionAudit, Conversation


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
    ask the action for its inverse, invoke the inverse. Returns the inverse name."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None, f"{audit.action_name} not undoable"
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    res = registry.invoke(db, inv_name, inv_params, ctx)
    return inv_name, res


def _mk_conversation(
    db, title="Chat", folder_path="/", sort_order=0, messages=None, scope_document_id=None
) -> Conversation:
    conv = Conversation(
        title=title,
        folder_path=folder_path,
        sort_order=sort_order,
        messages=messages if messages is not None else [],
        provider="openai",
        model="gpt-4o-mini",
        scope_document_id=scope_document_id,
    )
    db.save(conv)
    return conv


# ===========================================================================
# conversation.update — undo via restore (edit-family)
# ===========================================================================


class TestConversationUpdateAction:
    def test_update_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        conv = _mk_conversation(db, title="Before", folder_path="/a")
        result = registry.invoke(
            db,
            "conversation.update",
            {"conversation_id": conv.id, "title": "After", "folder_path": "/b"},
            ctx,
        )
        assert result.ok and result.changed_domains == ["conversation"]

        reloaded = db.get(Conversation, conv.id)
        assert reloaded.title == "After"
        assert reloaded.folder_path == "/b"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "conversation.update"
        assert audit.actor == "ui"
        assert audit.target_ids == [conv.id]
        assert audit.before["title"] == "Before"
        assert audit.before["folder_path"] == "/a"
        assert audit.after["title"] == "After"
        assert audit.undone is False

        # (e) emit fired with the right type
        assert emit_spy[-1][1]["type"] == "conversation.updated"

        # undo restores the prior snapshot (via conversation.restore, same id)
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "conversation.restore"
        back = db.get(Conversation, conv.id)
        assert back is not None
        assert back.title == "Before"
        assert back.folder_path == "/a"

    def test_update_only_title_leaves_folder(self, db):
        """A naive impl that always overwrites folder_path would clobber it when
        only the title is supplied — None means 'leave unchanged'."""
        ctx = _ctx()
        conv = _mk_conversation(db, title="T1", folder_path="/keep")
        registry.invoke(
            db, "conversation.update", {"conversation_id": conv.id, "title": "T2"}, ctx
        )
        reloaded = db.get(Conversation, conv.id)
        assert reloaded.title == "T2"
        assert reloaded.folder_path == "/keep"

    def test_update_undo_then_redo_reapplies_edit(self, db):
        """The self-correcting restore inverse: undo(update) restores the prior
        snapshot; undo-of-that-restore must RE-APPLY the edit (not delete)."""
        ctx = _ctx()
        conv = _mk_conversation(db, title="V1")
        upd = registry.invoke(
            db, "conversation.update", {"conversation_id": conv.id, "title": "V2"}, ctx
        )
        # undo -> restore V1
        _, restore_res = _undo(db, upd.audit_id, ctx)
        assert db.get(Conversation, conv.id).title == "V1"

        # redo = undo the restore -> must restore V2 (re-apply the edit), NOT delete
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "conversation.restore"
        assert db.get(Conversation, conv.id) is not None
        assert db.get(Conversation, conv.id).title == "V2"

    def test_update_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "conversation.update", {"conversation_id": "ghost", "title": "X"}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_update_validation_rejects_missing_conversation_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "conversation.update", {"title": "no id"}, _ctx())


# ===========================================================================
# conversation.duplicate — pure copy, NOT undoable
# ===========================================================================


class TestConversationDuplicateAction:
    def test_duplicate_effect_audit_emit(self, db, emit_spy):
        ctx = _ctx()
        original = _mk_conversation(
            db, title="Original", messages=[{"role": "user", "content": "hi"}]
        )
        result = registry.invoke(
            db, "conversation.duplicate", {"conversation_id": original.id}, ctx
        )
        new_id = result.result["id"]

        # effect: a distinct copy with the "(Copy)" title and copied messages
        copy = db.get(Conversation, new_id)
        assert copy is not None
        assert new_id != original.id
        assert copy.title == "Original (Copy)"
        assert copy.messages == [{"role": "user", "content": "hi"}]
        # original untouched
        assert db.get(Conversation, original.id) is not None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "conversation.duplicate"
        assert audit.target_ids == [new_id]
        assert audit.before is None
        assert audit.after["id"] == new_id

        # not undoable (sweep scope)
        assert registry.get("conversation.duplicate").undoable is False
        assert emit_spy[-1][1]["type"] == "conversation.created"

    def test_duplicate_messages_not_aliased(self, db):
        """Mutating the copy's messages must NOT bleed back into the original
        (the impl copies the list, so this guards against a shared reference)."""
        ctx = _ctx()
        original = _mk_conversation(
            db, title="Src", messages=[{"role": "user", "content": "a"}]
        )
        result = registry.invoke(
            db, "conversation.duplicate", {"conversation_id": original.id}, ctx
        )
        copy = db.get(Conversation, result.result["id"])
        copy.messages.append({"role": "assistant", "content": "b"})
        db.save(copy)

        reloaded_original = db.get(Conversation, original.id)
        assert reloaded_original.messages == [{"role": "user", "content": "a"}]

    def test_duplicate_preserves_scope_document_id(self, db):
        ctx = _ctx()
        original = _mk_conversation(
            db,
            title="Scoped",
            scope_document_id="folder-1",
        )

        result = registry.invoke(
            db, "conversation.duplicate", {"conversation_id": original.id}, ctx
        )

        assert db.get(Conversation, result.result["id"]).scope_document_id == "folder-1"

    def test_duplicate_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "conversation.duplicate", {"conversation_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_duplicate_validation_rejects_missing_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "conversation.duplicate", {}, _ctx())


# ===========================================================================
# conversation.delete / conversation.restore — undo restores SAME id, redo sane
# ===========================================================================


class TestConversationDeleteRestoreActions:
    def test_delete_effect_audit_emit_and_undo_restores_same_id(self, db, emit_spy):
        ctx = _ctx()
        conv = _mk_conversation(
            db, title="ToDelete", messages=[{"role": "user", "content": "keep me"}]
        )
        cid = conv.id
        result = registry.invoke(db, "conversation.delete", {"conversation_id": cid}, ctx)
        assert db.get(Conversation, cid) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "conversation.delete"
        assert audit.target_ids == [cid]
        assert audit.before and audit.before["id"] == cid
        assert audit.after is None
        assert emit_spy[-1][1]["type"] == "conversation.deleted"

        # undo -> conversation.restore re-materializes the SAME id + full state
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "conversation.restore"
        back = db.get(Conversation, cid)
        assert back is not None
        assert back.title == "ToDelete"
        assert back.messages == [{"role": "user", "content": "keep me"}]

    def test_delete_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "conversation.delete", {"conversation_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_restore_redo_chain_deletes_again(self, db):
        """delete -> restore -> undo(restore) == delete again (redo is sane:
        the restore RE-CREATED a missing row, so its inverse is delete)."""
        ctx = _ctx()
        conv = _mk_conversation(db, title="Cycle")
        cid = conv.id
        del_res = registry.invoke(db, "conversation.delete", {"conversation_id": cid}, ctx)
        restore_name, restore_res = _undo(db, del_res.audit_id, ctx)
        assert restore_name == "conversation.restore"
        assert db.get(Conversation, cid) is not None

        # undo the restore -> deletes again
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "conversation.delete"
        assert db.get(Conversation, cid) is None

    def test_restore_validation_rejects_bad_input(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "conversation.restore", {"snapshot": "not-a-dict"}, _ctx())
