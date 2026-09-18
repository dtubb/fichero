"""hermeneutic.actor-not-forged (#4857) and hermeneutic.mutations-are-audited
(#4858).

`interpretation.create` is the ONLY forgery risk in `hermeneutics.py`:
`InterpretationCreateRequest.created_by` is a plain client-settable field
that used to be stored verbatim (`hermeneutics.py:392`, before this fix).
No other request model in this file carries a client-supplied actor-like
field (checked against `models/hermeneutics.py`: `InterpretiveFramework`,
`PatternInstance`, `HermeneuticCircleState` have no `created_by`/author
field at all).

Every mutating route in `hermeneutics.py` already calls `registry.invoke(`
in its own body (verified by reading the whole file) -- this suite proves
`hermeneutic.mutations-are-audited`'s missing per-domain coverage: each of
the 11 registered actions (framework create/update/delete, interpretation
create/update, pattern create/update/add_claim, circle_state
create/navigate/backtrack) writes an `ActionAudit` row naming the REAL
actor, driven through `registry.invoke` the same way chat tools / App
Intents / tests do.
"""

from __future__ import annotations

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.models.hermeneutics import (
    CircleNavigationDirection,
    FrameworkType,
    HermeneuticCircleState,
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
    PatternInstance,
    PatternStatus,
)
from fichero_server.models.knowledge import KnowledgeClaim

# Importing the route module registers its @action decorators.
import fichero_server.api.routes.interpretation.hermeneutics  # noqa: F401,E402


def _ctx(actor: str = "alice") -> ActionContext:
    return ActionContext(actor=actor, library_path="/lib/test.fichero")


def _framework(db, fwk_id: str = "fwk-1") -> InterpretiveFramework:
    fwk = InterpretiveFramework(
        id=fwk_id,
        name="Marxist Lens",
        framework_type=FrameworkType.theoretical,
        description="Materialist analysis.",
    )
    db.save(fwk)
    return fwk


def _claim(db, claim_id: str = "claim-1") -> KnowledgeClaim:
    claim = KnowledgeClaim(id=claim_id, text="c", source_document_id="d", entity_ids=[])
    db.save(claim)
    return claim


def _audit(db, audit_id: str) -> ActionAudit:
    row = db.get(ActionAudit, audit_id)
    assert row is not None
    return row


# ===========================================================================
# hermeneutic.actor-not-forged (#4857)
# ===========================================================================


class TestInterpretationActorNotForged:
    def test_forged_created_by_never_reaches_the_stored_row(self, db):
        fwk = _framework(db)
        claim = _claim(db)

        result = registry.invoke(
            db,
            "interpretation.create",
            {
                "framework_id": fwk.id,
                "claim_id": claim.id,
                "interpretation_text": "Class conflict evident.",
                "act": "contextualizing",
                "created_by": "totally-forged-name",
            },
            _ctx(actor="alice"),
        )

        stored = db.get(Interpretation, result.result["id"])
        assert stored.created_by == "alice"
        assert stored.created_by != "totally-forged-name"

    def test_real_actor_recorded_when_client_sends_none(self, db):
        fwk = _framework(db)
        claim = _claim(db)

        result = registry.invoke(
            db,
            "interpretation.create",
            {
                "framework_id": fwk.id,
                "claim_id": claim.id,
                "interpretation_text": "Class conflict evident.",
                "act": "contextualizing",
            },
            _ctx(actor="bob"),
        )
        assert db.get(Interpretation, result.result["id"]).created_by == "bob"


# ===========================================================================
# hermeneutic.mutations-are-audited (#4858) -- one per registered action
# ===========================================================================


class TestEachMutatingActionWritesAnAuditWithTheRealActor:
    def test_framework_create(self, db):
        result = registry.invoke(
            db,
            "framework.create",
            {
                "name": "Postcolonial Theory",
                "framework_type": "theoretical",
                "description": "Examines colonial legacies.",
            },
            _ctx(actor="alice"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "framework.create"
        assert audit.actor == "alice"

    def test_framework_update(self, db):
        fwk = _framework(db)
        result = registry.invoke(
            db,
            "framework.update",
            {"framework_id": fwk.id, "description": "Updated."},
            _ctx(actor="alice"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "framework.update"
        assert audit.actor == "alice"

    def test_framework_delete(self, db):
        fwk = _framework(db)
        result = registry.invoke(
            db, "framework.delete", {"framework_id": fwk.id}, _ctx(actor="alice")
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "framework.delete"
        assert audit.actor == "alice"

    def test_interpretation_create(self, db):
        fwk = _framework(db)
        claim = _claim(db)
        result = registry.invoke(
            db,
            "interpretation.create",
            {
                "framework_id": fwk.id,
                "claim_id": claim.id,
                "interpretation_text": "text",
                "act": "contextualizing",
            },
            _ctx(actor="alice"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "interpretation.create"
        assert audit.actor == "alice"

    def test_interpretation_update(self, db):
        fwk = _framework(db)
        claim = _claim(db)
        created = registry.invoke(
            db,
            "interpretation.create",
            {
                "framework_id": fwk.id,
                "claim_id": claim.id,
                "interpretation_text": "text",
                "act": "contextualizing",
            },
            _ctx(actor="alice"),
        )
        result = registry.invoke(
            db,
            "interpretation.update",
            {
                "interpretation_id": created.result["id"],
                "interpretation_text": "revised",
            },
            _ctx(actor="bob"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "interpretation.update"
        assert audit.actor == "bob"

    def test_pattern_create(self, db):
        result = registry.invoke(
            db,
            "pattern.create",
            {
                "name": "Recurring theme",
                "description": "d",
                "pattern_type": "motif",
                "status": PatternStatus.tentative.value,
            },
            _ctx(actor="alice"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "pattern.create"
        assert audit.actor == "alice"

    def test_pattern_update(self, db):
        created = registry.invoke(
            db,
            "pattern.create",
            {"name": "n", "description": "d", "pattern_type": "motif"},
            _ctx(),
        )
        result = registry.invoke(
            db,
            "pattern.update",
            {"pattern_id": created.result["id"], "description": "revised"},
            _ctx(actor="bob"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "pattern.update"
        assert audit.actor == "bob"

    def test_pattern_add_claim(self, db):
        claim = _claim(db)
        created = registry.invoke(
            db,
            "pattern.create",
            {"name": "n", "description": "d", "pattern_type": "motif"},
            _ctx(),
        )
        result = registry.invoke(
            db,
            "pattern.add_claim",
            {"pattern_id": created.result["id"], "claim_id": claim.id},
            _ctx(actor="alice"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "pattern.add_claim"
        assert audit.actor == "alice"

    def test_circle_state_create(self, db):
        claim = _claim(db)
        result = registry.invoke(
            db,
            "circle_state.create",
            {
                "claim_id": claim.id,
                "current_focus": "part",
                "focus_id": "f1",
                "focus_label": "Focus one",
                "direction": CircleNavigationDirection.part_to_whole.value,
            },
            _ctx(actor="alice"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "circle_state.create"
        assert audit.actor == "alice"

    def test_circle_state_navigate(self, db):
        claim = _claim(db)
        created = registry.invoke(
            db,
            "circle_state.create",
            {
                "claim_id": claim.id,
                "current_focus": "part",
                "focus_id": "f1",
                "focus_label": "Focus one",
                "direction": CircleNavigationDirection.part_to_whole.value,
            },
            _ctx(),
        )
        result = registry.invoke(
            db,
            "circle_state.navigate",
            {
                "state_id": created.result["id"],
                "direction": CircleNavigationDirection.whole_to_part.value,
                "focus_id": "f2",
                "focus_label": "Focus two",
            },
            _ctx(actor="bob"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "circle_state.navigate"
        assert audit.actor == "bob"

    def test_circle_state_backtrack(self, db):
        claim = _claim(db)
        created = registry.invoke(
            db,
            "circle_state.create",
            {
                "claim_id": claim.id,
                "current_focus": "part",
                "focus_id": "f1",
                "focus_label": "Focus one",
                "direction": CircleNavigationDirection.part_to_whole.value,
            },
            _ctx(),
        )
        registry.invoke(
            db,
            "circle_state.navigate",
            {
                "state_id": created.result["id"],
                "direction": CircleNavigationDirection.whole_to_part.value,
                "focus_id": "f2",
                "focus_label": "Focus two",
            },
            _ctx(),
        )
        result = registry.invoke(
            db,
            "circle_state.backtrack",
            {"state_id": created.result["id"]},
            _ctx(actor="alice"),
        )
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "circle_state.backtrack"
        assert audit.actor == "alice"
