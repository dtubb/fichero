"""Tests for the review-queue actions (#4831 batch 2): `review.accept`,
`review.reject`, `review.queue`, and their `inclusion.upsert` /
`triangulation.recompute` siblings.

Drives each action via `registry.invoke` (the same path chat tools / App
Intents / `POST /api/actions/invoke` use), per the project test bar
([[would-more-tests-catch-more-issues]]): effect, an ActionAudit row with
the REAL actor (never a hardcoded/forged one, #4843), and undo where the
action declares it.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.models.knowledge import (
    EntityMatchCandidate,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    PendingMatchMethod,
    PendingMatchState,
)

# Importing the route modules registers their @action decorators.
import fichero_server.api.routes.kg.review  # noqa: F401,E402
import fichero_server.api.routes.kg.triangulation  # noqa: F401,E402


def _ctx(actor: str = "human") -> ActionContext:
    return ActionContext(actor=actor, library_path="/lib/test.fichero")


def _ent(db, name: str) -> KnowledgeEntity:
    ent = KnowledgeEntity(canonical_name=name, entity_type=EntityType.event)
    db.save(ent)
    return ent


def _pair(db, survivor, candidate, score=0.86) -> EntityMatchCandidate:
    pair = EntityMatchCandidate(
        survivor_entity_id=survivor.id,
        candidate_entity_id=candidate.id,
        score=score,
        method=PendingMatchMethod.embedding_cosine,
    )
    db.save(pair)
    return pair


class TestReviewAcceptAction:
    def test_effect_audit_real_actor_and_undo(self, db):
        survivor = _ent(db, "Narrator's Account")
        candidate = _ent(db, "Narrator's Monologue")
        claim = KnowledgeClaim(
            text="A claim about the narrator.",
            source_document_id="doc-1",
            entity_ids=[candidate.id],
        )
        db.save(claim)
        pair = _pair(db, survivor, candidate)

        result = registry.invoke(
            db, "review.accept", {"pair_id": pair.id}, _ctx(actor="alice")
        )

        # (a) effect: merge landed, claim reassigned, pair closed
        assert db.get(KnowledgeEntity, candidate.id).merged_into_id == survivor.id
        assert db.get(KnowledgeClaim, claim.id).entity_ids == [survivor.id]
        reloaded_pair = db.get(EntityMatchCandidate, pair.id)
        assert reloaded_pair.state == PendingMatchState.accepted
        assert reloaded_pair.decided_by == "alice"  # never hardcoded "human"

        # (a) audit: the REAL actor, never a hardcoded/forged one (#4843)
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "review.accept"
        assert audit.actor == "alice"
        merge_audit_id = audit.after["entity_merge_audit_id"]
        from fichero_server.models.knowledge import EntityMergeAudit

        merge_audit = db.get(EntityMergeAudit, merge_audit_id)
        assert merge_audit.created_by == "alice"  # the actual actor-forgery fix

        # (b) undo -> entity.unmerge reverses the entity side
        reg = registry.get("review.accept")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse == ("entity.unmerge", {"audit_id": merge_audit_id})
        registry.invoke(db, inverse[0], inverse[1], _ctx(actor="bob"))
        assert db.get(KnowledgeEntity, candidate.id).merged_into_id is None
        # documented scope limit: the pair itself stays "accepted", not
        # reopened to "pending" -- same idiom as undo-of-split not re-merging.
        assert db.get(EntityMatchCandidate, pair.id).state == PendingMatchState.accepted

    def test_unknown_pair_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "review.accept", {"pair_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_already_decided_409(self, db):
        survivor = _ent(db, "S")
        candidate = _ent(db, "C")
        pair = _pair(db, survivor, candidate)
        registry.invoke(db, "review.accept", {"pair_id": pair.id}, _ctx())
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "review.accept", {"pair_id": pair.id}, _ctx())
        assert exc.value.status_code == 409


class TestReviewRejectAction:
    def test_effect_audit_real_actor_and_undo(self, db):
        survivor = _ent(db, "S")
        candidate = _ent(db, "C")
        pair = _pair(db, survivor, candidate, score=0.8)

        result = registry.invoke(
            db, "review.reject", {"pair_id": pair.id}, _ctx(actor="alice")
        )

        reloaded = db.get(EntityMatchCandidate, pair.id)
        assert reloaded.state == PendingMatchState.rejected
        assert reloaded.decided_by == "alice"  # never hardcoded "human"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "review.reject"
        assert audit.actor == "alice"
        assert audit.before["state"] == "pending"

        # (b) undo -> review.restore_pair brings the pair back to pending
        reg = registry.get("review.reject")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse[0] == "review.restore_pair"
        registry.invoke(db, inverse[0], inverse[1], _ctx(actor="bob"))
        restored = db.get(EntityMatchCandidate, pair.id)
        assert restored.state == PendingMatchState.pending
        assert restored.decided_by is None

    def test_unknown_pair_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "review.reject", {"pair_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_already_decided_409(self, db):
        survivor = _ent(db, "S")
        candidate = _ent(db, "C")
        pair = _pair(db, survivor, candidate)
        registry.invoke(db, "review.reject", {"pair_id": pair.id}, _ctx())
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "review.reject", {"pair_id": pair.id}, _ctx())
        assert exc.value.status_code == 409


class TestReviewQueueAction:
    def test_effect_and_audit(self, db):
        survivor = _ent(db, "S")
        candidate = _ent(db, "C")

        result = registry.invoke(
            db,
            "review.queue",
            {
                "survivor_entity_id": survivor.id,
                "candidate_entity_id": candidate.id,
                "reason": "manual suggestion",
            },
            _ctx(actor="alice"),
        )
        pair_id = result.result["id"]
        pair = db.get(EntityMatchCandidate, pair_id)
        assert pair is not None
        assert pair.state == PendingMatchState.pending

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "review.queue"
        assert audit.actor == "alice"

        # Non-undoable, honestly declared.
        assert registry.get("review.queue").undoable is False

    def test_same_entity_twice_400(self, db):
        survivor = _ent(db, "S")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "review.queue",
                {"survivor_entity_id": survivor.id, "candidate_entity_id": survivor.id},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_unknown_entity_404(self, db):
        survivor = _ent(db, "S")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "review.queue",
                {"survivor_entity_id": survivor.id, "candidate_entity_id": "ghost"},
                _ctx(),
            )
        assert exc.value.status_code == 404


class TestTriangulationRecomputeAction:
    def test_effect_and_audit(self, db, monkeypatch):
        monkeypatch.setattr(
            "fichero_server.knowledge.triangulation.persist_support_counts",
            lambda db: 3,
        )
        result = registry.invoke(db, "triangulation.recompute", {}, _ctx(actor="alice"))
        assert result.result["claims_updated"] == 3

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "triangulation.recompute"
        assert audit.actor == "alice"
        assert audit.after == {"claims_updated": 3}

        # Idempotent bulk recompute stays honestly non-undoable.
        assert registry.get("triangulation.recompute").undoable is False
