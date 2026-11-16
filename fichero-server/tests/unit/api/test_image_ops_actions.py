"""Every name a page's edit chain accepts is one audited action `image.<name>` (`image.ops.one-action-per-operation`, #6363).

The guardrail walks the chain vocabulary (`_OPERATION_MODELS`, `_PARAMETERLESS_OPERATIONS`), so a name added to the chain without an
action fails here. Each action, invoked on a page, writes exactly one chain row carrying the op, its settings and `who`, and one
audit row naming the action; undo removes that row and no other.
"""
from __future__ import annotations

import asyncio

import pytest
from PIL import Image

import fichero_server.api.routes.ingest.image_editing  # noqa: F401  (registers the image.* actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.ingest.image_editing import _OPERATION_MODELS, _PARAMETERLESS_OPERATIONS
from fichero_server.api.routes.system.actions_registry import undo_action
from fichero_server.models import ActionAudit, Document, FileType, ImageEditChain

CHAIN_NAMES = sorted(_OPERATION_MODELS.keys() | _PARAMETERLESS_OPERATIONS)
# Not a pixel row on one page: a split, a blank mark and a region cut write documents or flags, and have their own tests.
OWN_TESTS = {"segment", "mark_blank", "square"}
HAND_WRITTEN = {"crop", "rotate", "straighten", "enhance", "remove_background"}  # their rows do not carry `who` yet
NEEDS = {"crop": {"left": 5, "top": 5, "width": 50, "height": 40}, "rotate": {"angle": 90}}  # the hand-written actions with a required setting
PIXEL_NAMES = [name for name in CHAIN_NAMES if name not in OWN_TESTS]
CTX = ActionContext(actor="ui", library_path="/lib/test.fichero")


def _page(db) -> Document:
    path = db.path.parent / "files" / "p.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 90), "white").save(path, format="PNG")
    doc = Document(name="p.png", path=str(path), file_type=FileType.image)
    db.save(doc)
    return doc


def _rows(db, doc) -> list[dict]:
    chains = list(db.query(ImageEditChain, document_id=doc.id))
    return [dict(op) for op in chains[0].operations] if chains else []


def test_every_chain_name_has_an_action():
    missing = [name for name in CHAIN_NAMES if f"image.{name}" not in registry.names()]
    assert not missing, f"chain operations with no `image.<op>` action: {missing}"


@pytest.mark.parametrize("name", [n for n in CHAIN_NAMES if n in _OPERATION_MODELS])
def test_an_action_takes_the_operations_own_request_model(name):
    action_params = registry.get(f"image.{name}").params_model
    assert issubclass(action_params, _OPERATION_MODELS[name]), f"image.{name} does not take {_OPERATION_MODELS[name].__name__}"
    assert "document_id" in action_params.model_fields


@pytest.mark.parametrize("name", PIXEL_NAMES)
def test_invoking_it_writes_one_row_and_one_audit_entry_and_undo_removes_it(db, name):
    doc = _page(db)
    first = registry.invoke(db, "image.rotate", {"document_id": doc.id, "angle": 90}, CTX)  # a row already there that undo must leave
    assert first.result["operations"][-1]["op"] == "rotate"
    audits_before = len(db.query(ActionAudit))
    result = registry.invoke(db, f"image.{name}", {"document_id": doc.id, **NEEDS.get(name, {}), "who": "run r1"}, CTX)
    rows = result.result["operations"]
    assert [row["op"] for row in rows] == ["rotate", name], rows
    assert isinstance(rows[-1]["params"], dict)
    if name not in HAND_WRITTEN:
        assert rows[-1]["who"] == "run r1"
    audits = db.query(ActionAudit)
    assert len(audits) == audits_before + 1 and audits[-1].action_name == f"image.{name}"
    asyncio.run(undo_action(audits[-1].id, request=None, db=db, ctx=CTX, x_fichero_library_path=CTX.library_path, x_fichero_origin_window=None))
    assert [row["op"] for row in _rows(db, doc)] == ["rotate"]
