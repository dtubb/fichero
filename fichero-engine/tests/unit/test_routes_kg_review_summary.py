"""Tests for review-queue summary API used by UI badge counts (#1356)."""

from fichero.models.knowledge import (
    EntityMatchCandidate,
    PendingMatchState,
)


def test_review_summary_returns_pending_count(client, db):
    pending_a = EntityMatchCandidate(
        survivor_entity_id="survivor-a",
        candidate_entity_id="candidate-a",
        score=0.81,
    )
    pending_b = EntityMatchCandidate(
        survivor_entity_id="survivor-b",
        candidate_entity_id="candidate-b",
        score=0.82,
    )
    accepted = EntityMatchCandidate(
        survivor_entity_id="survivor-c",
        candidate_entity_id="candidate-c",
        score=0.9,
        state=PendingMatchState.accepted,
    )
    db.save(pending_a)
    db.save(pending_b)
    db.save(accepted)

    r = client.get("/api/kg/review/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["pending_count"] == 2
    assert body["has_pending"] is True

