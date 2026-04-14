"""Tests for review queue routes.

The review queue manages KnowledgeClaim curation state transitions
(unreviewed → shortlisted → curated/rejected). Routes live under
/api/claims/... because the router uses prefix="/claims" and is mounted
at /api.
"""

import pytest
from unittest.mock import MagicMock

from fichero.knowledge_models import (
    KnowledgeClaim,
    KnowledgeEntity,
    ClaimCurationState,
    ClaimType,
    EpistemicStatus,
    SourceType,
    EntityType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(name: str = "Alice", entity_id: str = "ent-1") -> KnowledgeEntity:
    return KnowledgeEntity(id=entity_id, canonical_name=name)


def _make_claim(
    claim_id: str = "claim-1",
    text: str = "Paris is the capital of France.",
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed,
    entity_ids: list[str] | None = None,
) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=claim_id,
        text=text,
        source_document_id="doc-1",
        source_ids=["doc-1"],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.tentative,
        curation_state=curation_state,
        confidence=0.8,
        entity_ids=entity_ids or [],
    )


# ---------------------------------------------------------------------------
# PATCH /api/claims/{claim_id}/transition
# ---------------------------------------------------------------------------


class TestTransitionClaim:
    def test_transition_to_shortlisted(self, client, db):
        claim = _make_claim()
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "shortlisted",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["from_state"] == "unreviewed"
        assert data["to_state"] == "shortlisted"

    def test_transition_to_curated(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.shortlisted)
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "curated",
            "reason": "Verified",
        })
        assert r.status_code == 200
        assert r.json()["to_state"] == "curated"

    def test_transition_to_rejected(self, client, db):
        claim = _make_claim()
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "rejected",
            "reason": "Duplicate",
        })
        assert r.status_code == 200
        assert r.json()["to_state"] == "rejected"

    def test_transition_missing_claim_returns_404(self, client):
        r = client.patch("/api/claims/no-such-claim/transition", json={
            "to_state": "shortlisted",
        })
        assert r.status_code == 404

    def test_transition_invalid_state_returns_400(self, client, db):
        claim = _make_claim()
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "invalid-state",
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/claims/batch/transition
# ---------------------------------------------------------------------------


class TestBatchTransition:
    def test_batch_transitions_succeed(self, client, db):
        c1 = _make_claim("c-1", "Claim one")
        c2 = _make_claim("c-2", "Claim two")
        db.save(c1)
        db.save(c2)

        r = client.post("/api/claims/batch/transition", json={
            "claim_ids": ["c-1", "c-2"],
            "to_state": "shortlisted",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0

    def test_batch_transition_with_missing_claims(self, client, db):
        c1 = _make_claim("c-1", "Claim one")
        db.save(c1)

        r = client.post("/api/claims/batch/transition", json={
            "claim_ids": ["c-1", "no-such-claim"],
            "to_state": "shortlisted",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    def test_batch_transition_invalid_state_returns_400(self, client):
        r = client.post("/api/claims/batch/transition", json={
            "claim_ids": ["c-1"],
            "to_state": "bogus",
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/claims/queues/unreviewed
# ---------------------------------------------------------------------------


class TestUnreviewedQueue:
    def test_empty_queue(self, client):
        r = client.get("/api/claims/queues/unreviewed")
        assert r.status_code == 200
        data = r.json()
        assert data["queue"] == "unreviewed"
        assert data["claims"] == []
        assert data["total"] == 0

    def test_returns_unreviewed_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.unreviewed)
        db.save(claim)

        r = client.get("/api/claims/queues/unreviewed")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["claims"][0]["claim_id"] == claim.id

    def test_does_not_return_shortlisted_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.shortlisted)
        db.save(claim)

        r = client.get("/api/claims/queues/unreviewed")
        assert r.status_code == 200
        assert r.json()["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/claims/queues/shortlisted
# ---------------------------------------------------------------------------


class TestShortlistedQueue:
    def test_returns_shortlisted_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.shortlisted)
        db.save(claim)

        r = client.get("/api/claims/queues/shortlisted")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["queue"] == "shortlisted"


# ---------------------------------------------------------------------------
# GET /api/claims/queues/curated
# ---------------------------------------------------------------------------


class TestCuratedQueue:
    def test_returns_curated_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.curated)
        db.save(claim)

        r = client.get("/api/claims/queues/curated")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["queue"] == "curated"


# ---------------------------------------------------------------------------
# GET /api/claims/queues/rejected
# ---------------------------------------------------------------------------


class TestRejectedQueue:
    def test_returns_rejected_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.rejected)
        db.save(claim)

        r = client.get("/api/claims/queues/rejected")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["queue"] == "rejected"

    def test_filter_by_question(self, client, db):
        c1 = _make_claim("c-1", "Paris is the capital", ClaimCurationState.rejected)
        c2 = _make_claim("c-2", "The sky is blue", ClaimCurationState.rejected)
        db.save(c1)
        db.save(c2)

        r = client.get("/api/claims/queues/rejected?question=Paris")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["claims"][0]["claim_id"] == "c-1"
