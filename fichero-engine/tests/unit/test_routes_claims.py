"""Tests for knowledge claim routes.

KnowledgeClaim connects text evidence to entities with provenance (source
document, excerpt, confidence). Tests verify CRUD, filtering, and validation
(source document must exist). Uses real in-memory DB fixtures.
"""

from datetime import datetime
from fichero.knowledge_models import (
    ClaimRelationType,
    ClaimCurationState,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    EntityType,
)
from fichero.models import Document, DocType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(db, name: str = "Source Doc") -> Document:
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _make_entity(db, name: str = "Alice") -> KnowledgeEntity:
    entity = KnowledgeEntity(
        canonical_name=name,
        entity_type=EntityType.person,
        aliases=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(entity)
    return entity


def _make_claim(db, doc: Document, text: str = "Alice was born in 1867.") -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=text,
        source_document_id=doc.id,
        entity_ids=[],
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.8,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(claim)
    return claim


# ---------------------------------------------------------------------------
# GET /api/claims
# ---------------------------------------------------------------------------


class TestListClaims:
    def test_empty_list(self, client):
        r = client.get("/api/claims")
        assert r.status_code == 200
        assert r.json()["items"] == []
        assert r.json()["count"] == 0

    def test_returns_saved_claims(self, client, db):
        doc = _make_document(db)
        _make_claim(db, doc, "Claim A")
        _make_claim(db, doc, "Claim B")
        r = client.get("/api/claims")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_filter_by_source_document(self, client, db):
        doc1 = _make_document(db, "Doc 1")
        doc2 = _make_document(db, "Doc 2")
        _make_claim(db, doc1)
        _make_claim(db, doc2)
        r = client.get(f"/api/claims?source_document_id={doc1.id}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["source_document_id"] == doc1.id

    def test_search_by_text(self, client, db):
        doc = _make_document(db)
        _make_claim(db, doc, "Alpha claim text")
        _make_claim(db, doc, "Beta claim text")
        r = client.get("/api/claims?q=alpha")
        assert r.status_code == 200
        data = r.json()["items"]
        assert len(data) == 1
        assert "Alpha" in data[0]["text"]


# ---------------------------------------------------------------------------
# POST /api/claims
# ---------------------------------------------------------------------------


class TestCreateClaim:
    def test_create_claim(self, client, db):
        doc = _make_document(db)
        r = client.post("/api/claims", json={
            "text": "Some knowledge claim",
            "source_document_id": doc.id,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["text"] == "Some knowledge claim"
        assert "id" in data

    def test_create_with_missing_document_returns_404(self, client):
        r = client.post("/api/claims", json={
            "text": "Claim",
            "source_document_id": "no-such-doc",
        })
        assert r.status_code == 404

    def test_create_with_entity_ids(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        r = client.post("/api/claims", json={
            "text": "Alice did something",
            "source_document_id": doc.id,
            "entity_ids": [entity.id],
        })
        assert r.status_code == 200
        assert entity.id in r.json()["entity_ids"]

    def test_create_with_missing_entity_returns_404(self, client, db):
        doc = _make_document(db)
        r = client.post("/api/claims", json={
            "text": "Claim",
            "source_document_id": doc.id,
            "entity_ids": ["no-such-entity"],
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/claims/{claim_id}
# ---------------------------------------------------------------------------


class TestGetClaim:
    def test_get_existing(self, client, db):
        doc = _make_document(db)
        claim = _make_claim(db, doc)
        r = client.get(f"/api/claims/{claim.id}")
        assert r.status_code == 200
        assert r.json()["id"] == claim.id

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/claims/no-such-claim")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/claims/{claim_id}
# ---------------------------------------------------------------------------


class TestPatchClaim:
    def test_patch_text(self, client, db):
        doc = _make_document(db)
        claim = _make_claim(db, doc, "Original text")
        r = client.patch(f"/api/claims/{claim.id}", json={"text": "Updated text"})
        assert r.status_code == 200
        assert r.json()["text"] == "Updated text"

    def test_patch_curation_state(self, client, db):
        doc = _make_document(db)
        claim = _make_claim(db, doc)
        r = client.patch(f"/api/claims/{claim.id}", json={"curation_state": "curated"})
        assert r.status_code == 200
        assert r.json()["curation_state"] == "curated"

    def test_patch_svo_fields_recomputes_canonical_predicate(self, client, db):
        doc = _make_document(db)
        claim = _make_claim(db, doc)
        r = client.patch(
            f"/api/claims/{claim.id}",
            json={
                "subject_canonical": "Alice",
                "predicate_verb": "served as",
                "object_phrase": "mayor",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["predicate_canonical"] == "served_as"
        assert data["svo_subject"] == "Alice"
        assert data["svo_verb"] == "served_as"
        assert data["svo_object"] == "mayor"

    def test_patch_allows_null_clearing_editable_fields(self, client, db):
        doc = _make_document(db)
        claim = _make_claim(db, doc)
        claim.source_excerpt = "original excerpt"
        db.save(claim)
        r = client.patch(f"/api/claims/{claim.id}", json={"source_excerpt": None})
        assert r.status_code == 200
        assert r.json()["source_excerpt"] is None

    def test_patch_missing_subject_entity_returns_404(self, client, db):
        doc = _make_document(db)
        claim = _make_claim(db, doc)
        r = client.patch(
            f"/api/claims/{claim.id}",
            json={"subject_entity_id": "no-such-entity"},
        )
        assert r.status_code == 404

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/claims/no-such-id", json={"text": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/claims/{claim_id}
# ---------------------------------------------------------------------------


class TestDeleteClaim:
    def test_delete_removes_claim_and_incident_links(self, client, db):
        doc = _make_document(db)
        left = _make_claim(db, doc, "Left claim")
        right = _make_claim(db, doc, "Right claim")
        link = KnowledgeClaimLink(
            claim_id=left.id,
            related_claim_id=right.id,
            relation_type=ClaimRelationType.supports,
        )
        db.save(link)

        r = client.delete(f"/api/claims/{left.id}")
        assert r.status_code == 204
        assert db.get(KnowledgeClaim, left.id) is None
        assert db.get(KnowledgeClaim, right.id) is not None
        assert db.get(KnowledgeClaimLink, link.id) is None

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/claims/no-such-id")
        assert r.status_code == 404
