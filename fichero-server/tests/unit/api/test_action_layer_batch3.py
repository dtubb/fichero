"""#4831 batch 3: `claim.embed`, `entity.embed`,
`kg.set_external_authority_enabled`, `pykeen.create_review`,
`pykeen.decide_review`.

`audit.every-mutating-route-uses-the-registry`
(docs/contributor_manual/specs/harness/audited-action-layer.md): these five
routes used to bypass the registry entirely -- no `registry.invoke(` call in
their own body, confirmed by the AST guardrail
(`scripts/check_routes_use_action_layer.py`). None of the five carries a
client-supplied actor-like field (checked each request model: `_EmbedClaimRequest`,
`_EmbedEntityRequest`, `ExternalAuthoritySettings`, `KnowledgePredictionReview`,
`PredictionReviewDecision` -- none has a `created_by`/author field), so there
is no forged-actor case to test for this batch; the actor-forgery fix
(`audit.actor-attribution-is-real-not-hardcoded`) is proven separately on
`entity.unmerge`/`entity.split`/`entity.link_authority` in
`test_routes_entity_curation.py` and `test_action_registry.py`.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgePredictionReview,
    PredictionReviewState,
)

# Importing the route modules registers their @action decorators.
import fichero_server.api.routes.kg.claim_search  # noqa: F401,E402
import fichero_server.api.routes.kg.entity_curation  # noqa: F401,E402
import fichero_server.api.routes.kg.pykeen  # noqa: F401,E402


def _ctx(actor: str = "alice") -> ActionContext:
    return ActionContext(actor=actor, library_path="/lib/test.fichero")


class TestClaimEmbedAction:
    def test_effect_and_audit_with_real_actor(self, db, monkeypatch):
        claim = KnowledgeClaim(text="c", source_document_id="d", entity_ids=[])
        db.save(claim)
        monkeypatch.setattr(
            "fichero_server.api.routes.kg.claim_search._embed_claims_sync",
            lambda db, claims: len(claims),
        )

        result = registry.invoke(db, "claim.embed", {}, _ctx(actor="alice"))

        assert result.result["embedded"] == 1
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.embed"
        assert audit.actor == "alice"

    def test_non_undoable_declared_honestly(self, db):
        assert registry.get("claim.embed").undoable is False


class TestEntityEmbedAction:
    def test_effect_and_audit_with_real_actor(self, db, monkeypatch):
        entity = KnowledgeEntity(canonical_name="Alice")
        db.save(entity)
        monkeypatch.setattr(
            "fichero_server.api.routes.kg.entity_curation._embed_entities_sync",
            lambda db, entities: len(entities),
        )

        result = registry.invoke(db, "entity.embed", {}, _ctx(actor="bob"))

        assert result.result["embedded"] == 1
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "entity.embed"
        assert audit.actor == "bob"

    def test_unknown_entity_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "entity.embed", {"entity_ids": ["ghost"]}, _ctx())
        assert exc.value.status_code == 404

    def test_non_undoable_declared_honestly(self, db):
        assert registry.get("entity.embed").undoable is False


class TestSetExternalAuthorityEnabledAction:
    def test_effect_audit_and_undo(self, db):
        result = registry.invoke(
            db, "kg.set_external_authority_enabled",
            {"external_authority_enabled": True}, _ctx(actor="alice"),
        )
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "kg.set_external_authority_enabled"
        assert audit.actor == "alice"
        assert audit.before is None  # first-ever toggle, nothing to restore
        assert audit.after == {"external_authority_enabled": True}

        # Toggle again -- now `before` is populated and undo can replay it.
        result2 = registry.invoke(
            db, "kg.set_external_authority_enabled",
            {"external_authority_enabled": False}, _ctx(actor="bob"),
        )
        audit2 = db.get(ActionAudit, result2.audit_id)
        reg = registry.get("kg.set_external_authority_enabled")
        inverse = reg.invert(audit2.before, audit2.after, _ctx())
        assert inverse is not None
        registry.invoke(db, inverse[0], inverse[1], _ctx(actor="carol"))

        # After undo the setting is back to True (what it was before the
        # second toggle); prove it by reading straight from the DB.
        from fichero_server.models.knowledge import LibrarySetting
        setting = db.get(LibrarySetting, "external_authority_enabled")
        assert setting.value == "true"


class TestPykeenCreateReviewAction:
    def test_effect_and_audit(self, db):
        review = KnowledgePredictionReview(
            source_entity_id="e1", relation="r", target_entity_id="e2", score=0.9,
        )
        result = registry.invoke(
            db, "pykeen.create_review", review.model_dump(mode="json"), _ctx(actor="alice"),
        )
        stored = db.get(KnowledgePredictionReview, result.result["id"])
        assert stored is not None
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "pykeen.create_review"
        assert audit.actor == "alice"

    def test_non_undoable_declared_honestly(self, db):
        assert registry.get("pykeen.create_review").undoable is False


class TestPykeenDecideReviewAction:
    def _review(self, db) -> KnowledgePredictionReview:
        review = KnowledgePredictionReview(
            source_entity_id="e1", relation="r", target_entity_id="e2", score=0.9,
        )
        db.save(review)
        return review

    def test_effect_audit_and_undo(self, db):
        review = self._review(db)

        result = registry.invoke(
            db, "pykeen.decide_review",
            {"review_id": review.id, "state": "accepted"},
            _ctx(actor="alice"),
        )
        updated = db.get(KnowledgePredictionReview, review.id)
        assert updated.state == PredictionReviewState.accepted

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "pykeen.decide_review"
        assert audit.actor == "alice"
        assert audit.before["state"] == "pending"

        reg = registry.get("pykeen.decide_review")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse == ("pykeen.restore_review", {"snapshot": audit.before})
        registry.invoke(db, inverse[0], inverse[1], _ctx(actor="bob"))

        restored = db.get(KnowledgePredictionReview, review.id)
        assert restored.state == PredictionReviewState.pending

    def test_unknown_review_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "pykeen.decide_review",
                {"review_id": "ghost", "state": "accepted"}, _ctx(),
            )
        assert exc.value.status_code == 404
