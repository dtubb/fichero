"""Tests for generic library item links (#2590 backend slice).

LibraryItemLink connects any two library items (document, note, entity,
claim) via source_id/target_id and reuses the typed ClaimRelationType
vocabulary from KnowledgeClaimLink. These tests cover the new /api/links CRUD.
"""

from datetime import datetime

from fichero.knowledge_models import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeEntity,
    LibraryItemLink,
    LibraryItemType,
)
from fichero.models import Document, DocType, Note


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(db, name: str = "Source") -> Document:
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _make_note(db, target: Document) -> Note:
    note = Note(target_type="Document", target_id=target.id, content="annotation")
    db.save(note)
    return note


def _make_entity(db, canonical_name: str = "Entity") -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name=canonical_name)
    db.save(entity)
    return entity


def _make_claim(db, doc: Document, text: str = "A claim") -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=text,
        source_document_id=doc.id,
        entity_ids=[],
        confidence=0.7,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(claim)
    return claim


# ---------------------------------------------------------------------------
# POST /api/links
# ---------------------------------------------------------------------------


class TestCreateLibraryLink:
    def test_create_document_to_entity_link(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        r = client.post("/api/links", json={
            "source_id": doc.id,
            "source_type": "document",
            "target_id": entity.id,
            "target_type": "entity",
            "relation_type": "related_to",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["source_id"] == doc.id
        assert data["source_type"] == "document"
        assert data["target_id"] == entity.id
        assert data["target_type"] == "entity"
        assert data["relation_type"] == "related_to"

    def test_missing_source_returns_404(self, client, db):
        entity = _make_entity(db)
        r = client.post("/api/links", json={
            "source_id": "missing-id",
            "source_type": "document",
            "target_id": entity.id,
            "target_type": "entity",
            "relation_type": "related_to",
        })
        assert r.status_code == 404

    def test_missing_target_returns_404(self, client, db):
        doc = _make_document(db)
        r = client.post("/api/links", json={
            "source_id": doc.id,
            "source_type": "document",
            "target_id": "missing-id",
            "target_type": "entity",
            "relation_type": "related_to",
        })
        assert r.status_code == 404

    def test_invalid_item_type_returns_400(self, client, db):
        doc = _make_document(db)
        r = client.post("/api/links", json={
            "source_id": doc.id,
            "source_type": "not-a-type",
            "target_id": doc.id,
            "target_type": "document",
            "relation_type": "related_to",
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/links
# ---------------------------------------------------------------------------


class TestListLibraryLinks:
    def test_lists_links_for_source(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.cites,
        )
        db.save(link)
        r = client.get(f"/api/links?source_id={doc.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["id"] == link.id

    def test_filters_by_relation_type(self, client, db):
        doc = _make_document(db)
        e1 = _make_entity(db, canonical_name="one")
        e2 = _make_entity(db, canonical_name="two")
        l1 = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=e1.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.supports,
        )
        l2 = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=e2.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.contradicts,
        )
        db.save(l1)
        db.save(l2)
        r = client.get(f"/api/links?source_id={doc.id}&relation_type=contradicts")
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert l2.id in ids
        assert l1.id not in ids


# ---------------------------------------------------------------------------
# GET /api/links/{link_id}
# ---------------------------------------------------------------------------


class TestGetLibraryLink:
    def test_get_existing_link(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.related_to,
        )
        db.save(link)
        r = client.get(f"/api/links/{link.id}")
        assert r.status_code == 200
        assert r.json()["id"] == link.id

    def test_get_missing_link_returns_404(self, client):
        r = client.get("/api/links/missing-link")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/links/{link_id}
# ---------------------------------------------------------------------------


class TestUpdateLibraryLink:
    def test_patch_relation_type(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.supports,
        )
        db.save(link)
        r = client.patch(f"/api/links/{link.id}", json={"relation_type": "cites"})
        assert r.status_code == 200, r.text
        assert r.json()["relation_type"] == "cites"
        assert r.json()["updated_at"] is not None

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/links/missing-link", json={"link_quality": 0.9})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/links/{link_id}
# ---------------------------------------------------------------------------


class TestDeleteLibraryLink:
    def test_delete_removes_link(self, client, db):
        doc = _make_document(db)
        note = _make_note(db, doc)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=note.id,
            target_type=LibraryItemType.note,
            relation_type=ClaimRelationType.cites,
        )
        db.save(link)
        r = client.delete(f"/api/links/{link.id}")
        assert r.status_code == 200
        assert r.json()["link_id"] == link.id
        r2 = client.get(f"/api/links/{link.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/links/missing-link")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/library-items/{item_id}/links
# ---------------------------------------------------------------------------


class TestListLinksForItem:
    def test_includes_outgoing_and_incoming(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        claim = _make_claim(db, doc)
        l1 = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.related_to,
        )
        l2 = LibraryItemLink(
            source_id=claim.id,
            source_type=LibraryItemType.claim,
            target_id=doc.id,
            target_type=LibraryItemType.document,
            relation_type=ClaimRelationType.cites,
        )
        db.save(l1)
        db.save(l2)
        r = client.get(f"/api/library-items/{doc.id}/links")
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert l1.id in ids
        assert l2.id in ids
        assert r.json()["count"] == 2


# ---------------------------------------------------------------------------
# Read authz — library-path header enforcement (#2590)
# ---------------------------------------------------------------------------


class TestReadLibraryLinksRequireLibraryPath:
    """The three read endpoints must require the X-Fichero-Library-Path header."""

    def test_list_links_requires_library_path(self, client):
        r = client.get("/api/links", headers={"X-Fichero-Library-Path": ""})
        assert r.status_code == 400
        assert "library" in r.json()["detail"].lower()

    def test_get_link_requires_library_path(self, client):
        r = client.get("/api/links/some-link-id", headers={"X-Fichero-Library-Path": ""})
        assert r.status_code == 400
        assert "library" in r.json()["detail"].lower()

    def test_list_links_for_item_requires_library_path(self, client):
        r = client.get(
            "/api/library-items/some-item-id/links",
            headers={"X-Fichero-Library-Path": ""},
        )
        assert r.status_code == 400
        assert "library" in r.json()["detail"].lower()
