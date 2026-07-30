"""Unit tests for the workflow audited actions (EPIC #1848 / sweep #2014).

Domain: WORKFLOW. Covers, for every registered action:
  (a) the effect lands AND an ActionAudit row is written (actor / target_ids /
      before / after correct);
  (b) undo reverses it (for undoable actions) AND the redo / undo-of-undo chain
      is sane (the self-correcting ``workflow.restore`` inverse is exercised for
      both delete-undo and edit-undo);
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id -> 404,
      import without nodes/edges -> 400, reorder restores the EXACT prior order
      not a contiguous 0..n, unknown tool -> 404);
  (e) emit_change fires with the right type + ids (spy monkeypatched at the
      SOURCE ``fichero_server.api.change_stream.emit_change``).

These tests are MANAGER-run (workers don't run pytest). They mirror
``test_routes_classification_ontology_actions.py`` and reuse the shared ``db``
fixture (a real Database on a temp .fichero package). Importing the route module
below registers the actions via the ``@action`` decorator at import time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Importing the route module registers the workflow.* actions on the
# process-global registry via the @action decorator.
import fichero_server.api.routes.workflow.workflows  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, Workflow
from fichero_server.workflows.registry import list_tools


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture(autouse=True)
def _single_user_workflow_actions(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")


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
    ask the action for its inverse, invoke the inverse. Returns the inverse name."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None, f"{audit.action_name} not undoable"
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    res = registry.invoke(db, inv_name, inv_params, ctx)
    return inv_name, res


def _mk_workflow(db, name="WF", folder_path="/", sort_order=0) -> Workflow:
    wf = Workflow(name=name, format="nodes", folder_path=folder_path, sort_order=sort_order)
    db.save(wf)
    return wf


# ===========================================================================
# workflow.create / workflow.import / workflow.duplicate (create-family)
# ===========================================================================


class TestWorkflowCreateFamilyActions:
    # -- create --------------------------------------------------------------

    def test_create_effect_audit_emit(self, db, emit_spy):
        result = registry.invoke(
            db,
            "workflow.create",
            {"name": "My Pipeline", "description": "d", "provider": "openai"},
            _ctx(),
        )
        wid = result.result["id"]
        assert result.ok and result.changed_domains == ["workflow"]

        # effect: a persisted node-based workflow exists
        saved = db.get(Workflow, wid)
        assert saved is not None
        assert saved.name == "My Pipeline"
        assert saved.format == "nodes"

        # audit row written with the produced id in target_ids + after
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "workflow.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [wid]
        assert audit.before is None
        assert audit.after and audit.after["name"] == "My Pipeline"
        assert audit.undone is False

        # (e) emit fired with the right type
        assert len(emit_spy) == 1
        assert emit_spy[0][1]["type"] == "workflow.created"

    def test_create_undo_deletes(self, db):
        ctx = _ctx()
        result = registry.invoke(db, "workflow.create", {"name": "Temp"}, ctx)
        wid = result.result["id"]
        assert db.get(Workflow, wid) is not None

        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "workflow.delete"
        assert db.get(Workflow, wid) is None

    def test_create_validation_rejects_missing_name(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "workflow.create", {"description": "no name"}, _ctx())

    # -- import --------------------------------------------------------------

    def test_import_effect_audit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        result = registry.invoke(
            db,
            "workflow.import",
            {
                "name": "Imported",
                "workflow_data": {"nodes": [], "edges": [], "provider": "openai"},
            },
            ctx,
        )
        wid = result.result["id"]
        assert db.get(Workflow, wid) is not None
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "workflow.import"
        assert emit_spy[0][1]["type"] == "workflow.created"

        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "workflow.delete"
        assert db.get(Workflow, wid) is None

    def test_import_missing_nodes_edges_400(self, db):
        """A naive import would persist a structurally-invalid workflow."""
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "workflow.import", {"name": "Bad", "workflow_data": {"name": "x"}}, _ctx()
            )
        assert exc.value.status_code == 400

    # -- duplicate -----------------------------------------------------------

    def test_duplicate_effect_audit_and_undo(self, db):
        ctx = _ctx()
        original = _mk_workflow(db, name="Original")
        result = registry.invoke(db, "workflow.duplicate", {"workflow_id": original.id}, ctx)
        new_id = result.result["id"]

        # effect: a distinct copy with the "(Copy)" name
        copy = db.get(Workflow, new_id)
        assert copy is not None
        assert new_id != original.id
        assert copy.name == "Original (Copy)"
        # original untouched
        assert db.get(Workflow, original.id) is not None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "workflow.duplicate"
        assert audit.target_ids == [new_id]

        # undo removes the copy but NOT the original
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "workflow.delete"
        assert db.get(Workflow, new_id) is None
        assert db.get(Workflow, original.id) is not None

    def test_duplicate_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "workflow.duplicate", {"workflow_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404


# ===========================================================================
# workflow.update / workflow.patch (edit-family) — undo via restore
# ===========================================================================


class TestWorkflowEditActions:
    def test_update_effect_audit_and_undo(self, db):
        ctx = _ctx()
        wf = _mk_workflow(db, name="Before")
        result = registry.invoke(
            db,
            "workflow.update",
            {"workflow_id": wf.id, "workflow": {"name": "After", "description": "new"}},
            ctx,
        )
        reloaded = db.get(Workflow, wf.id)
        assert reloaded.name == "After"
        assert reloaded.description == "new"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "workflow.update"
        assert audit.before["name"] == "Before"
        assert audit.after["name"] == "After"

        # undo restores the prior snapshot (via workflow.restore, same id)
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "workflow.restore"
        back = db.get(Workflow, wf.id)
        assert back is not None and back.name == "Before"

    def test_update_undo_then_redo_reapplies_edit(self, db):
        """The self-correcting restore inverse: undo(update) restores the prior
        snapshot; undo-of-that-restore must RE-APPLY the edit (not delete)."""
        ctx = _ctx()
        wf = _mk_workflow(db, name="V1")
        upd = registry.invoke(
            db, "workflow.update", {"workflow_id": wf.id, "workflow": {"name": "V2"}}, ctx
        )
        # undo -> restore V1
        _, restore_res = _undo(db, upd.audit_id, ctx)
        assert db.get(Workflow, wf.id).name == "V1"

        # redo = undo the restore -> must restore V2 (re-apply the edit), NOT delete
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "workflow.restore"
        assert db.get(Workflow, wf.id) is not None
        assert db.get(Workflow, wf.id).name == "V2"

    def test_update_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "workflow.update", {"workflow_id": "ghost", "workflow": {"name": "X"}}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_update_validation_rejects_missing_name(self, db):
        wf = _mk_workflow(db, name="Keep")
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "workflow.update", {"workflow_id": wf.id, "workflow": {"description": "x"}}, _ctx()
            )

    def test_patch_rename_effect_audit_and_undo(self, db, emit_spy):
        ctx = _ctx()
        wf = _mk_workflow(db, name="Old Name", folder_path="/a")
        result = registry.invoke(
            db,
            "workflow.patch",
            {"workflow_id": wf.id, "name": "New Name", "folder_path": "/b"},
            ctx,
        )
        reloaded = db.get(Workflow, wf.id)
        assert reloaded.name == "New Name"
        assert reloaded.folder_path == "/b"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "workflow.patch"
        assert audit.before["name"] == "Old Name"
        assert emit_spy[-1][1]["type"] == "workflow.updated"

        # undo restores prior name + folder
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "workflow.restore"
        back = db.get(Workflow, wf.id)
        assert back.name == "Old Name"
        assert back.folder_path == "/a"

    def test_patch_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "workflow.patch", {"workflow_id": "ghost", "name": "X"}, _ctx())
        assert exc.value.status_code == 404


# ===========================================================================
# workflow.delete / workflow.restore — undo restores SAME id, redo chain sane
# ===========================================================================


class TestWorkflowDeleteRestoreActions:
    def test_delete_effect_audit_and_undo_restores_same_id(self, db, emit_spy):
        ctx = _ctx()
        wf = _mk_workflow(db, name="ToDelete")
        wid = wf.id
        result = registry.invoke(db, "workflow.delete", {"workflow_id": wid}, ctx)
        assert db.get(Workflow, wid) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "workflow.delete"
        assert audit.before and audit.before["id"] == wid
        assert audit.after is None
        assert emit_spy[-1][1]["type"] == "workflow.deleted"

        # undo -> workflow.restore re-materializes the SAME id + name
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "workflow.restore"
        back = db.get(Workflow, wid)
        assert back is not None and back.name == "ToDelete"

    def test_delete_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "workflow.delete", {"workflow_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_restore_redo_chain_deletes_again(self, db):
        """delete -> restore -> undo(restore) == delete again (redo is sane:
        the restore RE-CREATED a missing row, so its inverse is delete)."""
        ctx = _ctx()
        wf = _mk_workflow(db, name="Cycle")
        wid = wf.id
        del_res = registry.invoke(db, "workflow.delete", {"workflow_id": wid}, ctx)
        restore_name, restore_res = _undo(db, del_res.audit_id, ctx)
        assert restore_name == "workflow.restore"
        assert db.get(Workflow, wid) is not None

        # undo the restore -> deletes again
        inv, _ = _undo(db, restore_res.audit_id, ctx)
        assert inv == "workflow.delete"
        assert db.get(Workflow, wid) is None

    def test_restore_validation_rejects_bad_input(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "workflow.restore", {"snapshot": "not-a-dict"}, _ctx())


# ===========================================================================
# workflow.reorder / workflow.set_sort_orders
# ===========================================================================


class TestWorkflowReorderActions:
    def _three(self, db) -> list[Workflow]:
        # Non-contiguous prior sort_orders so undo must restore EXACT values,
        # not assume a 0..n permutation.
        a = _mk_workflow(db, name="A", sort_order=5)
        b = _mk_workflow(db, name="B", sort_order=9)
        c = _mk_workflow(db, name="C", sort_order=2)
        return [a, b, c]

    def test_reorder_effect_audit_and_undo_restores_prior_orders(self, db, emit_spy):
        ctx = _ctx()
        a, b, c = self._three(db)
        # reorder to [c, a, b] -> sort_order 0,1,2
        result = registry.invoke(
            db, "workflow.reorder", {"workflow_ids": [c.id, a.id, b.id]}, ctx
        )
        assert db.get(Workflow, c.id).sort_order == 0
        assert db.get(Workflow, a.id).sort_order == 1
        assert db.get(Workflow, b.id).sort_order == 2

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "workflow.reorder"
        # before captured the non-contiguous prior orders
        before_map = {o["id"]: o["sort_order"] for o in audit.before["orders"]}
        assert before_map == {c.id: 2, a.id: 5, b.id: 9}
        assert emit_spy[-1][1]["type"] == "workflow.updated"

        # undo restores EXACT prior (non-contiguous) sort orders
        inv, _ = _undo(db, result.audit_id, ctx)
        assert inv == "workflow.set_sort_orders"
        assert db.get(Workflow, a.id).sort_order == 5
        assert db.get(Workflow, b.id).sort_order == 9
        assert db.get(Workflow, c.id).sort_order == 2

    def test_reorder_unknown_id_404(self, db):
        a = _mk_workflow(db, name="Solo")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "workflow.reorder", {"workflow_ids": [a.id, "ghost"]}, _ctx())
        assert exc.value.status_code == 404

    def test_set_sort_orders_effect_and_redo_chain(self, db):
        ctx = _ctx()
        a = _mk_workflow(db, name="A", sort_order=3)
        result = registry.invoke(
            db, "workflow.set_sort_orders", {"orders": [{"id": a.id, "sort_order": 7}]}, ctx
        )
        assert db.get(Workflow, a.id).sort_order == 7

        # undo restores 3; undo-of-undo re-applies 7 (orders captured both ways)
        _, undo_res = _undo(db, result.audit_id, ctx)
        assert db.get(Workflow, a.id).sort_order == 3
        _undo(db, undo_res.audit_id, ctx)
        assert db.get(Workflow, a.id).sort_order == 7

    def test_set_sort_orders_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "workflow.set_sort_orders", {"orders": [{"id": "ghost", "sort_order": 1}]}, _ctx()
            )
        assert exc.value.status_code == 404


# ===========================================================================
# workflow.create_node — pure factory, NOT undoable
# ===========================================================================


class TestWorkflowCreateNodeAction:
    def _a_tool_name(self) -> str:
        tools = list_tools()
        assert tools, "expected at least one registered workflow tool"
        return tools[0].name

    def test_create_node_effect_audit_without_emit(self, db, emit_spy):
        tool_name = self._a_tool_name()
        result = registry.invoke(
            db,
            "workflow.create_node",
            {"tool_name": tool_name, "position_x": 12, "position_y": 34},
            _ctx(),
        )
        node = result.result
        assert node["tool"] == tool_name
        assert node["position_x"] == 12 and node["position_y"] == 34
        assert node["id"]

        # audited even though nothing is persisted to the workflow table
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "workflow.create_node"
        assert audit.target_ids == [node["id"]]

        # not undoable (no persisted state to reverse)
        assert registry.get("workflow.create_node").undoable is False

        assert emit_spy == []

    def test_create_node_unknown_tool_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "workflow.create_node", {"tool_name": "no_such_tool"}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_create_node_validation_rejects_missing_tool(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "workflow.create_node", {"position_x": 1}, _ctx())
