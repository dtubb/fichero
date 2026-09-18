"""kg.merge.repoints-subject (#4859), sibling sweep.

The first #4859 delivery (d5e00d094) fixed `subject_entity_id`. This sweep
generalizes the SAME repointing to the other three scalar entity-id fields
a claim carries: `speaker_entity_id`, `subject_of_inquiry_entity_id`,
`scribe_entity_id`, `editor_entity_id` (checked against the model; there is
no `object_entity_id` to repoint). One test per field for merge, one for
undo, one claim carrying several fields at once, and one proving an audit
written in the OLDER (d5e00d094) `claim_subject_repoints` shape still
undoes through the generalized code.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.models.knowledge import (
    EntityMergeAudit,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)

# Importing the route module registers its @action decorators.
import fichero_server.api.routes.kg.entity_curation  # noqa: F401,E402

ATTRIBUTION_FIELDS = (
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


def _claim_with_field(db, field: str, value: str, subject: KnowledgeEntity) -> KnowledgeClaim:
    """A claim whose SUBJECT is `subject` (so entity_ids also repoints,
    proving the two repoint paths don't interfere) and whose `field` names
    `value` -- some other entity id being merged away."""
    claim = KnowledgeClaim(
        text="Adolfo doy fe.",
        subject_canonical=subject.canonical_name,
        svo_subject=subject.canonical_name,
        predicate_verb="doy fe",
        subject_entity_id=subject.id,
        entity_ids=[subject.id],
        source_document_id="doc-1",
        **{field: value},
    )
    db.save(claim)
    return claim


class TestEachAttributionFieldRepointsOnMerge:
    """kg.merge.repoints-subject, #4859 -- one test per sibling field."""

    @pytest.mark.parametrize("field", ATTRIBUTION_FIELDS)
    def test_field_repoints_on_merge(self, db, field):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        subject = _entity(db, "Adolfo")
        claim = _claim_with_field(db, field, absorbed.id, subject)

        registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert getattr(after, field) == survivor.id
        # Never rewritten: display fields stay exactly as extracted.
        assert after.subject_canonical == "Adolfo"
        assert after.text == "Adolfo doy fe."

    @pytest.mark.parametrize("field", ATTRIBUTION_FIELDS)
    def test_field_untouched_when_it_never_named_an_absorbed_entity(self, db, field):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        subject = _entity(db, "Adolfo")
        someone_else = _entity(db, "Ramirez")
        claim = _claim_with_field(db, field, someone_else.id, subject)

        registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert getattr(after, field) == someone_else.id  # untouched

    @pytest.mark.parametrize("field", ATTRIBUTION_FIELDS)
    def test_undo_restores_the_field_exactly(self, db, field):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        subject = _entity(db, "Adolfo")
        claim = _claim_with_field(db, field, absorbed.id, subject)

        merge_result = registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )
        assert getattr(db.get(KnowledgeClaim, claim.id), field) == survivor.id

        audit = db.get(ActionAudit, merge_result.audit_id)
        reg = registry.get("entity.merge")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        assert getattr(db.get(KnowledgeClaim, claim.id), field) == absorbed.id


class TestClaimCarryingSeveralFieldsAtOnce:
    def test_all_five_fields_repoint_and_undo_together(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        claim = KnowledgeClaim(
            text="Adolfo doy fe.",
            subject_canonical="Adolfo",
            subject_entity_id=absorbed.id,
            speaker_entity_id=absorbed.id,
            subject_of_inquiry_entity_id=absorbed.id,
            scribe_entity_id=absorbed.id,
            editor_entity_id=absorbed.id,
            entity_ids=[absorbed.id],
            source_document_id="doc-1",
        )
        db.save(claim)

        result = registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )
        after = db.get(KnowledgeClaim, claim.id)
        for field in (
            "subject_entity_id",
            "speaker_entity_id",
            "subject_of_inquiry_entity_id",
            "scribe_entity_id",
            "editor_entity_id",
        ):
            assert getattr(after, field) == survivor.id
        assert after.subject_canonical == "Adolfo"  # unchanged

        merge_audit = db.get(EntityMergeAudit, result.result["id"])
        repoints = merge_audit.alias_changes["claim_field_repoints"]
        assert {r["field"] for r in repoints} == {
            "subject_entity_id",
            "speaker_entity_id",
            "subject_of_inquiry_entity_id",
            "scribe_entity_id",
            "editor_entity_id",
        }
        assert all(r["old_entity_id"] == absorbed.id for r in repoints)

        # Undo restores every field.
        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("entity.merge")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        restored = db.get(KnowledgeClaim, claim.id)
        for field in (
            "subject_entity_id",
            "speaker_entity_id",
            "subject_of_inquiry_entity_id",
            "scribe_entity_id",
            "editor_entity_id",
        ):
            assert getattr(restored, field) == absorbed.id


class TestLegacyAuditShapeStillUndoes:
    """An audit written in the OLDER `claim_subject_repoints` shape
    (d5e00d094, before this sweep generalized to `claim_field_repoints`)
    must still undo correctly through the generalized code."""

    def test_d5e00d094_shape_audit_still_undoes(self, db):
        from fichero_server.api.routes.kg.entity_curation import (
            undo_entity_operation_impl,
        )
        from fichero_server.models.knowledge import EntityMergeOperationType

        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        claim = KnowledgeClaim(
            text="Alicia sold the mine.",
            subject_canonical="Alicia",
            subject_entity_id=survivor.id,  # already merged, as if by the old code
            entity_ids=[survivor.id],
            source_document_id="doc-1",
        )
        db.save(claim)
        absorbed.merged_into_id = survivor.id
        db.save(absorbed)

        # A hand-built audit in the EXACT old shape a real d5e00d094-era
        # merge would have written -- no `claim_field_repoints` key at all.
        legacy_audit = EntityMergeAudit(
            operation_type=EntityMergeOperationType.merge,
            source_entity_ids=[absorbed.id],
            target_entity_id=survivor.id,
            alias_changes={
                "added": [],
                "removed": [],
                "moved_to": {},
                "claim_subject_repoints": {claim.id: absorbed.id},
            },
        )
        legacy_audit.reversal_id = legacy_audit.id
        db.save(legacy_audit)

        undo_entity_operation_impl(db, legacy_audit.id)

        restored = db.get(KnowledgeClaim, claim.id)
        assert restored.subject_entity_id == absorbed.id
