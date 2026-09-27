"""ACCESS CONTROL: a write names its document one level down, and is still checked (#5135).

`ActionRegistry.invoke` checks every target id before an action runs. It used to read ids at the
TOP LEVEL of the params only, so a document named inside a nested object -- an anchor, an
`update` object, an anchor's `refines` chain -- was never resolved, and a person denied that
document could write into it. One test per SHAPE of nesting, each proving the denied write is
refused AND wrote nothing, with a positive control that an allowed nested id still passes.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ContentRepresentation, Document
from fichero_server.models.knowledge import Annotation
from fichero_server.models.segments import Segment
from fichero_server.security import accounts, authz


@pytest.fixture
def denied_setup(db, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    editor = app_db.create_user(
        username="nested-editor", display_name="Editor", password_hash=accounts.hash_password("password"),
    )
    app_db.set_library_role(user_id=editor.id, library_path=authz.normalize_library_path(library_path), role="editor")
    allowed = Document(name="allowed.jpg")
    denied = Document(name="denied.jpg")
    db.save(allowed)
    db.save(denied)
    app_db.set_library_acl_override(
        user_id=editor.id, library_path=authz.normalize_library_path(library_path),
        target_id=denied.id, effect="deny",
    )
    ctx = ActionContext(actor="nested-editor", library_path=library_path)
    return ctx, allowed, denied


def _anchor(document_id: str) -> dict:
    return {"document_id": document_id, "rect": [0.1, 0.1, 0.2, 0.1]}


def test_an_annotation_on_an_allowed_document_anchored_in_a_denied_one(db, denied_setup):
    """SHAPE: a nested object names a different document from the top level."""
    ctx, allowed, denied = denied_setup
    before = len(db.all(Annotation))
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(db, "annotation.create", {
            "kind": "highlight", "document_id": allowed.id, "anchor": _anchor(denied.id)}, ctx)
    assert len(db.all(Annotation)) == before


def test_a_segment_created_on_an_allowed_document_with_an_anchor_on_a_denied_one(db, denied_setup):
    """SHAPE: the top level is allowed and the nested object is not -- the nested one decides."""
    ctx, allowed, denied = denied_setup
    before = len(db.all(Segment))
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(db, "segment.create", {
            "document_id": allowed.id, "pass_id": "p", "kind": "word", "anchor": _anchor(denied.id),
        }, ctx)
    assert len(db.all(Segment)) == before


def test_a_reading_whose_denied_document_is_three_levels_down(db, denied_setup):
    """SHAPE: depth -- an anchor's `refines` chain."""
    ctx, allowed, denied = denied_setup
    before = len(db.all(ContentRepresentation))
    anchor = _anchor(allowed.id)
    anchor["refines"] = _anchor(denied.id)
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(db, "representation.create", {
            "document_id": allowed.id, "kind": "transcription", "content": "x", "source_anchor": anchor,
        }, ctx)
    assert len(db.all(ContentRepresentation)) == before


def test_an_update_object_that_moves_an_annotation_into_a_denied_document(db, denied_setup):
    """SHAPE: an object inside an object (`update.anchor.document_id`)."""
    ctx, allowed, denied = denied_setup
    owner = ActionContext(actor="system", library_path=ctx.library_path, is_bootstrap=True)
    made = registry.invoke(db, "annotation.create", {
        "kind": "highlight", "document_id": allowed.id, "anchor": _anchor(allowed.id)}, owner)
    annotation_id = made.result["id"] if isinstance(made.result, dict) else made.result.id
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(db, "annotation.update", {
            "annotation_id": annotation_id, "update": {"anchor": _anchor(denied.id)},
        }, ctx)
    assert db.get(Annotation, annotation_id).anchor.document_id == allowed.id


def test_an_allowed_nested_document_still_writes(db, denied_setup):
    """The positive control: the check is document-scoped, not a lockout of nested writes."""
    ctx, allowed, denied = denied_setup
    before = len(db.all(Annotation))
    registry.invoke(db, "annotation.create", {
        "kind": "highlight", "document_id": allowed.id, "anchor": _anchor(allowed.id)}, ctx)
    assert len(db.all(Annotation)) == before + 1
