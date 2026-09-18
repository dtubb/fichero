"""kg.delete.clears-entity-links (#4863).

A non-cascade `entity.delete` must CLEAR (set to None) every scalar
entity-id field a claim carries that names the deleted entity --
`subject_entity_id` and its three siblings (`speaker_entity_id`,
`subject_of_inquiry_entity_id`, `scribe_entity_id`, `editor_entity_id`) --
not only strip it from `entity_ids`. A deleted entity no longer exists at
all, unlike a merge's absorbed-but-still-alive-as-tombstone entity, so the
correct link value is None, never a dangling dead id.

Ruling (#4863): clear the LINK only. `subject_canonical`, any other
display name, and the claim's sentence (`text`) are NEVER touched -- the
source still said what it said.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity

# Importing the route module registers its @action decorators.
import fichero_server.api.routes.entity.entities  # noqa: F401,E402

CLAIM_ENTITY_ID_FIELDS = (
    "subject_entity_id",
    "speaker_entity_id",
    "subject_of_inquiry_entity_id",
    "scribe_entity_id",
    "editor_entity_id",
)


def _ctx(actor: str = "human") -> ActionContext:
    return ActionContext(actor=actor, library_path="/lib/test.fichero")


def _entity(db, name: str) -> KnowledgeEntity:
    ent = KnowledgeEntity(canonical_name=name, entity_type=EntityType.person)
    db.save(ent)
    return ent


def _claim_with_field(db, field: str, value: str, other_entity_ids=()) -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text="Adolfo doy fe.",
        subject_canonical="Adolfo",
        entity_ids=list(other_entity_ids),
        source_document_id="doc-1",
        **{field: value},
    )
    db.save(claim)
    return claim


class TestEachFieldClearsOnDelete:
    """kg.delete.clears-entity-links, #4863 -- one test per field."""

    @pytest.mark.parametrize("field", CLAIM_ENTITY_ID_FIELDS)
    def test_field_cleared_on_delete(self, db, field):
        deleted = _entity(db, "Alicia")
        claim = _claim_with_field(db, field, deleted.id, other_entity_ids=[deleted.id])

        registry.invoke(
            db, "entity.delete", {"entity_id": deleted.id, "cascade_claims": False}, _ctx()
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert getattr(after, field) is None
        assert deleted.id not in (after.entity_ids or [])

    @pytest.mark.parametrize("field", CLAIM_ENTITY_ID_FIELDS)
    def test_field_naming_a_different_entity_is_untouched(self, db, field):
        deleted = _entity(db, "Alicia")
        someone_else = _entity(db, "Ramirez")
        claim = _claim_with_field(
            db, field, someone_else.id, other_entity_ids=[deleted.id, someone_else.id]
        )

        registry.invoke(
            db, "entity.delete", {"entity_id": deleted.id, "cascade_claims": False}, _ctx()
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert getattr(after, field) == someone_else.id  # untouched
        assert deleted.id not in (after.entity_ids or [])  # entity_ids WAS cleared

    @pytest.mark.parametrize("field", CLAIM_ENTITY_ID_FIELDS)
    def test_undo_restores_the_field_exactly(self, db, field):
        deleted = _entity(db, "Alicia")
        claim = _claim_with_field(db, field, deleted.id, other_entity_ids=[deleted.id])

        result = registry.invoke(
            db, "entity.delete", {"entity_id": deleted.id, "cascade_claims": False}, _ctx()
        )
        assert getattr(db.get(KnowledgeClaim, claim.id), field) is None

        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("entity.delete")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse is not None
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        restored = db.get(KnowledgeClaim, claim.id)
        assert getattr(restored, field) == deleted.id
        assert deleted.id in (restored.entity_ids or [])


class TestClaimCarryingSeveralFieldsAtOnce:
    def test_all_five_fields_cleared_and_restored_together(self, db):
        deleted = _entity(db, "Alicia")
        claim = KnowledgeClaim(
            text="Adolfo doy fe.",
            subject_canonical="Adolfo",
            subject_entity_id=deleted.id,
            speaker_entity_id=deleted.id,
            subject_of_inquiry_entity_id=deleted.id,
            scribe_entity_id=deleted.id,
            editor_entity_id=deleted.id,
            entity_ids=[deleted.id],
            source_document_id="doc-1",
        )
        db.save(claim)

        result = registry.invoke(
            db, "entity.delete", {"entity_id": deleted.id, "cascade_claims": False}, _ctx()
        )
        after = db.get(KnowledgeClaim, claim.id)
        for field in CLAIM_ENTITY_ID_FIELDS:
            assert getattr(after, field) is None
        assert after.entity_ids == []

        audit = db.get(ActionAudit, result.audit_id)
        clears = audit.before["claim_field_clears"]
        assert {c["field"] for c in clears} == set(CLAIM_ENTITY_ID_FIELDS)
        assert all(c["old_entity_id"] == deleted.id for c in clears)

        reg = registry.get("entity.delete")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        restored = db.get(KnowledgeClaim, claim.id)
        for field in CLAIM_ENTITY_ID_FIELDS:
            assert getattr(restored, field) == deleted.id


class TestDisplayFieldsNeverTouched:
    def test_subject_canonical_and_text_unchanged_by_delete(self, db):
        deleted = _entity(db, "Alicia")
        claim = KnowledgeClaim(
            text="Alicia sold the mine.",
            subject_canonical="Alicia",
            subject_entity_id=deleted.id,
            entity_ids=[deleted.id],
            source_document_id="doc-1",
        )
        db.save(claim)

        registry.invoke(
            db, "entity.delete", {"entity_id": deleted.id, "cascade_claims": False}, _ctx()
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert after.subject_entity_id is None
        # The source still said "Alicia" -- never rewritten, even though
        # the link to the (now-deleted) entity is gone.
        assert after.subject_canonical == "Alicia"
        assert after.text == "Alicia sold the mine."
