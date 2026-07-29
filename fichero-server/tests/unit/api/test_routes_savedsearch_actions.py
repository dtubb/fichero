"""Unit tests for the saved-search audited actions (EPIC #1848 / sweep #2014).

Domain: SAVED SEARCH. Covers, for every registered action:
  (a) the effect lands AND an ActionAudit row is written (actor / target_ids /
      before / after correct);
  (b) undo reverses it (for undoable actions) AND the redo / undo-of-undo chain
      is sane (the self-correcting ``savedsearch.restore`` inverse is exercised
      for both delete-undo and edit-undo);
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id -> 404,
      partial update leaves untouched fields, duplicate makes a distinct row,
      restore preserves the SAME id, reorder records prior orders, empty
      reorder no-ops);
  (e) emit_change fires with the right type (spy monkeypatched at the SOURCE
      ``fichero_server.api.change_stream.emit_change``).

These tests are MANAGER-run (workers don't run pytest). They mirror
``test_routes_conversation_actions.py`` and reuse the shared ``db`` fixture (a
real Database on a temp .fichero package). Importing the route module below
registers the actions via the ``@action`` decorator at import time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Importing the route module registers the savedsearch.* actions on the
# process-global registry via the @action decorator.
import fichero_server.api.routes.search  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, SavedSearch


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def emit_spy(monkeypatch):
    """Spy on emit_change at the SOURCE module (where registry._emit imports it)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
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


def _mk_saved_search(
    db, query="racial inequality", folder_path="/", sort_order=0, **kw
) -> SavedSearch:
    saved = SavedSearch(
        query=query, folder_path=folder_path, sort_order=sort_order, **kw
    )
    db.save(saved)
    return saved


# ===========================================================================
# Fixture sanity — the test factory supplies every REQUIRED model field
# ===========================================================================


def test_factory_supplies_all_required_fields():
    """If SavedSearch grows a required field, _mk_saved_search must too —
    otherwise the whole suite silently constructs invalid rows."""
    required = {
        name
        for name, field in SavedSearch.model_fields.items()
        if field.is_required()
    }
    # ``query`` is the only required field today; the factory always passes it.
    assert required <= {"query"}
    # And it really does build a valid persisted row.
    saved = SavedSearch(query="q")
    assert saved.id and saved.query == "q"


# ===========================================================================
# savedsearch.save — create, undo via delete
# ===========================================================================


class TestSavedSearchSaveAction:
    def test_save_effect_audit_emit(self, db, emit_spy):
        ctx = _ctx()
        result = registry.invoke(
            db,
            "savedsearch.save",
            {"query": "Asprilla", "folder_path": "/people", "sort_order": 3},
            ctx,
        )
        assert result.ok and result.changed_domains == ["savedsearch"]
        new_id = result.result["id"]

        saved = db.get(SavedSearch, new_id)
        assert saved is not None
        assert saved.query == "Asprilla"
        assert saved.folder_path == "/people"
        assert saved.sort_order == 3

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "savedsearch.save"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.before is None
        assert audit.after["id"] == new_id
        assert audit.undone is False

        assert registry.get("savedsearch.save").undoable is True
        assert emit_spy[-1][1]["type"] == "savedsearch.created"

        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "savedsearch.delete"
        assert db.get(SavedSearch, new_id) is None

    def test_save_uses_create_defaults(self, db):
        """A naive impl that drops unspecified fields would lose the defaults;
        the create model fills hybrid/relevance/desc/'/' for us."""
        ctx = _ctx()
        result = registry.invoke(db, "savedsearch.save", {"query": "q"}, ctx)
        saved = db.get(SavedSearch, result.result["id"])
        assert saved.is_smart_search is True
        assert saved.search_type == "hybrid"
        assert saved.sort_by == "relevance"
        assert saved.sort_direction == "desc"
        assert saved.folder_path == "/"

    def test_save_validation_rejects_missing_query(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "savedsearch.save", {"folder_path": "/x"}, _ctx())

    def test_save_undo_then_redo_recreates_search(self, db):
        ctx = _ctx()
        created = registry.invoke(db, "savedsearch.save", {"query": "yo-yo"}, ctx)
        sid = created.result["id"]

        _, delete_res = _undo(db, created.audit_id, ctx)
        assert db.get(SavedSearch, sid) is None

        inv, _ = _undo(db, delete_res.audit_id, ctx)
        assert inv == "savedsearch.restore"
        restored = db.get(SavedSearch, sid)
        assert restored is not None
        assert restored.query == "yo-yo"


# ===========================================================================
# savedsearch.update — undo via restore (edit-family)
# ===========================================================================


class TestSavedSearchUpdateAction:
    def test_update_effect_audit_emit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        saved = _mk_saved_search(db, query="Before", folder_path="/a")
        result = registry.invoke(
            db,
            "savedsearch.update",
            {"search_id": saved.id, "query": "After", "folder_path": "/b"},
            ctx,
        )
        assert result.ok and result.changed_domains == ["savedsearch"]

        reloaded = db.get(SavedSearch, saved.id)
        assert reloaded.query == "After"
        assert reloaded.folder_path == "/b"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "savedsearch.update"
        assert audit.actor == "ui"
        assert audit.target_ids == [saved.id]
        assert audit.before["query"] == "Before"
        assert audit.before["folder_path"] == "/a"
        assert audit.after["query"] == "After"
        assert audit.undone is False

        assert emit_spy[-1][1]["type"] == "savedsearch.updated"

        # undo restores the prior snapshot (via savedsearch.restore, same id)
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "savedsearch.restore"
        back = db.get(SavedSearch, saved.id)
        assert back is not None
        assert back.query == "Before"
        assert back.folder_path == "/a"

    def test_update_only_query_leaves_folder(self, db):
        """A naive impl that always overwrites folder_path would clobber it when
        only the query is supplied — None means 'leave unchanged'."""
        ctx = _ctx()
        saved = _mk_saved_search(db, query="Q1", folder_path="/keep")
        registry.invoke(
            db, "savedsearch.update", {"search_id": saved.id, "query": "Q2"}, ctx
        )
        reloaded = db.get(SavedSearch, saved.id)
        assert reloaded.query == "Q2"
        assert reloaded.folder_path == "/keep"

    def test_update_undo_then_redo_reapplies_edit(self, db):
        """The self-correcting restore inverse: undo(update) restores the prior
        snapshot; undo-of-that-restore must RE-APPLY the edit (not delete)."""
        ctx = _ctx()
        saved = _mk_saved_search(db, query="V1")
        upd = registry.invoke(
            db, "savedsearch.update", {"search_id": saved.id, "query": "V2"}, ctx
        )
        # undo -> restore V1
        _, restore_res = _undo(db, upd.audit_id, ctx)
        assert db.get(SavedSearch, saved.id).query == "V1"

        # redo = undo the restore -> must restore V2 (re-apply the edit), NOT delete
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "savedsearch.restore"
        assert db.get(SavedSearch, saved.id) is not None
        assert db.get(SavedSearch, saved.id).query == "V2"

    def test_update_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "savedsearch.update", {"search_id": "ghost", "query": "X"}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_update_validation_rejects_missing_search_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "savedsearch.update", {"query": "no id"}, _ctx())


# ===========================================================================
# savedsearch.duplicate — pure copy, undo via delete
# ===========================================================================


class TestSavedSearchDuplicateAction:
    def test_duplicate_effect_audit_emit(self, db, emit_spy):
        ctx = _ctx()
        original = _mk_saved_search(db, query="Original", folder_path="/p", sort_order=5)
        result = registry.invoke(
            db, "savedsearch.duplicate", {"search_id": original.id}, ctx
        )
        new_id = result.result["id"]

        # effect: a distinct copy carrying the same properties
        copy = db.get(SavedSearch, new_id)
        assert copy is not None
        assert new_id != original.id
        assert copy.query == "Original"
        assert copy.folder_path == "/p"
        assert copy.sort_order == 5
        # original untouched
        assert db.get(SavedSearch, original.id) is not None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "savedsearch.duplicate"
        assert audit.target_ids == [new_id]
        assert audit.before is None
        assert audit.after["id"] == new_id

        assert registry.get("savedsearch.duplicate").undoable is True
        assert emit_spy[-1][1]["type"] == "savedsearch.created"

        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "savedsearch.delete"
        assert db.get(SavedSearch, new_id) is None

    def test_duplicate_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "savedsearch.duplicate", {"search_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_duplicate_validation_rejects_missing_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "savedsearch.duplicate", {}, _ctx())

    def test_duplicate_undo_then_redo_restores_copy(self, db):
        ctx = _ctx()
        original = _mk_saved_search(db, query="Original", folder_path="/p", sort_order=5)
        duplicated = registry.invoke(
            db, "savedsearch.duplicate", {"search_id": original.id}, ctx
        )
        new_id = duplicated.result["id"]

        _, delete_res = _undo(db, duplicated.audit_id, ctx)
        assert db.get(SavedSearch, new_id) is None

        inv, _ = _undo(db, delete_res.audit_id, ctx)
        assert inv == "savedsearch.restore"
        restored = db.get(SavedSearch, new_id)
        assert restored is not None
        assert restored.query == "Original"

    def test_duplicate_undo_deletes_copy_even_after_later_edit(self, db):
        ctx = _ctx()
        original = _mk_saved_search(db, query="Original", folder_path="/p", sort_order=5)
        duplicated = registry.invoke(
            db, "savedsearch.duplicate", {"search_id": original.id}, ctx
        )
        new_id = duplicated.result["id"]

        copy = db.get(SavedSearch, new_id)
        assert copy is not None
        copy.query = "Edited Copy"
        db.save(copy)

        inv, _ = _undo(db, duplicated.audit_id, ctx)
        assert inv == "savedsearch.delete"
        assert db.get(SavedSearch, new_id) is None


# ===========================================================================
# savedsearch.delete / savedsearch.restore — undo restores SAME id, redo sane
# ===========================================================================


class TestSavedSearchDeleteRestoreActions:
    def test_delete_effect_audit_emit_and_undo_restores_same_id(self, db, emit_spy):
        ctx = _ctx()
        saved = _mk_saved_search(db, query="ToDelete", folder_path="/d", sort_order=2)
        sid = saved.id
        result = registry.invoke(db, "savedsearch.delete", {"search_id": sid}, ctx)
        assert db.get(SavedSearch, sid) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "savedsearch.delete"
        assert audit.target_ids == [sid]
        assert audit.before and audit.before["id"] == sid
        assert audit.after is None
        assert emit_spy[-1][1]["type"] == "savedsearch.deleted"

        # undo -> savedsearch.restore re-materializes the SAME id + full state
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "savedsearch.restore"
        back = db.get(SavedSearch, sid)
        assert back is not None
        assert back.query == "ToDelete"
        assert back.folder_path == "/d"
        assert back.sort_order == 2

    def test_delete_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "savedsearch.delete", {"search_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_restore_redo_chain_deletes_again(self, db):
        """delete -> restore -> undo(restore) == delete again (redo is sane:
        the restore RE-CREATED a missing row, so its inverse is delete)."""
        ctx = _ctx()
        saved = _mk_saved_search(db, query="Cycle")
        sid = saved.id
        del_res = registry.invoke(db, "savedsearch.delete", {"search_id": sid}, ctx)
        restore_name, restore_res = _undo(db, del_res.audit_id, ctx)
        assert restore_name == "savedsearch.restore"
        assert db.get(SavedSearch, sid) is not None

        # undo the restore -> deletes again
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "savedsearch.delete"
        assert db.get(SavedSearch, sid) is None

    def test_restore_validation_rejects_bad_input(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "savedsearch.restore", {"snapshot": "not-a-dict"}, _ctx())


# ===========================================================================
# savedsearch.reorder — multi-row renumber, undo via prior sort-order map
# ===========================================================================


class TestSavedSearchReorderAction:
    def test_reorder_effect_audit_emit(self, db, emit_spy):
        ctx = _ctx()
        a = _mk_saved_search(db, query="A", sort_order=0)
        b = _mk_saved_search(db, query="B", sort_order=1)
        c = _mk_saved_search(db, query="C", sort_order=2)

        # New order: c, a, b
        result = registry.invoke(
            db, "savedsearch.reorder", {"search_ids": [c.id, a.id, b.id]}, ctx
        )
        assert result.result["count"] == 3

        assert db.get(SavedSearch, c.id).sort_order == 0
        assert db.get(SavedSearch, a.id).sort_order == 1
        assert db.get(SavedSearch, b.id).sort_order == 2

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "savedsearch.reorder"
        assert audit.target_ids == [c.id, a.id, b.id]
        # before/after carry the prior + new positions so the move is recorded
        assert audit.before["sort_orders"] == {c.id: 2, a.id: 0, b.id: 1}
        assert audit.after["sort_orders"] == {c.id: 0, a.id: 1, b.id: 2}
        assert emit_spy[-1][1]["type"] == "savedsearch.reordered"
        assert registry.get("savedsearch.reorder").undoable is True

        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "savedsearch.restore_order"
        assert db.get(SavedSearch, a.id).sort_order == 0
        assert db.get(SavedSearch, b.id).sort_order == 1
        assert db.get(SavedSearch, c.id).sort_order == 2

    def test_reorder_unknown_id_404(self, db):
        """A missing id mid-list 404s; the existing route semantics (partial
        renumber up to the failure) are preserved — guard the contract."""
        ctx = _ctx()
        a = _mk_saved_search(db, query="A", sort_order=7)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "savedsearch.reorder", {"search_ids": [a.id, "ghost"]}, ctx
            )
        assert exc.value.status_code == 404
        # a was renumbered to position 0 before the failure (route parity)
        assert db.get(SavedSearch, a.id).sort_order == 0

    def test_reorder_empty_list_no_op(self, db, emit_spy):
        ctx = _ctx()
        result = registry.invoke(db, "savedsearch.reorder", {"search_ids": []}, ctx)
        assert result.result["count"] == 0
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["sort_orders"] == {}
        assert audit.after["sort_orders"] == {}

    def test_reorder_validation_rejects_non_list(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "savedsearch.reorder", {"search_ids": "not-a-list-of-ids"}, _ctx()
            )

    def test_reorder_undo_then_redo_reapplies_order(self, db):
        ctx = _ctx()
        a = _mk_saved_search(db, query="A", sort_order=0)
        b = _mk_saved_search(db, query="B", sort_order=1)
        c = _mk_saved_search(db, query="C", sort_order=2)

        reordered = registry.invoke(
            db, "savedsearch.reorder", {"search_ids": [c.id, a.id, b.id]}, ctx
        )
        _, restore_res = _undo(db, reordered.audit_id, ctx)
        assert db.get(SavedSearch, a.id).sort_order == 0
        assert db.get(SavedSearch, b.id).sort_order == 1
        assert db.get(SavedSearch, c.id).sort_order == 2

        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "savedsearch.restore_order"
        assert db.get(SavedSearch, c.id).sort_order == 0
        assert db.get(SavedSearch, a.id).sort_order == 1
        assert db.get(SavedSearch, b.id).sort_order == 2

    def test_reorder_undo_restores_captured_order_after_later_reorder(self, db):
        ctx = _ctx()
        a = _mk_saved_search(db, query="A", sort_order=0)
        b = _mk_saved_search(db, query="B", sort_order=1)
        c = _mk_saved_search(db, query="C", sort_order=2)

        first = registry.invoke(
            db, "savedsearch.reorder", {"search_ids": [c.id, a.id, b.id]}, ctx
        )
        assert db.get(SavedSearch, c.id).sort_order == 0

        registry.invoke(
            db, "savedsearch.reorder", {"search_ids": [b.id, c.id, a.id]}, ctx
        )
        assert db.get(SavedSearch, b.id).sort_order == 0

        inv, _ = _undo(db, first.audit_id, ctx)
        assert inv == "savedsearch.restore_order"
        assert db.get(SavedSearch, a.id).sort_order == 0
        assert db.get(SavedSearch, b.id).sort_order == 1
        assert db.get(SavedSearch, c.id).sort_order == 2
