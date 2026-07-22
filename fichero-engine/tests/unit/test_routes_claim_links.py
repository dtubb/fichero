"""Tests for knowledge claim link routes.

ClaimLinks connect two KnowledgeClaims with a typed relationship (supports,
contradicts, refines, etc.). These routes manage the graph edges between
claims. Uses real in-memory DB fixtures.
"""

from datetime import datetime

import pytest

from fichero.models import ActionAudit
from fichero.models.knowledge import (
    ClaimRelationType,
    ClaimCurationState,
    KnowledgeClaim,
    KnowledgeClaimLink,
)
from fichero.models import Document, DocType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(db, name: str = "Source") -> Document:
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _make_claim(db, doc: Document, text: str = "A claim") -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=text,
        source_document_id=doc.id,
        entity_ids=[],
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.7,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(claim)
    return claim


def _make_link(
    db,
    claim: KnowledgeClaim,
    related: KnowledgeClaim,
    relation: ClaimRelationType = ClaimRelationType.supports,
) -> KnowledgeClaimLink:
    link = KnowledgeClaimLink(
        claim_id=claim.id,
        related_claim_id=related.id,
        relation_type=relation,
        link_quality=0.8,
        created_at=datetime.now(),
    )
    db.save(link)
    return link


# ---------------------------------------------------------------------------
# POST /api/claims/{claim_id}/links
# ---------------------------------------------------------------------------


class TestCreateClaimLink:
    def test_create_link(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc, "Claim 1")
        c2 = _make_claim(db, doc, "Claim 2")
        r = client.post(f"/api/claims/{c1.id}/links", json={
            "related_claim_id": c2.id,
            "relation_type": "supports",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["claim_id"] == c1.id
        assert data["related_claim_id"] == c2.id

    def test_missing_source_claim_returns_404(self, client, db):
        doc = _make_document(db)
        c2 = _make_claim(db, doc)
        r = client.post("/api/claims/no-such-claim/links", json={
            "related_claim_id": c2.id,
            "relation_type": "supports",
        })
        assert r.status_code == 404

    def test_missing_related_claim_returns_404(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc)
        r = client.post(f"/api/claims/{c1.id}/links", json={
            "related_claim_id": "no-such-claim",
            "relation_type": "supports",
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/claims/{claim_id}/links
# ---------------------------------------------------------------------------


class TestListClaimLinks:
    def test_returns_links_for_claim(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc, "Claim A")
        c2 = _make_claim(db, doc, "Claim B")
        c3 = _make_claim(db, doc, "Claim C")
        _make_link(db, c1, c2)
        _make_link(db, c1, c3)
        r = client.get(f"/api/claims/{c1.id}/links")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_includes_incoming_links(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc, "Source")
        c2 = _make_claim(db, doc, "Target")
        _make_link(db, c2, c1)  # c2 -> c1 (c1 is related_claim_id)
        r = client.get(f"/api/claims/{c1.id}/links")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1  # incoming link is included

    def test_missing_claim_returns_404(self, client):
        r = client.get("/api/claims/no-such-claim/links")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/claim-links/{link_id}
# ---------------------------------------------------------------------------


class TestGetClaimLink:
    def test_get_existing_link(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc)
        c2 = _make_claim(db, doc)
        link = _make_link(db, c1, c2)
        r = client.get(f"/api/claim-links/{link.id}")
        assert r.status_code == 200
        assert r.json()["id"] == link.id

    def test_get_missing_link_returns_404(self, client):
        r = client.get("/api/claim-links/no-such-link")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/claim-links/{link_id}
# ---------------------------------------------------------------------------


class TestUpdateClaimLink:
    def test_patch_quality(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc)
        c2 = _make_claim(db, doc)
        link = _make_link(db, c1, c2)
        r = client.patch(f"/api/claim-links/{link.id}", json={"link_quality": 0.95})
        assert r.status_code == 200
        assert r.json()["link_quality"] == 0.95

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/claim-links/no-such-id", json={"link_quality": 0.5})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/claim-links/{link_id}
# ---------------------------------------------------------------------------


class TestDeleteClaimLink:
    def test_delete_removes_link(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc)
        c2 = _make_claim(db, doc)
        link = _make_link(db, c1, c2)
        r = client.delete(f"/api/claim-links/{link.id}")
        assert r.status_code == 200
        r2 = client.get(f"/api/claim-links/{link.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/claim-links/no-such-id")
        assert r.status_code == 404


class TestClaimLinkRouteAudit:
    def test_create_update_delete_routes_write_action_audit(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc, "Claim 1")
        c2 = _make_claim(db, doc, "Claim 2")

        created = client.post(
            f"/api/claims/{c1.id}/links",
            json={"related_claim_id": c2.id, "relation_type": "supports"},
        )
        assert created.status_code == 200
        link_id = created.json()["id"]
        create_audit = db.all(ActionAudit)[-1]
        assert create_audit.action_name == "claim.create_link"
        assert create_audit.target_ids == [link_id]

        updated = client.patch(
            f"/api/claim-links/{link_id}",
            json={"link_quality": 0.95},
        )
        assert updated.status_code == 200
        update_audit = db.all(ActionAudit)[-1]
        assert update_audit.action_name == "claim.update_link"
        assert update_audit.target_ids == [link_id]

        deleted = client.delete(f"/api/claim-links/{link_id}")
        assert deleted.status_code == 200
        delete_audit = db.all(ActionAudit)[-1]
        assert delete_audit.action_name == "claim.delete_link"
        assert delete_audit.target_ids == [link_id]


# ---------------------------------------------------------------------------
# GET /api/claims/{claim_id}/related
# ---------------------------------------------------------------------------


class TestGetRelatedClaims:
    def test_returns_related_claims(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc, "Main claim")
        c2 = _make_claim(db, doc, "Related claim")
        _make_link(db, c1, c2)
        r = client.get(f"/api/claims/{c1.id}/related")
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["items"]]
        assert c2.id in ids

    def test_missing_claim_returns_404(self, client):
        r = client.get("/api/claims/no-such-claim/related")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# #1123 Phase B — new ClaimRelationType kinds
# ---------------------------------------------------------------------------


class TestExtendedClaimRelationTypes:
    """The new relation kinds added by #1123 round-trip through the
    POST/GET/PATCH/DELETE endpoints. Without enum extension the FastAPI
    validator would 422-reject these values; this test pins the enum
    addition in place.
    """

    @pytest.mark.parametrize(
        "kind",
        [
            "corroborates",
            "derives_from",
            "cites",
            "follows",
            "caused_by",
            "related_to",
        ],
    )
    def test_create_with_new_kind(self, client, db, kind):
        doc = _make_document(db)
        c1 = _make_claim(db, doc, "claim 1")
        c2 = _make_claim(db, doc, "claim 2")
        r = client.post(
            f"/api/claims/{c1.id}/links",
            json={"related_claim_id": c2.id, "relation_type": kind},
        )
        assert r.status_code == 200, r.text
        link_id = r.json()["id"]
        # Round-trip the value back via GET
        r2 = client.get(f"/api/claim-links/{link_id}")
        assert r2.status_code == 200
        assert r2.json()["relation_type"] == kind

    def test_patch_to_new_kind(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc)
        c2 = _make_claim(db, doc)
        link = _make_link(db, c1, c2, ClaimRelationType.supports)
        r = client.patch(
            f"/api/claim-links/{link.id}",
            json={"relation_type": "corroborates"},
        )
        assert r.status_code == 200
        assert r.json()["relation_type"] == "corroborates"

    def test_filter_related_by_new_kind(self, client, db):
        doc = _make_document(db)
        c1 = _make_claim(db, doc, "anchor")
        c2 = _make_claim(db, doc, "supporter")
        c3 = _make_claim(db, doc, "citation")
        _make_link(db, c1, c2, ClaimRelationType.supports)
        _make_link(db, c1, c3, ClaimRelationType.cites)
        r = client.get(f"/api/claims/{c1.id}/related?relation_type=cites")
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["items"]]
        assert c3.id in ids
        assert c2.id not in ids
