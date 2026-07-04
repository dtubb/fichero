"""Unit tests for the image-editing audited actions (EPIC #1848 / #2014).

Every mutating image-editing route now has a registered action that wraps the
proven ``*_impl`` and routes through ``registry.invoke`` (write -> ActionAudit ->
emit_change). These tests drive each action via the registry and assert, per the
action-layer test bar:

  (a) the effect lands on the edit chain + an ActionAudit row is written with the
      correct actor / target_ids / before / after;
  (b) undo reverses it (for the undoable ones) and redo is sane;
  (c) param validation rejects bad input (ValidationError);
  (d) edge/failure cases a naive impl would get wrong — unknown document id,
      clear-when-empty idempotency, undo of a replace restores the OLD list,
      segment side effects (child docs) that make it non-undoable;
  (e) emit_change fires with the right type + document ids (monkeypatched at the
      source ``fichero.api.change_stream.emit_change``).

Mirrors ``tests/unit/test_action_registry.py``. Uses the shared ``db``/``client``
conftest fixtures (a real Database on a temp ``.fichero`` package).
"""

from __future__ import annotations

import asyncio

import pytest
from PIL import Image
from pydantic import ValidationError

import fichero.api.routes.actions_registry  # noqa: F401
# Importing the route module registers the image.* actions via @action at import.
import fichero.api.routes.image_editing  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.api.routes.actions_registry import undo_action
from fichero.models import ActionAudit, DocType, Document, FileType, ImageEditChain


LIB = "/lib/test.fichero"


def _ctx(actor: str = "ui") -> ActionContext:
    return ActionContext(actor=actor, library_path=LIB)


def _make_image_doc(db, tmp_path, name="sample.jpg", size=(120, 90)) -> Document:
    image_path = db.path.parent / "files" / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, "white")
    img.putpixel((0, 0), (255, 0, 0))
    img.save(image_path, format="JPEG")
    doc = Document(name=name, path=str(image_path), file_type=FileType.image)
    db.save(doc)
    return doc


def _make_segmentable_doc(db, tmp_path, name="segments.png") -> Document:
    image_path = db.path.parent / "files" / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 60), "white")
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), (0, 0, 0))
    for x in range(65, 90):
        for y in range(20, 45):
            img.putpixel((x, y), (0, 0, 0))
    img.save(image_path, format="PNG")
    doc = Document(name=name, path=str(image_path), file_type=FileType.image)
    db.save(doc)
    return doc


def _ops(db, document_id) -> list[dict]:
    rows = list(db.query(ImageEditChain, document_id=document_id))
    return rows[0].operations if rows else []


def _spy_emit(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _undo(db, audit_id: str, library_path: str):
    return asyncio.run(
        undo_action(
            audit_id,
            db=db,
            ctx=ActionContext(actor="ui", library_path=library_path),
            x_fichero_library_path=library_path,
            x_fichero_origin_window=None,
        )
    )


# ===========================================================================
# image.set_operations — replace the whole chain
# ===========================================================================


class TestSetOperationsAction:
    def test_effect_and_audit(self, db, tmp_path, monkeypatch):
        calls = _spy_emit(monkeypatch)
        doc = _make_image_doc(db, tmp_path)
        new_ops = [{"op": "rotate", "params": {"angle": 90}}, {"op": "grayscale"}]

        result = registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": new_ops}, _ctx(),
        )

        # (a) effect lands on the persisted chain
        assert [o["op"] for o in _ops(db, doc.id)] == ["rotate", "grayscale"]
        assert result.ok is True
        assert result.changed_domains == ["image"]

        # (a) ActionAudit row with correct actor / target / before / after
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "image.set_operations"
        assert audit.actor == "ui"
        assert audit.target_ids == [doc.id]
        assert audit.before == {"document_id": doc.id, "operations": []}
        assert audit.after["document_id"] == doc.id
        assert [o["op"] for o in audit.after["operations"]] == ["rotate", "grayscale"]

        # (e) emit fired once with the image change type + the document id
        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["type"] == "image.edits_changed"
        assert kwargs["document_ids"] == [doc.id]
        assert kwargs["actor"] == "ui"

    def test_undo_restores_previous_list_not_just_empty(self, db, tmp_path):
        """Undo of a *replace* must restore the OLD list, not blindly clear it."""
        doc = _make_image_doc(db, tmp_path)
        first = [{"op": "grayscale"}]
        registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": first}, _ctx(),
        )
        # Replace with a different chain.
        second = [{"op": "rotate", "params": {"angle": 90}}]
        replace = registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": second}, _ctx(),
        )
        assert [o["op"] for o in _ops(db, doc.id)] == ["rotate"]

        # Undo via the action's invert -> set_operations(before == grayscale list).
        audit = db.get(ActionAudit, replace.audit_id)
        reg = registry.get(audit.action_name)
        assert reg.undoable and reg.invert is not None
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse is not None
        inv_name, inv_params = inverse
        assert inv_name == "image.set_operations"
        registry.invoke(db, inv_name, inv_params, _ctx())

        assert [o["op"] for o in _ops(db, doc.id)] == ["grayscale"]

    def test_redo_after_undo_is_sane(self, db, tmp_path):
        doc = _make_image_doc(db, tmp_path)
        ops = [{"op": "grayscale"}]
        first = registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": ops}, _ctx(),
        )
        # Undo to empty.
        registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": []}, _ctx(),
        )
        assert _ops(db, doc.id) == []
        # Redo = re-apply the original after-list.
        audit = db.get(ActionAudit, first.audit_id)
        registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": audit.after["operations"]}, _ctx(),
        )
        assert [o["op"] for o in _ops(db, doc.id)] == ["grayscale"]

    def test_validation_rejects_missing_document_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "image.set_operations", {"operations": []}, _ctx())

    def test_unknown_document_raises_404(self, db):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "image.set_operations",
                {"document_id": "no-such-doc", "operations": []}, _ctx(),
            )
        assert exc.value.status_code == 404


# ===========================================================================
# image.clear_operations — delete the whole chain
# ===========================================================================


class TestClearOperationsAction:
    def test_clear_records_cleared_ops_and_emits(self, db, tmp_path, monkeypatch):
        calls = _spy_emit(monkeypatch)
        doc = _make_image_doc(db, tmp_path)
        registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": [{"op": "grayscale"}]}, _ctx(),
        )
        calls.clear()

        result = registry.invoke(
            db, "image.clear_operations", {"document_id": doc.id}, _ctx()
        )
        assert _ops(db, doc.id) == []
        assert result.result == {"document_id": doc.id, "cleared": 1}

        audit = db.get(ActionAudit, result.audit_id)
        assert [o["op"] for o in audit.before["operations"]] == ["grayscale"]
        assert audit.after == {"document_id": doc.id, "operations": []}
        assert calls[0][1]["type"] == "image.edits_changed"

    def test_undo_clear_restores_chain(self, db, tmp_path):
        doc = _make_image_doc(db, tmp_path)
        registry.invoke(
            db, "image.set_operations",
            {"document_id": doc.id, "operations": [{"op": "grayscale"}]}, _ctx(),
        )
        clear = registry.invoke(
            db, "image.clear_operations", {"document_id": doc.id}, _ctx()
        )
        assert _ops(db, doc.id) == []

        audit = db.get(ActionAudit, clear.audit_id)
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inv_name, inv_params, _ctx())

        assert [o["op"] for o in _ops(db, doc.id)] == ["grayscale"]

    def test_clear_when_empty_is_idempotent_noop(self, db, tmp_path):
        """Clearing a document with no chain must not error and reports 0 cleared."""
        doc = _make_image_doc(db, tmp_path)
        result = registry.invoke(
            db, "image.clear_operations", {"document_id": doc.id}, _ctx()
        )
        assert result.result == {"document_id": doc.id, "cleared": 0}
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before == {"document_id": doc.id, "operations": []}
        # Undo of an empty clear is a harmless empty set_operations.
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, _ctx())
        assert inv_params["operations"] == []


# ===========================================================================
# Append ops — crop / rotate / enhance / remove_background
# ===========================================================================


class TestAppendOpActions:
    def test_crop_appends_renders_and_audits(self, db, tmp_path, monkeypatch):
        calls = _spy_emit(monkeypatch)
        doc = _make_image_doc(db, tmp_path, size=(120, 90))

        result = registry.invoke(
            db, "image.crop",
            {"document_id": doc.id, "left": 10, "top": 15, "width": 40,
             "height": 30, "page": 1}, _ctx(),
        )

        ops = _ops(db, doc.id)
        assert [o["op"] for o in ops] == ["crop"]
        # the render ran — a derived preview path was stamped
        assert "derived_path" in ops[0]
        assert ops[0]["params"]["width"] == 40

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "image.crop"
        assert audit.before["operations"] == []
        assert [o["op"] for o in audit.after["operations"]] == ["crop"]
        assert calls[0][1]["type"] == "image.edits_changed"

    def test_crop_undo_drops_the_appended_op(self, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(120, 90))
        result = registry.invoke(
            db, "image.crop",
            {"document_id": doc.id, "left": 10, "top": 15, "width": 40,
             "height": 30}, _ctx(),
        )
        assert len(_ops(db, doc.id)) == 1

        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get(audit.action_name)
        assert reg.undoable
        inv_name, inv_params = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inv_name, inv_params, _ctx())
        assert _ops(db, doc.id) == []

    def test_crop_onto_existing_chain_undo_restores_prior(self, db, tmp_path):
        """Append-then-undo must restore the chain that existed *before*, not wipe it."""
        doc = _make_image_doc(db, tmp_path, size=(120, 90))
        registry.invoke(
            db, "image.rotate",
            {"document_id": doc.id, "angle": 90, "page": 1}, _ctx(),
        )
        crop = registry.invoke(
            db, "image.crop",
            {"document_id": doc.id, "left": 5, "top": 5, "width": 20, "height": 20}, _ctx(),
        )
        assert [o["op"] for o in _ops(db, doc.id)] == ["rotate", "crop"]

        audit = db.get(ActionAudit, crop.audit_id)
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inv_name, inv_params, _ctx())
        # back to just the rotate, not empty
        assert [o["op"] for o in _ops(db, doc.id)] == ["rotate"]

    def test_rotate_appends_and_audits(self, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(80, 50))
        result = registry.invoke(
            db, "image.rotate",
            {"document_id": doc.id, "angle": 90, "expand": True, "page": 1}, _ctx(),
        )
        ops = _ops(db, doc.id)
        assert ops[0]["op"] == "rotate"
        assert ops[0]["params"] == {"angle": 90.0, "expand": True}
        assert db.get(ActionAudit, result.audit_id).action_name == "image.rotate"

    def test_straighten_route_writes_audit_and_undo_restores_chain(
        self, client, db, tmp_path, monkeypatch
    ):
        calls = _spy_emit(monkeypatch)
        doc = _make_image_doc(db, tmp_path, size=(80, 50))

        response = client.post(
            f"/api/images/{doc.id}/operations/straighten",
            json={"page": 1},
            headers={"X-Fichero-Library-Path": str(db.path.parent)},
        )

        assert response.status_code == 200, response.text
        ops = _ops(db, doc.id)
        assert len(ops) == 1
        assert ops[0]["op"] == "straighten"
        audit = db.all(ActionAudit)[-1]
        assert audit.action_name == "image.straighten"
        assert audit.before == {"document_id": doc.id, "operations": []}
        assert [o["op"] for o in audit.after["operations"]] == ["straighten"]
        assert calls[-1][1]["type"] == "image.edits_changed"

        inverse = _undo(db, audit.id, str(db.path.parent))

        assert _ops(db, doc.id) == []
        inverse_audit = db.get(ActionAudit, inverse.audit_id)
        assert inverse_audit is not None
        assert inverse_audit.action_name == "image.set_operations"
        assert inverse_audit.inverse_of == audit.id

    def test_enhance_appends_and_audits(self, db, tmp_path):
        doc = _make_image_doc(db, tmp_path)
        result = registry.invoke(
            db, "image.enhance",
            {"document_id": doc.id, "brightness": 0.5, "contrast": 1.25,
             "sharpen": 1.5, "auto_levels": True, "page": 1}, _ctx(),
        )
        ops = _ops(db, doc.id)
        assert ops[0]["op"] == "enhance"
        assert ops[0]["params"]["brightness"] == 0.5
        assert db.get(ActionAudit, result.audit_id) is not None

    def test_remove_background_appends_png_preview(self, db, tmp_path):
        # foreground-on-white so the threshold method produces an alpha mask
        image_path = db.path.parent / "files" / "fg.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (60, 40), "white")
        for x in range(20, 40):
            for y in range(10, 30):
                img.putpixel((x, y), (10, 20, 30))
        img.save(image_path, format="PNG")
        doc = Document(name="fg.png", path=str(image_path), file_type=FileType.image)
        db.save(doc)

        result = registry.invoke(
            db, "image.remove_background",
            {"document_id": doc.id, "method": "threshold", "threshold": 5, "page": 1},
            _ctx(),
        )
        ops = _ops(db, doc.id)
        assert ops[0]["op"] == "remove_background"
        assert ops[0]["derived_path"].endswith(".png")
        assert db.get(ActionAudit, result.audit_id) is not None

    def test_enhance_validation_rejects_negative_brightness(self, db, tmp_path):
        doc = _make_image_doc(db, tmp_path)
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "image.enhance",
                {"document_id": doc.id, "brightness": -1.0}, _ctx(),
            )

    def test_remove_background_validation_rejects_bad_method(self, db, tmp_path):
        doc = _make_image_doc(db, tmp_path)
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "image.remove_background",
                {"document_id": doc.id, "method": "magic"}, _ctx(),
            )

    def test_crop_unknown_document_raises_404(self, db):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "image.crop",
                {"document_id": "nope", "left": 0, "top": 0, "width": 5, "height": 5},
                _ctx(),
            )
        assert exc.value.status_code == 404


# ===========================================================================
# image.segment — non-undoable (creates child documents)
# ===========================================================================


class TestSegmentAction:
    def test_segment_creates_children_and_is_not_undoable(self, db, tmp_path, monkeypatch):
        calls = _spy_emit(monkeypatch)
        doc = _make_segmentable_doc(db, tmp_path)

        result = registry.invoke(
            db, "image.segment",
            {"document_id": doc.id, "method": "foreground", "threshold": 5,
             "min_area": 50, "max_segments": 10, "page": 1}, _ctx(),
        )

        # the segment op is appended with its child ids
        ops = _ops(db, doc.id)
        assert ops[-1]["op"] == "segment"
        assert len(ops[-1]["child_document_ids"]) == 2

        # child chunk documents actually exist in the DB
        children = db.query(Document, parent_id=doc.id, doc_type=DocType.chunk)
        assert len(children) == 2

        # domains + emit carry the document layer + every child id
        assert set(result.changed_domains) == {"image", "document"}
        _args, kwargs = calls[0]
        assert kwargs["type"] == "image.segmented"
        assert doc.id in kwargs["document_ids"]
        for child in children:
            assert child.id in kwargs["document_ids"]

        # explicitly NOT undoable — restoring the chain would orphan the children
        reg = registry.get("image.segment")
        assert reg.undoable is False
        assert reg.invert is None

        # audit still written with the chain delta
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "image.segment"
        assert audit.before["operations"] == []
        assert audit.after["operations"][-1]["op"] == "segment"


# ===========================================================================
# Registry surface — the actions are discoverable + advertise undoability
# ===========================================================================


class TestImageActionsRegistered:
    def test_all_image_actions_registered(self):
        names = set(registry.names())
        expected = {
            "image.set_operations", "image.clear_operations", "image.crop",
            "image.rotate", "image.straighten", "image.enhance", "image.remove_background",
            "image.segment",
        }
        assert expected <= names

    def test_undoable_flags(self):
        undoable = {
            "image.set_operations", "image.clear_operations", "image.crop",
            "image.rotate", "image.straighten", "image.enhance", "image.remove_background",
        }
        for name in undoable:
            assert registry.get(name).undoable is True
        assert registry.get("image.segment").undoable is False
