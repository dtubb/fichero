"""Unit tests for /api/annotations CRUD and crop helpers (#914)."""

from __future__ import annotations

import pytest

from fichero.knowledge_models import Annotation, AnnotationKind
from fichero.models import DocType, Document, FileType, Status
from fichero.workflows.tools._annotation_input import crop_text


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
