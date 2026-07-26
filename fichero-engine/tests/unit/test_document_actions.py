"""Unit tests for the DOCUMENT-domain audited actions (EPIC #1848 / #2014).

The document sweep registers every mutating document endpoint as an action that
WRAPS the route's proven ``*_impl`` (iterate-not-replace) and runs through
``registry.invoke`` — the single audited write path. These tests drive each
action via the registry (the same path chat tools / App Intents / the
``/api/actions/invoke`` route use) and, per the project test bar
([[would-more-tests-catch-more-issues]]), assert MORE than the happy path:

  (a) the effect lands AND an ActionAudit row is written (actor/target_ids/
      before/after correct);
  (b) undo reverses it (for undoable actions) and undo-of-undo is sane;
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id, non-folder
      workspace, dedup, non-contiguous reorder restore, parent-id guard, empty
      list no-op);
  (e) the emit fires with the right type + ids (emit_change monkeypatched at
      the SOURCE module, mirroring test_action_registry).

The MANAGER runs the full suite; this worker only writes the tests.

Importing the documents route module registers the document.* actions at
import time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

# Importing the route module registers the document.* actions at import time.
import fichero.api.routes.documents  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.models import ActionAudit, Artifact, DocType, Document, Status


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def spy_emit(monkeypatch):
    """Capture emit_change calls from both document emit paths.

    The audited create/move/delete actions emit through the documents route
    module so the route-patched change-stream tests and the action tests observe
    the same call. Other document actions still use the registry's generic
    change-stream emit path. Both append into the same sink here.
    """
    calls: list[tuple] = []
    def spy(*a, **k):
        calls.append((a, k))
    monkeypatch.setattr("fichero.api.routes.documents.emit_change", spy)
    monkeypatch.setattr("fichero.api.change_stream.emit_change", spy)
    return calls


def _save_doc(db, name="Doc", **kwargs) -> Document:
    doc = Document(name=name, **kwargs)
    db.save(doc)
    return doc


def _invoke_inverse(db, audit_id, ctx):
    """Drive undo the way the generic undo endpoint does: read the audit, ask
    the action for its inverse, invoke the inverse. Returns the inverse name."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    registry.invoke(db, inv_name, inv_params, ctx)
    return inv_name


# ===========================================================================
# document.create
# ===========================================================================


class TestDocumentCreateAction:
    def test_create_effect_audit_and_emit(self, db, spy_emit):
        result = registry.invoke(
            db, "document.create", {"name": "Letter 1"}, _ctx()
        )

        # (a) effect: the document is persisted
        new_id = result.result["id"]
        persisted = db.get(Document, new_id)
        assert persisted is not None
        assert persisted.name == "Letter 1"

        # (a) audit row written with the right shape
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "document.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.after == {"document_id": new_id}

        # (e) emit fired with document.created + the new id
        assert len(spy_emit) == 1
        _args, kwargs = spy_emit[0]
        assert kwargs["type"] == "document.created"
        assert kwargs["document_ids"] == [new_id]

    def test_create_collection_doc_type_persists(self, db):
        # (d) "create_collection" is create_document for a top-level container —
        # a collection is a root folder. The action honours the requested
        # doc_type rather than forcing the default `file`.
        result = registry.invoke(
            db,
            "document.create",
            {"name": "Archive", "doc_type": "folder"},
            _ctx(),
        )
        persisted = db.get(Document, result.result["id"])
        assert persisted.doc_type == DocType.folder
        assert persisted.parent_id is None  # a collection sits at the root

    def test_create_undo_deletes_then_undo_of_undo_restores(self, db):
        """(b) create -> undo (soft-delete) hides it; undo-of-undo restores it."""
        ctx = _ctx()
        result = registry.invoke(db, "document.create", {"name": "ephemeral"}, ctx)
        new_id = result.result["id"]
        assert db.get(Document, new_id) is not None

        # undo create -> document.delete
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.delete"
        assert db.get(Document, new_id) is not None
        assert db.get(Document, new_id).deleted_at is not None

        # undo-of-undo: the delete audit inverts to document.restore -> doc back
        del_audit = next(
            a for a in db.all(ActionAudit)
            if a.action_name == "document.delete" and new_id in a.target_ids
        )
        reg = registry.get("document.delete")
        inverse = reg.invert(del_audit.before, del_audit.after, ctx)
        registry.invoke(db, inverse[0], inverse[1], ctx)
        assert db.get(Document, new_id) is not None

    def test_create_validation_rejects_missing_name(self, db):
        # (c) name is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "document.create", {"doc_type": "file"}, _ctx())

    def test_create_unknown_parent_400(self, db):
        # (d) a naive impl would create a child pointing at a ghost parent
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "document.create", {"name": "x", "parent_id": "ghost"}, _ctx()
            )
        assert exc.value.status_code == 400

    def test_create_rejects_path_outside_library(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "document.create",
                {"name": "passwd", "path": "/etc/passwd"},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_create_allows_absolute_path_under_library(self, db):
        source = Path(db.path).parent / "files" / "safe.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("safe")

        result = registry.invoke(
            db,
            "document.create",
            {"name": "safe", "path": str(source)},
            _ctx(),
        )

        persisted = db.get(Document, result.result["id"])
        assert persisted.path == str(source)


# ===========================================================================
# document.update
# ===========================================================================


class TestDocumentUpdateAction:
    def test_update_effect_audit_and_undo(self, db, spy_emit):
        doc = _save_doc(db, name="old name", is_starred=False)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "document.update",
            {"doc_id": doc.id, "update": {"name": "new name", "is_starred": True}},
            ctx,
        )
        reloaded = db.get(Document, doc.id)
        assert reloaded.name == "new name"
        assert reloaded.is_starred is True

        # (a) audit captured the before-snapshot (the undo payload)
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "document.update"
        assert audit.before["name"] == "old name"
        assert audit.before["is_starred"] is False
        assert spy_emit[-1][1]["type"] == "document.updated"

        # (b) undo (restore) reverts BOTH changed fields
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.restore"
        restored = db.get(Document, doc.id)
        assert restored.name == "old name"
        assert restored.is_starred is False

    def test_update_does_not_reparent(self, db):
        """(d) parent_id must NEVER be mutated by update — reparenting goes
        through move. A naive setattr-everything impl would silently move it."""
        parent = _save_doc(db, name="parent", doc_type=DocType.folder)
        doc = _save_doc(db, name="child", parent_id=parent.id)
        registry.invoke(
            db,
            "document.update",
            {"doc_id": doc.id, "update": {"name": "renamed", "parent_id": "ghost"}},
            _ctx(),
        )
        reloaded = db.get(Document, doc.id)
        assert reloaded.name == "renamed"
        assert reloaded.parent_id == parent.id  # untouched

    def test_update_unknown_doc_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "document.update", {"doc_id": "ghost", "update": {"name": "x"}}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_update_validation_rejects_bad_doc_type(self, db):
        doc = _save_doc(db, name="d")
        # (c) doc_type must be a valid DocType
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "document.update",
                {"doc_id": doc.id, "update": {"doc_type": "banana"}},
                _ctx(),
            )

    def test_update_rejects_path_outside_library(self, db):
        doc = _save_doc(db, name="d")

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "document.update",
                {"doc_id": doc.id, "update": {"path": "/etc/passwd"}},
                _ctx(),
            )
        assert exc.value.status_code == 400


# ===========================================================================
# document.move
# ===========================================================================


class TestDocumentMoveAction:
    def test_move_effect_audit_and_undo(self, db, spy_emit):
        old_parent = _save_doc(db, name="old", doc_type=DocType.folder)
        new_parent = _save_doc(db, name="new", doc_type=DocType.folder)
        doc = _save_doc(db, name="child", parent_id=old_parent.id)
        ctx = _ctx()

        result = registry.invoke(
            db, "document.move", {"doc_id": doc.id, "parent_id": new_parent.id}, ctx
        )
        assert db.get(Document, doc.id).parent_id == new_parent.id

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "document.move"
        assert audit.before["parent_id"] == old_parent.id
        assert spy_emit[-1][1]["type"] == "document.updated"

        # (b) undo -> restore reverts parent_id to the original
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.restore"
        assert db.get(Document, doc.id).parent_id == old_parent.id

    def test_move_to_root_clears_parent(self, db):
        # (d) parent_id None moves the doc to the root — not a no-op
        parent = _save_doc(db, name="p", doc_type=DocType.folder)
        doc = _save_doc(db, name="c", parent_id=parent.id)
        registry.invoke(db, "document.move", {"doc_id": doc.id, "parent_id": None}, _ctx())
        assert db.get(Document, doc.id).parent_id is None

    def test_move_unknown_doc_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "document.move", {"doc_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_move_unknown_parent_400(self, db):
        doc = _save_doc(db, name="d")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "document.move", {"doc_id": doc.id, "parent_id": "ghost"}, _ctx()
            )
        assert exc.value.status_code == 400

    def test_move_validation_requires_doc_id(self, db):
        # (c) doc_id is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "document.move", {"parent_id": None}, _ctx())

    def test_move_into_self_rejected(self, db):
        # A self-parent detaches the doc from the root; orphan cleanup would
        # then delete it. Mirrors the client-side SidebarMovePolicy guard.
        folder = _save_doc(db, name="f", doc_type=DocType.folder)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "document.move", {"doc_id": folder.id, "parent_id": folder.id}, _ctx()
            )
        assert exc.value.status_code == 400
        assert db.get(Document, folder.id).parent_id is None  # unchanged

    def test_move_into_descendant_rejected(self, db):
        top = _save_doc(db, name="top", doc_type=DocType.folder)
        mid = _save_doc(db, name="mid", doc_type=DocType.folder, parent_id=top.id)
        leaf = _save_doc(db, name="leaf", doc_type=DocType.folder, parent_id=mid.id)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "document.move", {"doc_id": top.id, "parent_id": leaf.id}, _ctx()
            )
        assert exc.value.status_code == 400
        assert db.get(Document, top.id).parent_id is None  # unchanged

    def test_locked_nodes_reject_document_writes(self, db):
        # Default Workflows container / preset mirrors carry
        # attributes.read_only=True; the document write surface must refuse
        # them just like the workflow routes do (403, #11 Phase 1).
        locked = _save_doc(
            db,
            name="Default Workflows",
            doc_type=DocType.folder,
            attributes={"read_only": True, "scope": "global", "system": True},
        )
        normal = _save_doc(db, name="normal")

        for action, params in [
            ("document.move", {"doc_id": locked.id, "parent_id": None}),
            ("document.update", {"doc_id": locked.id, "update": {"name": "renamed"}}),
            ("document.delete", {"doc_id": locked.id}),
            # Locked containers accept no new children via the API either.
            ("document.move", {"doc_id": normal.id, "parent_id": locked.id}),
        ]:
            with pytest.raises(HTTPException) as exc:
                registry.invoke(db, action, params, _ctx())
            assert exc.value.status_code == 403, action

        assert db.get(Document, locked.id).name == "Default Workflows"
        assert db.get(Document, normal.id).parent_id is None

    def test_move_to_current_parent_still_allowed(self, db):
        # Ancestors are legal targets — only self/descendants form cycles.
        parent = _save_doc(db, name="p", doc_type=DocType.folder)
        doc = _save_doc(db, name="c", parent_id=parent.id)
        registry.invoke(
            db, "document.move", {"doc_id": doc.id, "parent_id": parent.id}, _ctx()
        )
        assert db.get(Document, doc.id).parent_id == parent.id


# ===========================================================================
# document.duplicate
# ===========================================================================


class TestDocumentDuplicateAction:
    def test_duplicate_leaf_lands_beside_original(self, db):
        parent = _save_doc(db, name="p", doc_type=DocType.folder)
        doc = _save_doc(db, name="Paper", parent_id=parent.id, page_content="hello")

        result = registry.invoke(
            db, "document.duplicate", {"doc_id": doc.id}, _ctx()
        )
        copy = Document.model_validate(result.result)

        assert copy.id != doc.id
        assert copy.name == "Paper copy"
        assert copy.parent_id == parent.id
        assert db.get(Document, copy.id).page_content == "hello"
        # Original untouched.
        assert db.get(Document, doc.id).name == "Paper"

    def test_duplicate_folder_deep_copies_subtree(self, db):
        folder = _save_doc(db, name="F", doc_type=DocType.folder)
        child = _save_doc(db, name="c1", parent_id=folder.id)
        grand = _save_doc(
            db, name="g1", doc_type=DocType.folder, parent_id=child.id
        )

        result = registry.invoke(
            db, "document.duplicate", {"doc_id": folder.id}, _ctx()
        )
        copy = Document.model_validate(result.result)

        assert copy.name == "F copy"
        copy_children = [d for d in db.query(Document, parent_id=copy.id)]
        assert [c.name for c in copy_children] == ["c1"]
        copy_grand = [d for d in db.query(Document, parent_id=copy_children[0].id)]
        assert [g.name for g in copy_grand] == ["g1"]
        # Fresh ids everywhere — the copy shares no rows with the original.
        original_ids = {folder.id, child.id, grand.id}
        assert {copy.id, copy_children[0].id, copy_grand[0].id}.isdisjoint(original_ids)

    def test_duplicate_into_target_folder_keeps_name(self, db):
        # Option-drag copy: cross-folder copies keep their name — Finder only
        # suffixes copies landing beside the original.
        source_parent = _save_doc(db, name="src", doc_type=DocType.folder)
        target = _save_doc(db, name="dst", doc_type=DocType.folder)
        doc = _save_doc(db, name="Paper", parent_id=source_parent.id)

        result = registry.invoke(
            db,
            "document.duplicate",
            {"doc_id": doc.id, "parent_id": target.id},
            _ctx(),
        )
        copy = Document.model_validate(result.result)
        assert copy.parent_id == target.id
        assert copy.name == "Paper"

    def test_duplicate_to_root_is_explicit(self, db):
        # to_root disambiguates "copy to root" from the beside-the-original
        # default; a doc copied OUT of a folder to root keeps its name.
        folder = _save_doc(db, name="F", doc_type=DocType.folder)
        doc = _save_doc(db, name="Paper", parent_id=folder.id)
        result = registry.invoke(
            db,
            "document.duplicate",
            {"doc_id": doc.id, "to_root": True},
            _ctx(),
        )
        copy = Document.model_validate(result.result)
        assert copy.parent_id is None
        assert copy.name == "Paper"
        # A root doc copied to root lands beside itself → suffixed.
        root_doc = _save_doc(db, name="Loose")
        result2 = registry.invoke(
            db,
            "document.duplicate",
            {"doc_id": root_doc.id, "to_root": True},
            _ctx(),
        )
        assert Document.model_validate(result2.result).name == "Loose copy"

    def test_duplicate_into_own_subtree_rejected(self, db):
        # Copying a folder into its own descendant would make the recursion
        # copy its own output.
        folder = _save_doc(db, name="F", doc_type=DocType.folder)
        child = _save_doc(db, name="c", doc_type=DocType.folder, parent_id=folder.id)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "document.duplicate",
                {"doc_id": folder.id, "parent_id": child.id},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_duplicate_into_locked_target_rejected(self, db):
        locked = _save_doc(
            db, name="Default Workflows", doc_type=DocType.folder,
            attributes={"read_only": True},
        )
        doc = _save_doc(db, name="Paper")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "document.duplicate",
                {"doc_id": doc.id, "parent_id": locked.id},
                _ctx(),
            )
        assert exc.value.status_code == 403

    def test_duplicate_survives_trees_deeper_than_the_recursion_limit(self, db):
        # The copy walk is iterative — a chain deeper than Python's default
        # recursion limit (~1000) must copy completely, not strand partial
        # rows on a RecursionError (review suggestion).
        import sys
        depth = sys.getrecursionlimit() + 50
        parent_id = None
        top_id = None
        for i in range(depth):
            doc = _save_doc(db, name=f"d{i}", doc_type=DocType.folder, parent_id=parent_id)
            if top_id is None:
                top_id = doc.id
            parent_id = doc.id

        result = registry.invoke(db, "document.duplicate", {"doc_id": top_id}, _ctx())
        copy = Document.model_validate(result.result)
        # Walk the copy chain to the bottom — every level must exist.
        current = copy.id
        copied = 0
        while current is not None:
            copied += 1
            children = db.query(Document, parent_id=current)
            current = children[0].id if children else None
        assert copied == depth

    def test_duplicate_locked_node_rejected(self, db):
        locked = _save_doc(
            db, name="Default Workflows", doc_type=DocType.folder,
            attributes={"read_only": True},
        )
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "document.duplicate", {"doc_id": locked.id}, _ctx())
        assert exc.value.status_code == 403

    def test_duplicate_undo_deletes_the_copy_subtree(self, db):
        folder = _save_doc(db, name="F", doc_type=DocType.folder)
        _save_doc(db, name="c1", parent_id=folder.id)
        ctx = _ctx()

        result = registry.invoke(db, "document.duplicate", {"doc_id": folder.id}, ctx)
        copy = Document.model_validate(result.result)

        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.delete"
        assert db.get(Document, copy.id).deleted_at is not None
        # Original survives the undo.
        assert db.get(Document, folder.id).deleted_at is None


# ===========================================================================
# document.reorder
# ===========================================================================


class TestDocumentReorderAction:
    def test_reorder_effect_audit_and_emit(self, db, spy_emit):
        a = _save_doc(db, name="a", sort_order=0)
        b = _save_doc(db, name="b", sort_order=1)
        c = _save_doc(db, name="c", sort_order=2)

        result = registry.invoke(
            db, "document.reorder", {"doc_ids": [c.id, a.id, b.id]}, _ctx()
        )
        assert result.result["count"] == 3
        assert db.get(Document, c.id).sort_order == 0
        assert db.get(Document, a.id).sort_order == 1
        assert db.get(Document, b.id).sort_order == 2

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "document.reorder"
        assert set(audit.target_ids) == {a.id, b.id, c.id}
        assert spy_emit[-1][1]["type"] == "document.updated"

    def test_reorder_undo_restores_noncontiguous_sort_order(self, db):
        """(b/d) undo must restore the EXACT prior sort_order, not re-base to
        0..n-1. A naive 'reorder with the old list' inverse would corrupt
        previously non-contiguous values."""
        a = _save_doc(db, name="a", sort_order=5)
        b = _save_doc(db, name="b", sort_order=9)
        ctx = _ctx()

        result = registry.invoke(db, "document.reorder", {"doc_ids": [b.id, a.id]}, ctx)
        assert db.get(Document, b.id).sort_order == 0
        assert db.get(Document, a.id).sort_order == 1

        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.restore"
        assert db.get(Document, a.id).sort_order == 5
        assert db.get(Document, b.id).sort_order == 9

    def test_reorder_unknown_id_404(self, db):
        a = _save_doc(db, name="a")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "document.reorder", {"doc_ids": [a.id, "ghost"]}, _ctx())
        assert exc.value.status_code == 404

    def test_reorder_empty_list_skips_emit(self, db, spy_emit):
        # (d) empty list -> emit_type None, so emit_change is NOT called
        registry.invoke(db, "document.reorder", {"doc_ids": []}, _ctx())
        assert spy_emit == []

    def test_reorder_validation_requires_doc_ids(self, db):
        # (c) doc_ids is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "document.reorder", {"folder_path": "/"}, _ctx())


# ===========================================================================
# document.patch_workspace
# ===========================================================================


class TestPatchWorkspaceAction:
    def _workspace(self, db) -> Document:
        return _save_doc(db, name="WS", doc_type=DocType.folder)

    def _item(self, item_id="i1", target_id="t1") -> dict:
        return {"id": item_id, "target_type": "document", "target_id": target_id}

    def test_patch_add_effect_audit_and_undo(self, db, spy_emit):
        ws = self._workspace(db)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "document.patch_workspace",
            {"doc_id": ws.id, "patch": {"add": [self._item()]}},
            ctx,
        )
        assert result.result["count"] == 1
        reloaded = db.get(Document, ws.id)
        assert reloaded.is_workspace is True
        assert reloaded.curated_items[0]["id"] == "i1"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "document.patch_workspace"
        assert audit.before["curated_items"] == []
        assert spy_emit[-1][1]["type"] == "document.updated"

        # (b) undo -> restore brings curated_items back to empty
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.restore"
        assert db.get(Document, ws.id).curated_items == []

    def test_patch_remove_restores_on_undo(self, db):
        # (b/d) removing an item then undoing must bring that exact item back
        ws = self._workspace(db)
        ws.curated_items = [self._item("i1", "t1"), self._item("i2", "t2")]
        db.save(ws)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "document.patch_workspace",
            {"doc_id": ws.id, "patch": {"remove_ids": ["i1"]}},
            ctx,
        )
        remaining = {i["id"] for i in db.get(Document, ws.id).curated_items}
        assert remaining == {"i2"}

        _invoke_inverse(db, result.audit_id, ctx)
        restored = {i["id"] for i in db.get(Document, ws.id).curated_items}
        assert restored == {"i1", "i2"}

    def test_patch_non_folder_400(self, db):
        # (d) a workspace must be a folder; patching a file is a 400, not a
        # silent promotion of a leaf to a workspace
        leaf = _save_doc(db, name="file", doc_type=DocType.file)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "document.patch_workspace",
                {"doc_id": leaf.id, "patch": {"add": []}},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_patch_unknown_doc_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "document.patch_workspace",
                {"doc_id": "ghost", "patch": {"add": []}},
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_patch_validation_requires_doc_id(self, db):
        # (c) doc_id is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "document.patch_workspace", {"patch": {}}, _ctx())


# ===========================================================================
# document.batch_exclude
# ===========================================================================


class TestBatchExcludeAction:
    def test_batch_exclude_effect_audit_and_undo(self, db, spy_emit):
        a = _save_doc(db, name="a", exclude_from_processing=False)
        b = _save_doc(db, name="b", exclude_from_processing=False)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "document.batch_exclude",
            {"document_ids": [a.id, b.id], "excluded": True},
            ctx,
        )
        assert result.result["updated"] == 2
        assert db.get(Document, a.id).exclude_from_processing is True
        assert db.get(Document, b.id).exclude_from_processing is True

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "document.batch_exclude"
        assert set(audit.target_ids) == {a.id, b.id}
        assert spy_emit[-1][1]["type"] == "document.updated"

        # (b) undo -> restore reverts both exclude flags
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.restore"
        assert db.get(Document, a.id).exclude_from_processing is False
        assert db.get(Document, b.id).exclude_from_processing is False

    def test_batch_exclude_dedupes_repeated_ids(self, db):
        # (d) a doc id passed twice must be updated once, not double-counted
        a = _save_doc(db, name="a")
        result = registry.invoke(
            db,
            "document.batch_exclude",
            {"document_ids": [a.id, a.id], "excluded": True},
            _ctx(),
        )
        assert result.result["updated"] == 1
        assert result.result["document_ids"] == [a.id]

    def test_batch_exclude_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "document.batch_exclude",
                {"document_ids": ["ghost"], "excluded": True},
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_batch_exclude_validation_requires_excluded(self, db):
        # (c) excluded is a required bool
        a = _save_doc(db, name="a")
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "document.batch_exclude", {"document_ids": [a.id]}, _ctx()
            )


# ===========================================================================
# document.delete
# ===========================================================================


class TestDocumentDeleteAction:
    def test_delete_subtree_effect_audit_and_emit(self, db, spy_emit):
        parent = _save_doc(db, name="parent", doc_type=DocType.folder)
        child = _save_doc(db, name="child", parent_id=parent.id)

        result = registry.invoke(db, "document.delete", {"doc_id": parent.id}, _ctx())

        # (a) effect: the whole subtree is soft-deleted, not removed
        assert db.get(Document, parent.id) is not None
        assert db.get(Document, parent.id).deleted_at is not None
        assert db.get(Document, parent.id).deleted_by == "ui"
        assert db.get(Document, child.id) is not None
        assert db.get(Document, child.id).deleted_at is not None
        assert set(result.result["deleted_document_ids"]) == {parent.id, child.id}

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "document.delete"
        snap_ids = {d["id"] for d in audit.before["documents"]}
        assert snap_ids == {parent.id, child.id}

        # (e) emit document.deleted with the subtree ids
        _args, kwargs = spy_emit[-1]
        assert kwargs["type"] == "document.deleted"
        assert set(kwargs["document_ids"]) == {parent.id, child.id}

    def test_delete_undo_clears_deleted_flags(self, db):
        doc = _save_doc(db, name="d", status=Status.completed)
        art = Artifact(document_id=doc.id, artifact_type="transcript", content="hi")
        db.save(art)
        ctx = _ctx()

        result = registry.invoke(db, "document.delete", {"doc_id": doc.id}, ctx)
        assert db.get(Document, doc.id).deleted_at is not None
        assert db.get(Artifact, art.id) is not None

        # (b) undo -> document.restore clears the tombstone
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.restore"
        restored = db.get(Document, doc.id)
        assert restored is not None
        assert restored.status == Status.completed
        assert restored.deleted_at is None
        assert restored.deleted_by is None
        assert db.get(Artifact, art.id) is not None

    def test_delete_unknown_doc_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "document.delete", {"doc_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_validation_requires_doc_id(self, db):
        # (c) doc_id is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "document.delete", {}, _ctx())


# ===========================================================================
# document.restore (the generic inverse) — direct coverage
# ===========================================================================


class TestDocumentRestoreAction:
    def test_restore_clears_deleted_flags_by_id(self, db, spy_emit):
        doc = _save_doc(db, name="ghost-doc", deleted_by="ui")
        doc.deleted_at = doc.updated_at
        db.save(doc)
        result = registry.invoke(db, "document.restore", {"doc_id": doc.id}, _ctx())
        restored_id = result.result["restored_document_ids"][0]
        assert db.get(Document, restored_id) is not None
        assert db.get(Document, restored_id).deleted_at is None
        assert db.get(Document, restored_id).deleted_by is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "document.restore"
        assert spy_emit[-1][1]["type"] == "document.updated"

    def test_restore_is_not_undoable(self, db):
        # restore is the terminal inverse — it has no inverse of its own
        assert registry.get("document.restore").undoable is False

    def test_restore_empty_is_noop(self, db):
        # (d) restoring nothing writes no rows and reports an empty list
        result = registry.invoke(db, "document.restore", {"documents": []}, _ctx())
        assert result.result["restored_document_ids"] == []


class TestDocumentPurgeAndTrashActions:
    def test_purge_hard_deletes_document(self, db, spy_emit):
        doc = _save_doc(db, name="purge-me")
        registry.invoke(db, "document.delete", {"doc_id": doc.id}, _ctx())

        result = registry.invoke(db, "document.purge", {"doc_id": doc.id}, _ctx())

        assert db.get(Document, doc.id) is None
        assert result.result["deleted_document_ids"] == [doc.id]
        assert spy_emit[-1][1]["type"] == "document.deleted"

    def test_list_trash_returns_deleted_only(self, db):
        active = _save_doc(db, name="active")
        deleted = _save_doc(db, name="deleted")
        registry.invoke(db, "document.delete", {"doc_id": deleted.id}, _ctx())

        result = registry.invoke(db, "document.list_trash", {}, _ctx())

        item_ids = [item["id"] for item in result.result["items"]]
        assert deleted.id in item_ids
        assert active.id not in item_ids
