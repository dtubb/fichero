"""Unit tests for /api/annotations CRUD and crop helpers (#914)."""

from __future__ import annotations

import pytest

from fichero_server.models.knowledge import Annotation, AnnotationKind
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.workflows.tools._annotation_input import crop_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doc(db):
    """Persist a minimal Document so create_annotation can find it."""
    d = Document(
        id="doc-ann-test",
        name="test.txt",
        doc_type=DocType.file,
        file_type=FileType.text,
        status=Status.completed,
        page_content="Hello world. This is the document body.",
    )
    db.save(d)
    return d


@pytest.fixture
def page_doc(db):
    d = Document(
        id="page-ann-test",
        name="Page 1",
        doc_type=DocType.page,
        file_type=FileType.image,
        status=Status.completed,
        page_content="Page-scoped content",
    )
    db.save(d)
    return d


@pytest.fixture
def folder_doc(db):
    d = Document(
        id="folder-ann-test",
        name="Folder 1",
        doc_type=DocType.folder,
        status=Status.completed,
    )
    db.save(d)
    return d


# ---------------------------------------------------------------------------
# CRUD endpoint tests
# ---------------------------------------------------------------------------


class TestAnnotationCreate:
    def test_create_returns_annotation(self, client, doc):
        resp = client.post(
            "/api/annotations",
            json={
                "document_id": doc.id,
                "kind": "note",
                "text": "My note",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == doc.id
        assert data["kind"] == "note"
        assert data["text"] == "My note"
        assert "id" in data
        assert "created_at" in data

    def test_create_with_page_index_and_bbox(self, client, doc):
        resp = client.post(
            "/api/annotations",
            json={
                "document_id": doc.id,
                "kind": "highlight",
                "page_index": 2,
                "bbox": [0.1, 0.2, 0.5, 0.3],
                "color": "#FFFF00",
                "tags": ["important"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_index"] == 2
        assert data["bbox"] == [0.1, 0.2, 0.5, 0.3]
        assert data["color"] == "#FFFF00"

    def test_create_unknown_document_returns_404(self, client):
        resp = client.post(
            "/api/annotations",
            json={"document_id": "nonexistent", "kind": "note"},
        )
        assert resp.status_code == 404

    def test_create_page_scoped_annotation(self, client, page_doc):
        resp = client.post(
            "/api/annotations",
            json={
                "page_id": page_doc.id,
                "kind": "highlight",
                "text": "Page annotation",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_id"] == page_doc.id
        assert data["document_id"] == page_doc.id

    def test_create_folder_scoped_annotation(self, client, folder_doc):
        resp = client.post(
            "/api/annotations",
            json={
                "folder_id": folder_doc.id,
                "kind": "note",
                "text": "Folder annotation",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["folder_id"] == folder_doc.id
        assert data["document_id"] is None


class TestAnnotationList:
    def test_list_empty(self, client, doc):
        resp = client.get("/api/annotations", params={"document_id": doc.id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["items"] == []

    def test_list_by_document_id(self, client, db, doc):
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.note, text="n1")
        db.save(ann)
        other_doc = Document(
            id="other-doc",
            name="other.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            status=Status.completed,
        )
        db.save(other_doc)
        ann2 = Annotation(document_id=other_doc.id, kind=AnnotationKind.bookmark)
        db.save(ann2)

        resp = client.get("/api/annotations", params={"document_id": doc.id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["items"][0]["id"] == ann.id

    def test_list_filter_by_kind(self, client, db, doc):
        db.save(Annotation(document_id=doc.id, kind=AnnotationKind.highlight))
        db.save(Annotation(document_id=doc.id, kind=AnnotationKind.note, text="n"))

        resp = client.get("/api/annotations", params={"kind": "highlight"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["kind"] == "highlight" for i in items)

    def test_list_filter_by_tag(self, client, db, doc):
        db.save(Annotation(document_id=doc.id, kind=AnnotationKind.highlight, tags=["draft"]))
        db.save(Annotation(document_id=doc.id, kind=AnnotationKind.note, tags=["final"]))

        resp = client.get("/api/annotations", params={"tag": "draft"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert "draft" in items[0]["tags"]

    def test_list_filter_min_rating(self, client, db, doc):
        db.save(Annotation(document_id=doc.id, kind=AnnotationKind.rating, rating=2))
        db.save(Annotation(document_id=doc.id, kind=AnnotationKind.rating, rating=5))

        resp = client.get("/api/annotations", params={"min_rating": 4})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["rating"] == 5

    def test_list_by_page_scope(self, client, db, page_doc):
        page_ann = Annotation(
            document_id=page_doc.id,
            page_id=page_doc.id,
            kind=AnnotationKind.note,
            text="page scope",
        )
        db.save(page_ann)
        db.save(Annotation(document_id="other-doc", kind=AnnotationKind.note, text="other"))

        resp = client.get("/api/annotations", params={"page_id": page_doc.id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["items"][0]["id"] == page_ann.id

    def test_list_by_folder_scope(self, client, db, folder_doc, doc):
        folder_ann = Annotation(
            folder_id=folder_doc.id,
            kind=AnnotationKind.note,
            text="folder scope",
        )
        db.save(folder_ann)
        db.save(Annotation(document_id=doc.id, kind=AnnotationKind.note, text="other"))

        resp = client.get("/api/annotations", params={"folder_id": folder_doc.id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["items"][0]["id"] == folder_ann.id


class TestAnnotationGet:
    def test_get_existing(self, client, db, doc):
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.note, text="hello")
        db.save(ann)

        resp = client.get(f"/api/annotations/{ann.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == ann.id

    def test_get_missing_returns_404(self, client):
        resp = client.get("/api/annotations/does-not-exist")
        assert resp.status_code == 404


class TestAnnotationPatch:
    def test_patch_text(self, client, db, doc):
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.note, text="old")
        db.save(ann)

        resp = client.patch(f"/api/annotations/{ann.id}", json={"text": "updated"})
        assert resp.status_code == 200
        assert resp.json()["text"] == "updated"

    def test_patch_adds_tags(self, client, db, doc):
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.highlight)
        db.save(ann)

        resp = client.patch(f"/api/annotations/{ann.id}", json={"tags": ["tag1", "tag2"]})
        assert resp.status_code == 200
        assert "tag1" in resp.json()["tags"]

    def test_patch_missing_returns_404(self, client):
        resp = client.patch("/api/annotations/nope", json={"text": "x"})
        assert resp.status_code == 404


class TestAnnotationDelete:
    def test_delete_removes_annotation(self, client, db, doc):
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.bookmark)
        db.save(ann)

        resp = client.delete(f"/api/annotations/{ann.id}")
        assert resp.status_code == 204

        assert db.get(Annotation, ann.id) is None

    def test_delete_missing_returns_404(self, client):
        resp = client.delete("/api/annotations/ghost")
        assert resp.status_code == 404

    def test_delete_page_scoped_annotation(self, client, db, page_doc):
        ann = Annotation(
            document_id=page_doc.id,
            page_id=page_doc.id,
            kind=AnnotationKind.bookmark,
        )
        db.save(ann)

        resp = client.delete(f"/api/annotations/{ann.id}")
        assert resp.status_code == 204
        assert db.get(Annotation, ann.id) is None

    def test_delete_folder_scoped_annotation(self, client, db, folder_doc):
        ann = Annotation(folder_id=folder_doc.id, kind=AnnotationKind.bookmark)
        db.save(ann)

        resp = client.delete(f"/api/annotations/{ann.id}")
        assert resp.status_code == 204
        assert db.get(Annotation, ann.id) is None


# ---------------------------------------------------------------------------
# Crop helper unit tests (no HTTP, pure-function)
# ---------------------------------------------------------------------------


class TestCropText:
    def test_returns_char_range(self):
        doc = Document(
            id="d1",
            name="d.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            status=Status.completed,
            page_content="ABCDEFGHIJ",
        )
        ann = Annotation(document_id="d1", kind=AnnotationKind.highlight, char_start=2, char_end=5)
        assert crop_text(doc, ann) == "CDE"

    def test_falls_back_to_annotation_text(self):
        doc = Document(
            id="d2",
            name="d.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            status=Status.completed,
        )
        ann = Annotation(document_id="d2", kind=AnnotationKind.note, text="fallback note")
        assert crop_text(doc, ann) == "fallback note"

    def test_returns_none_when_no_content_and_no_text(self):
        doc = Document(
            id="d3",
            name="d.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            status=Status.completed,
        )
        ann = Annotation(document_id="d3", kind=AnnotationKind.bookmark)
        assert crop_text(doc, ann) is None


# ---------------------------------------------------------------------------
# Additive anchor fields + ink metadata (#2256)
# ---------------------------------------------------------------------------


class TestAnnotationAnchorFields:
    """anchor_kind / paragraph_index / ink metadata are additive (#2256).

    Pre-existing libraries created before these fields existed must keep
    working: the DB column reconcile (ALTER TABLE ADD COLUMN) is what makes
    the no-migration rule hold, so a persistence round-trip is the regression
    that proves a new field doesn't break save()/get() on the annotation table.
    """

    def test_create_with_anchor_kind_and_paragraph_index(self, client, doc):
        resp = client.post(
            "/api/annotations",
            json={
                "document_id": doc.id,
                "kind": "highlight",
                "anchor_kind": "paragraph",
                "paragraph_index": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["anchor_kind"] == "paragraph"
        assert data["paragraph_index"] == 3

    def test_anchor_fields_persist_round_trip(self, client, db, doc):
        resp = client.post(
            "/api/annotations",
            json={
                "document_id": doc.id,
                "kind": "highlight",
                "anchor_kind": "bbox",
                "paragraph_index": 0,
            },
        )
        ann_id = resp.json()["id"]
        # Read back through the DB layer (not just the response echo) to prove
        # the columns were actually persisted, not silently dropped.
        stored = db.get(Annotation, ann_id)
        assert stored is not None
        assert stored.anchor_kind == "bbox"
        assert stored.paragraph_index == 0

    def test_create_with_ink_metadata(self, client, doc):
        # The ink fields live in the free `metadata` dict (extra="allow"), so
        # they need no schema column — but they must round-trip intact.
        resp = client.post(
            "/api/annotations",
            json={
                "document_id": doc.id,
                "kind": "note",
                "anchor_kind": "ink",
                "text": "transcribed ink",
                "metadata": {
                    "ink_data": "base64-pencilkit-stroke-data",
                    "ocr_provider": "apple_vision",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["anchor_kind"] == "ink"
        assert data["metadata"]["ink_data"] == "base64-pencilkit-stroke-data"
        assert data["metadata"]["ocr_provider"] == "apple_vision"

    def test_patch_sets_anchor_fields(self, client, db, doc):
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.highlight)
        db.save(ann)
        resp = client.patch(
            f"/api/annotations/{ann.id}",
            json={"anchor_kind": "paragraph", "paragraph_index": 7},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["anchor_kind"] == "paragraph"
        assert data["paragraph_index"] == 7
        assert db.get(Annotation, ann.id).paragraph_index == 7

    def test_defaults_none_when_omitted(self, client, doc):
        # Backward compatibility: a client that never sends the new fields gets
        # nulls, exactly as before they existed.
        resp = client.post(
            "/api/annotations",
            json={"document_id": doc.id, "kind": "note", "text": "plain"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["anchor_kind"] is None
        assert data["paragraph_index"] is None


# ---------------------------------------------------------------------------
# Ephemeral crop — POST /annotations/crop (#2256)
# ---------------------------------------------------------------------------


class TestEphemeralCrop:
    """POST /annotations/crop returns cropped content WITHOUT persisting."""

    def test_text_crop_by_char_offsets(self, client, doc):
        # doc.page_content == "Hello world. This is the document body."
        resp = client.post(
            "/api/annotations/crop",
            json={"document_id": doc.id, "char_start": 0, "char_end": 5},
        )
        assert resp.status_code == 200
        assert resp.text == "Hello"

    def test_text_crop_falls_back_to_request_text(self, client, doc):
        resp = client.post(
            "/api/annotations/crop",
            json={"document_id": doc.id, "kind": "note", "text": "free note"},
        )
        assert resp.status_code == 200
        assert resp.text == "free note"

    def test_unknown_document_returns_404(self, client):
        resp = client.post(
            "/api/annotations/crop",
            json={"document_id": "does-not-exist", "char_start": 0, "char_end": 3},
        )
        assert resp.status_code == 404

    def test_missing_document_id_is_422(self, client):
        resp = client.post("/api/annotations/crop", json={"char_start": 0, "char_end": 3})
        assert resp.status_code == 422

    def test_no_crop_available_returns_404(self, client, doc):
        # bookmark with neither offsets nor text → nothing to crop.
        resp = client.post(
            "/api/annotations/crop",
            json={"document_id": doc.id, "kind": "bookmark"},
        )
        assert resp.status_code == 404

    def test_crop_persists_nothing(self, client, doc):
        before = client.get("/api/annotations", params={"document_id": doc.id}).json()["count"]
        client.post(
            "/api/annotations/crop",
            json={"document_id": doc.id, "char_start": 0, "char_end": 5},
        )
        after = client.get("/api/annotations", params={"document_id": doc.id}).json()["count"]
        assert before == after == 0


# ---------------------------------------------------------------------------
# #2105 / #3442: crop routes must advertise their real media types so the
# generated OpenAPI client can fetch PNG bytes (not silently decode JSON).
# ---------------------------------------------------------------------------


class TestCropResponseContract:
    """The crop routes return PNG bytes or a text substring — the OpenAPI
    schema must say so, or typed clients can never render the image crop
    (the old application/json default hid it)."""

    @pytest.mark.parametrize(
        "path,method",
        [
            ("/api/annotations/{annotation_id}/crop", "get"),
            ("/api/annotations/crop", "post"),
        ],
    )
    def test_crop_advertises_binary_and_text(self, client, path, method):
        schema = client.get("/openapi.json").json()
        content = schema["paths"][path][method]["responses"]["200"]["content"]
        # The binary + text bodies must be advertised so typed clients can fetch
        # the image crop (the whole point of #2105). FastAPI also keeps its
        # default application/json entry, which the routes never actually send —
        # the generated client handles it as an unused body case.
        assert "image/png" in content, f"{method} {path} must advertise image/png"
        assert "text/plain" in content, f"{method} {path} must advertise text/plain"


# ---------------------------------------------------------------------------
# #3263 regression: created_by is set from the acting user
# ---------------------------------------------------------------------------


class TestAnnotationCreatedByAttribution:
    """Annotation.created_by must reflect the acting user, not the model default."""

    def test_create_action_sets_created_by_from_actor(self, db):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.knowledge import Annotation

        doc = Document(name="doc.pdf")
        db.save(doc)

        ctx = ActionContext(actor="alice", library_path="/lib/test.fichero")
        result = registry.invoke(
            db,
            "annotation.create",
            {
                "document_id": doc.id,
                "kind": "highlight",
                "text": "important",
            },
            ctx,
        )
        ann = db.get(Annotation, result.result["id"])
        assert ann is not None
        assert ann.created_by == "alice"

    def test_create_action_default_actor_is_human(self, db):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.knowledge import Annotation

        doc = Document(name="doc.pdf")
        db.save(doc)

        ctx = ActionContext(actor="system", library_path="/lib/test.fichero")
        result = registry.invoke(
            db,
            "annotation.create",
            {
                "document_id": doc.id,
                "kind": "note",
                "text": "a note",
            },
            ctx,
        )
        ann = db.get(Annotation, result.result["id"])
        assert ann is not None
        assert ann.created_by == "system"

    def test_duplicate_action_sets_created_by_from_actor(self, db):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.knowledge import Annotation

        doc = Document(name="doc.pdf")
        db.save(doc)

        # Create as "bob"
        ctx_bob = ActionContext(actor="bob", library_path="/lib/test.fichero")
        create_result = registry.invoke(
            db,
            "annotation.create",
            {
                "document_id": doc.id,
                "kind": "highlight",
                "text": "original",
            },
            ctx_bob,
        )
        ann_id = create_result.result["id"]

        # Duplicate as "carol"
        ctx_carol = ActionContext(actor="carol", library_path="/lib/test.fichero")
        dup_result = registry.invoke(
            db,
            "annotation.duplicate",
            {"annotation_id": ann_id},
            ctx_carol,
        )
        dup_ann = db.get(Annotation, dup_result.result["id"])
        assert dup_ann is not None
        assert dup_ann.created_by == "carol"

    def test_promote_to_claim_action_inherits_actor(self, db):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.knowledge import KnowledgeClaim

        # Create an annotation with actor "dave"
        doc = Document(name="doc.pdf")
        db.save(doc)

        ctx = ActionContext(actor="dave", library_path="/lib/test.fichero")
        create_result = registry.invoke(
            db,
            "annotation.create",
            {
                "document_id": doc.id,
                "kind": "highlight",
                "text": "key insight",
            },
            ctx,
        )
        ann_id = create_result.result["id"]

        # Promote as "dave" (same actor)
        promote_result = registry.invoke(
            db,
            "annotation.promote_to_claim",
            {"annotation_id": ann_id},
            ctx,
        )
        claim_id = promote_result.result["claim_id"]
        claim = db.get(KnowledgeClaim, claim_id)
        assert claim is not None
        assert claim.created_by == "dave"


# ---------------------------------------------------------------------------
# #3266 regression: bbox and color validation
# ---------------------------------------------------------------------------


class TestAnnotationBboxValidation:
    """Annotation models reject malformed bbox and color."""

    def test_annotation_model_bbox_wrong_length_rejected(self, client):
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            Annotation(kind=AnnotationKind.highlight, bbox=[0.1, 0.2, 0.3])
        assert "bbox must have exactly 4 elements" in str(exc.value)

    def test_annotation_model_zero_bbox_rejected(self, client):
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            Annotation(kind=AnnotationKind.highlight, bbox=[0.0, 0.0, 0.0, 0.0])
        assert "width must be > 0" in str(exc.value)

    def test_annotation_model_invalid_color_rejected(self, client):
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            Annotation(kind=AnnotationKind.highlight, color="red")
        assert "hex colour" in str(exc.value)

    def test_bbox_wrong_length_rejected(self, client):
        """bbox must be exactly 4 elements."""
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        with pytest.raises(ValidationError) as exc:
            AnnotationCreateRequest(kind="highlight", bbox=[0.1, 0.2, 0.3])
        assert "bbox must have exactly 4 elements" in str(exc.value)

    def test_bbox_negative_value_rejected(self, client):
        """bbox values must be in [0, 1]."""
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        with pytest.raises(ValidationError) as exc:
            AnnotationCreateRequest(kind="highlight", bbox=[-0.1, 0.2, 0.3, 0.4])
        assert "must be in [0, 1]" in str(exc.value)

    def test_bbox_zero_width_rejected(self, client):
        """bbox width must be > 0."""
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        with pytest.raises(ValidationError) as exc:
            AnnotationCreateRequest(kind="highlight", bbox=[0.1, 0.2, 0.0, 0.4])
        assert "width must be > 0" in str(exc.value)

    def test_bbox_zero_height_rejected(self, client):
        """bbox height must be > 0."""
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        with pytest.raises(ValidationError) as exc:
            AnnotationCreateRequest(kind="highlight", bbox=[0.1, 0.2, 0.3, 0.0])
        assert "height must be > 0" in str(exc.value)

    def test_bbox_valid_passes(self, client):
        """Valid bbox values pass."""
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        req = AnnotationCreateRequest(kind="highlight", bbox=[0.1, 0.2, 0.3, 0.4])
        assert req.bbox == [0.1, 0.2, 0.3, 0.4]

    def test_bbox_none_passes(self, client):
        """None bbox is allowed."""
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        req = AnnotationCreateRequest(kind="highlight", bbox=None)
        assert req.bbox is None

    def test_color_invalid_string_rejected(self, client):
        """color must be hex like #RRGGBB."""
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        with pytest.raises(ValidationError) as exc:
            AnnotationCreateRequest(kind="highlight", color="red")
        assert "hex colour" in str(exc.value)

    def test_color_valid_hex_passes(self, client):
        """Valid hex colour passes."""
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        req = AnnotationCreateRequest(kind="highlight", color="#FFFF00")
        assert req.color == "#FFFF00"

    def test_color_hex_with_alpha_passes(self, client):
        """Hex colour with alpha (#RRGGBBAA) passes."""
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        req = AnnotationCreateRequest(kind="highlight", color="#FFFF0080")
        assert req.color == "#FFFF0080"

    def test_color_none_passes(self, client):
        """None color is allowed."""
        from fichero_server.api.routes.document.annotations import AnnotationCreateRequest
        req = AnnotationCreateRequest(kind="highlight", color=None)
        assert req.color is None


class TestAnnotationPatchBboxValidation:
    """AnnotationPatchRequest also validates bbox and color."""

    def test_patch_bbox_wrong_length_rejected(self, client):
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationPatchRequest
        with pytest.raises(ValidationError) as exc:
            AnnotationPatchRequest(bbox=[0.1, 0.2])
        assert "bbox must have exactly 4 elements" in str(exc.value)

    def test_patch_color_invalid_rejected(self, client):
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationPatchRequest
        with pytest.raises(ValidationError) as exc:
            AnnotationPatchRequest(color="not-a-color")
        assert "hex colour" in str(exc.value)

    def test_patch_rating_out_of_range_rejected(self, client):
        from pydantic import ValidationError
        from fichero_server.api.routes.document.annotations import AnnotationPatchRequest
        with pytest.raises(ValidationError):
            AnnotationPatchRequest(rating=0)
        with pytest.raises(ValidationError):
            AnnotationPatchRequest(rating=6)
