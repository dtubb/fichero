"""Tests for knowledge claim routes.

KnowledgeClaim connects text evidence to entities with provenance (source
document, excerpt, confidence). Tests verify CRUD, filtering, and validation
(source document must exist). Uses real in-memory DB fixtures.
"""

from datetime import datetime
from fichero.models.knowledge import (
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


class TestAssignTimePeriod:
    def test_assigns_period_for_page_range(self, client, db):
        doc = _make_document(db, "Book")
        claim_p1 = _make_claim(db, doc, "Page 1 claim")
        claim_p1.source_page_label = "1"
        db.save(claim_p1)

        claim_p5 = _make_claim(db, doc, "Page 5 claim")
        claim_p5.source_page_label = "5"
        db.save(claim_p5)

        r = client.post(
            "/api/claims/assign-time-period",
            json={
                "source_document_id": doc.id,
                "page_start": 1,
                "page_end": 2,
                "time_start": "1933-01-01",
                "time_end": "1933-12-31",
                "time_precision": "year",
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["matched_count"] == 1
        assert payload["updated_count"] == 1
        assert payload["skipped_existing_count"] == 0
        assert payload["skipped_unparseable_page_label_count"] == 0
        assert db.get(KnowledgeClaim, claim_p1.id).time_start == "1933-01-01"
        assert db.get(KnowledgeClaim, claim_p5.id).time_start is None

    def test_assign_time_period_surfaces_unparseable_page_labels(self, client, db):
        doc = _make_document(db, "Book")
        claim_bad = _make_claim(db, doc, "Bad page label")
        claim_bad.source_page_label = "frontispiece"
        db.save(claim_bad)

        claim_p2 = _make_claim(db, doc, "Page 2 claim")
        claim_p2.source_page_label = "2"
        db.save(claim_p2)

        r = client.post(
            "/api/claims/assign-time-period",
            json={
                "source_document_id": doc.id,
                "page_start": 1,
                "page_end": 3,
                "time_start": "1933-01-01",
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["matched_count"] == 1
        assert payload["updated_count"] == 1
        assert payload["skipped_unparseable_page_label_count"] == 1

    def test_assigns_period_including_descendant_pages(self, client, db):
        folder = Document(name="Folder", doc_type=DocType.folder)
        db.save(folder)
        page = Document(name="Page 3", doc_type=DocType.page, parent_id=folder.id)
        db.save(page)
        claim = _make_claim(db, page, "Descendant page claim")
        claim.source_page_label = "3"
        db.save(claim)

        r = client.post(
            "/api/claims/assign-time-period",
            json={
                "source_document_id": folder.id,
                "include_descendants": True,
                "time_start": "1945-01-01",
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["matched_count"] == 1
        assert payload["updated_count"] == 1
        updated = db.get(KnowledgeClaim, claim.id)
        assert updated.time_start == "1945-01-01"
        assert updated.time_end == "1945-01-01"

    def test_respects_overwrite_existing_false(self, client, db):
        doc = _make_document(db, "Source")
        claim = _make_claim(db, doc, "already dated")
        claim.time_start = "1900-01-01"
        claim.time_end = "1900-12-31"
        db.save(claim)

        r = client.post(
            "/api/claims/assign-time-period",
            json={
                "source_document_id": doc.id,
                "time_start": "2000-01-01",
                "overwrite_existing": False,
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["matched_count"] == 1
        assert payload["updated_count"] == 0
        assert payload["skipped_existing_count"] == 1
        unchanged = db.get(KnowledgeClaim, claim.id)
        assert unchanged.time_start == "1900-01-01"

    def test_assigns_period_from_document_metadata(self, client, db):
        folder = Document(name="Book Folder", doc_type=DocType.folder)
        folder.metadata = {"publication_date": "1937-03-10"}
        db.save(folder)

        page = Document(name="Page 1", doc_type=DocType.page, parent_id=folder.id)
        db.save(page)
        claim = _make_claim(db, page, "Metadata dated claim")
        db.save(claim)

        r = client.post(
            "/api/claims/assign-time-period-from-metadata",
            json={
                "source_document_id": folder.id,
                "include_descendants": True,
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["time_start"] == "1937-03-10"
        assert payload["updated_count"] == 1
        updated = db.get(KnowledgeClaim, claim.id)
        assert updated.time_start == "1937-03-10"
        assert updated.time_end == "1937-03-10"


class TestResolveClaimSource:
    def test_resolve_by_claim_id_returns_page_and_char_span(self, client, db):
        doc = _make_document(db, "Primary source")
        claim = _make_claim(db, doc, "Ada signed the decree.")
        claim.source_page_label = "12"
        claim.source_char_start = 101
        claim.source_char_end = 127
        claim.source_excerpt = "Ada signed the decree"
        db.save(claim)

        r = client.post("/api/claims/resolve-source", json={"claim_id": claim.id})
        assert r.status_code == 200
        data = r.json()
        assert data["claim_id"] == claim.id
        assert data["source_document_id"] == doc.id
        assert data["source_page_label"] == "12"
        assert data["source_char_start"] == 101
        assert data["source_char_end"] == 127

    def test_resolve_by_svo_returns_exact_anchor(self, client, db):
        doc = _make_document(db, "Minutes")
        claim = _make_claim(db, doc, "Ada served as mayor in Popayan.")
        claim.subject_canonical = "Ada Lovelace"
        claim.predicate_verb = "served as"
        claim.object_phrase = "mayor in Popayan"
        claim.source_page_label = "7"
        claim.source_char_start = 20
        claim.source_char_end = 58
        claim.source_excerpt = "Ada served as mayor in Popayan."
        db.save(claim)

        r = client.post(
            "/api/claims/resolve-source",
            json={
                "subject_canonical": "Ada Lovelace",
                "predicate_verb": "served as",
                "object_phrase": "mayor in Popayan",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["claim_id"] == claim.id
        assert data["source_document_id"] == doc.id
        assert data["source_page_label"] == "7"
        assert data["source_char_start"] == 20
        assert data["source_char_end"] == 58

    def test_resolve_by_svo_prefers_matching_source_document(self, client, db):
        doc_a = _make_document(db, "Doc A")
        doc_b = _make_document(db, "Doc B")

        claim_a = _make_claim(db, doc_a, "Ada served as mayor in Popayan.")
        claim_a.subject_canonical = "Ada Lovelace"
        claim_a.predicate_verb = "served as"
        claim_a.object_phrase = "mayor in Popayan"
        claim_a.source_page_label = "4"
        claim_a.source_char_start = 10
        claim_a.source_char_end = 48
        db.save(claim_a)

        claim_b = _make_claim(db, doc_b, "Ada served as mayor in Popayan.")
        claim_b.subject_canonical = "Ada Lovelace"
        claim_b.predicate_verb = "served as"
        claim_b.object_phrase = "mayor in Popayan"
        claim_b.source_page_label = "9"
        claim_b.source_char_start = 30
        claim_b.source_char_end = 68
        db.save(claim_b)

        r = client.post(
            "/api/claims/resolve-source",
            json={
                "subject_canonical": "Ada Lovelace",
                "predicate_verb": "served as",
                "object_phrase": "mayor in Popayan",
                "source_document_id": doc_b.id,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["claim_id"] == claim_b.id
        assert data["source_document_id"] == doc_b.id
        assert data["source_page_label"] == "9"

    def test_resolve_requires_claim_id_or_full_svo(self, client):
        r = client.post(
            "/api/claims/resolve-source",
            json={"subject_canonical": "Ada Lovelace"},
        )
        assert r.status_code == 400
