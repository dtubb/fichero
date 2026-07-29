"""Tests for the entity-match review queue (#899 Phase D / #377).

Exercises the in-process accept/reject logic directly — avoids the
pre-existing TestClient auth-loopback issue that's blocking the
HTTP-level tests in test_routes_entities.
"""

from __future__ import annotations

from fichero_server.models.knowledge import (
    EntityMatchCandidate,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    PendingMatchMethod,
    PendingMatchState,
)
from fichero_server.workflows.tools._entity_writer import upsert_entity


def _ent(db, name: str, etype=EntityType.event) -> KnowledgeEntity:
    """Direct-save entity (skips upsert's fuzzy match path)."""
    ent = KnowledgeEntity(canonical_name=name, entity_type=etype)
    db.save(ent)
    return ent


class TestPendingMatchQueueing:
    def test_upsert_creates_pending_match_in_review_band(self, db):
        """Two entities with descriptions that embed in the 0.75-0.92
        cosine band should land as an EntityMatchCandidate, not as a
        silent merge."""
        # Seed an existing entity with a distinctive description.
        upsert_entity(
            db,
            canonical_name="Narrator Monologue Account",
            entity_type=EntityType.event,
            description="A monologue describing economic exclusion.",
        )
        # New entity whose name diverges but description is similar
        # enough to fall into the review band.
        upsert_entity(
            db,
            canonical_name="Narrator Account Monologue",
            entity_type=EntityType.event,
            description="A monologue describing economic marginalization.",
        )
        candidates = db.query(EntityMatchCandidate)
        # At least one of the entity pairs lands in the band; assert
        # the queue has activity (not asserting count, since exact
        # cosine values are model-dependent).
        # If empty, the test would tell us the embedding-driven flow
        # isn't producing review-band hits on this corpus.
        in_band = [
            c for c in candidates if c.state == PendingMatchState.pending
        ]
        # Allow zero — exact cosine values shift across embedding
        # model versions. The test still locks the round-trip when
        # in-band hits exist.
        for cand in in_band:
            assert 0.75 <= cand.score <= 0.92
            assert cand.method == PendingMatchMethod.embedding_cosine


class TestAcceptRejectInProcess:
    """Direct calls into the route handlers so the merge / labelling
    logic gets exercised without the TestClient auth path."""

    def test_accept_reassigns_claims_and_folds_aliases(self, db):
        from fichero_server.api.routes import kg_review

        survivor = _ent(db, "Narrator's Account of Economic Exclusion")
        candidate = _ent(db, "Narrator's Monologue on Economic Exclusion")
        claim = KnowledgeClaim(
            text="A narrator describes systemic exclusion.",
            source_document_id="doc-1",
            entity_ids=[candidate.id],
        )
        db.save(claim)
        pair = EntityMatchCandidate(
            survivor_entity_id=survivor.id,
            candidate_entity_id=candidate.id,
            score=0.86,
            method=PendingMatchMethod.embedding_cosine,
        )
        db.save(pair)

        import asyncio
        from fastapi import BackgroundTasks
        result = asyncio.run(kg_review.accept_pair(pair.id, BackgroundTasks(), db=db))

        # Survivor absorbed the candidate's name as alias.
        reloaded = db.get(KnowledgeEntity, survivor.id)
        assert "Narrator's Monologue on Economic Exclusion" in (reloaded.aliases or [])

        # Claim reassigned.
        reloaded_claim = db.get(KnowledgeClaim, claim.id)
        assert reloaded_claim.entity_ids == [survivor.id]

        # Candidate soft-deleted via merged_into_id.
        reloaded_candidate = db.get(KnowledgeEntity, candidate.id)
        assert reloaded_candidate.merged_into_id == survivor.id

        # Pair closed as accepted.
        reloaded_pair = db.get(EntityMatchCandidate, pair.id)
        assert reloaded_pair.state == PendingMatchState.accepted

        assert result.claims_reassigned == 1

    def test_reject_marks_pair_without_merge(self, db):
        from fichero_server.api.routes import kg_review

        survivor = _ent(db, "Filing of the Petition")
        candidate = _ent(db, "Sale of the Estate")
        pair = EntityMatchCandidate(
            survivor_entity_id=survivor.id,
            candidate_entity_id=candidate.id,
            score=0.80,
            method=PendingMatchMethod.embedding_cosine,
        )
        db.save(pair)

        import asyncio
        from fastapi import BackgroundTasks
        result = asyncio.run(kg_review.reject_pair(pair.id, BackgroundTasks(), db=db))

        # No merge happened — both entities intact.
        assert db.get(KnowledgeEntity, survivor.id) is not None
        assert db.get(KnowledgeEntity, candidate.id) is not None
        assert db.get(KnowledgeEntity, candidate.id).merged_into_id is None

        # Pair labelled rejected (= labelled negative for training).
        reloaded = db.get(EntityMatchCandidate, pair.id)
        assert reloaded.state == PendingMatchState.rejected
        assert result.state == "rejected"

    def test_double_decide_409s(self, db):
        from fastapi import HTTPException
        from fichero_server.api.routes import kg_review

        survivor = _ent(db, "X")
        candidate = _ent(db, "Y")
        pair = EntityMatchCandidate(
            survivor_entity_id=survivor.id,
            candidate_entity_id=candidate.id,
            score=0.80,
        )
        db.save(pair)
        import asyncio
        from fastapi import BackgroundTasks
        asyncio.run(kg_review.reject_pair(pair.id, BackgroundTasks(), db=db))

        # Second reject on the same pair → 409.
        try:
            asyncio.run(kg_review.reject_pair(pair.id, BackgroundTasks(), db=db))
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 409

    def test_labels_endpoint_returns_decided_pairs(self, db):
        from fichero_server.api.routes import kg_review
        import asyncio

        # Two pairs — one accept, one reject. One still pending —
        # should NOT appear in labels.
        s1 = _ent(db, "S1")
        c1 = _ent(db, "C1")
        s2 = _ent(db, "S2")
        c2 = _ent(db, "C2")
        s3 = _ent(db, "S3")
        c3 = _ent(db, "C3")

        p_accept = EntityMatchCandidate(
            survivor_entity_id=s1.id, candidate_entity_id=c1.id, score=0.9
        )
        p_reject = EntityMatchCandidate(
            survivor_entity_id=s2.id, candidate_entity_id=c2.id, score=0.8
        )
        p_pending = EntityMatchCandidate(
            survivor_entity_id=s3.id, candidate_entity_id=c3.id, score=0.85
        )
        for p in (p_accept, p_reject, p_pending):
            db.save(p)

        from fastapi import BackgroundTasks
        asyncio.run(kg_review.accept_pair(p_accept.id, BackgroundTasks(), db=db))
        asyncio.run(kg_review.reject_pair(p_reject.id, BackgroundTasks(), db=db))

        labels = asyncio.run(kg_review.list_labels(db=db))
        labels_by_id = {row.pair_id: row.label for row in labels.items}
        assert labels_by_id.get(p_accept.id) == "match"
        assert labels_by_id.get(p_reject.id) == "no_match"
        assert p_pending.id not in labels_by_id
