"""kg.merge.repoints-subject (#4859).

A merge must repoint a claim's `subject_entity_id`, not only its
`entity_ids` list -- otherwise a claim keeps naming a soft-deleted
(absorbed) entity as its subject after the merge. Both callers of
`merge_entities_impl` are exercised: the `entity.merge` action directly,
and `review.accept` (which now delegates to the same impl, #4831 batch 2).

Ruling (creative director, #4859): `subject_canonical` and `text` are
NEVER rewritten by a merge -- only the resolved `subject_entity_id`
changes. A merge says two records are one entity; it does not rewrite
what the source said.
"""

from __future__ import annotations

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.knowledge.readable import render_entry
from fichero_server.models import ActionAudit
from fichero_server.models.knowledge import (
    EntityMatchCandidate,
    EntityMergeAudit,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    PendingMatchMethod,
)

# Importing the route modules registers their @action decorators.
import fichero_server.api.routes.kg.entity_curation  # noqa: F401,E402
import fichero_server.api.routes.kg.review  # noqa: F401,E402


def _ctx(actor: str = "human") -> ActionContext:
    return ActionContext(actor=actor, library_path="/lib/test.fichero")


def _entity(db, name: str) -> KnowledgeEntity:
    ent = KnowledgeEntity(canonical_name=name, entity_type=EntityType.person)
    db.save(ent)
    return ent


def _subject_claim(db, subject: KnowledgeEntity, extra_entity_ids=()) -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text="Alicia sold the mine.",
        subject_canonical=subject.canonical_name,
        svo_subject=subject.canonical_name,
        predicate_verb="sold",
        object_phrase="the mine",
        subject_entity_id=subject.id,
        entity_ids=[subject.id, *extra_entity_ids],
        source_document_id="doc-1",
    )
    db.save(claim)
    return claim


class TestMergeRepointsSubjectViaEntityMergeAction:
    """kg.merge.repoints-subject, #4859 -- driven through `entity.merge`."""

    def test_merge_repoints_subject_entity_id(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        claim = _subject_claim(db, absorbed)
        before_text, before_subject_canonical = claim.text, claim.subject_canonical

        registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert after.subject_entity_id == survivor.id
        # Ruling: subject_canonical and text are NEVER rewritten by a merge.
        assert after.subject_canonical == before_subject_canonical == "Alicia"
        assert after.text == before_text == "Alicia sold the mine."

    def test_claim_that_is_both_subject_and_mentioned(self, db):
        """entity_ids ALSO contains the absorbed id (the normal write-time
        invariant: subject is always in entity_ids too) -- both fields must
        repoint to the survivor, with no duplicate id left behind."""
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        other = _entity(db, "Bystander")
        claim = _subject_claim(db, absorbed, extra_entity_ids=[other.id])
        assert claim.entity_ids == [absorbed.id, other.id]

        registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert after.subject_entity_id == survivor.id
        assert after.entity_ids == [survivor.id, other.id]

    def test_claim_with_a_different_subject_is_untouched_by_the_merge(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        someone_else = _entity(db, "Bob")
        # entity_ids DOES get repointed (mentioned, not subject) but the
        # subject is Bob throughout -- must never change.
        claim = _subject_claim(db, someone_else, extra_entity_ids=[absorbed.id])

        registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )

        after = db.get(KnowledgeClaim, claim.id)
        assert after.subject_entity_id == someone_else.id  # untouched
        assert survivor.id in after.entity_ids  # entity_ids WAS repointed

    def test_audit_names_the_changed_field(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        claim = _subject_claim(db, absorbed)

        result = registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )
        merge_audit_id = result.result["id"]
        merge_audit = db.get(EntityMergeAudit, merge_audit_id)
        # Generalized (#4859 sibling sweep): the shape is now a list of
        # {claim_id, field, old_entity_id} records, one per repointed field.
        repoints = merge_audit.alias_changes.get("claim_field_repoints")
        assert repoints == [
            {"claim_id": claim.id, "field": "subject_entity_id", "old_entity_id": absorbed.id}
        ]

    def test_unmerge_restores_subject_entity_id_exactly(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        someone_else = _entity(db, "Bob")
        subject_claim = _subject_claim(db, absorbed)
        other_claim = _subject_claim(db, someone_else, extra_entity_ids=[absorbed.id])

        merge_result = registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )
        assert db.get(KnowledgeClaim, subject_claim.id).subject_entity_id == survivor.id

        audit = db.get(ActionAudit, merge_result.audit_id)
        reg = registry.get("entity.merge")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse is not None
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        # The repointed claim's subject is restored exactly.
        assert db.get(KnowledgeClaim, subject_claim.id).subject_entity_id == absorbed.id
        # The claim whose subject was never absorbed stays untouched, even
        # though ITS entity_ids were also repointed by the same merge.
        assert db.get(KnowledgeClaim, other_claim.id).subject_entity_id == someone_else.id

    def test_render_entry_gives_role_subject_on_survivors_page_after_merge(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        claim = _subject_claim(db, absorbed)

        registry.invoke(
            db,
            "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )

        sentences = render_entry(db, survivor.id)
        matching = [s for s in sentences if claim.id in s["claim_ids"]]
        assert len(matching) == 1
        assert matching[0]["role"] == "subject"


class TestMergeRepointsSubjectViaReviewAccept:
    """Same behavior through the OTHER caller of merge_entities_impl,
    review.accept (#4831 batch 2) -- proves the fix through both."""

    def _pair(self, db, survivor, candidate) -> EntityMatchCandidate:
        pair = EntityMatchCandidate(
            survivor_entity_id=survivor.id,
            candidate_entity_id=candidate.id,
            score=0.86,
            method=PendingMatchMethod.embedding_cosine,
        )
        db.save(pair)
        return pair

    def test_accept_repoints_subject_entity_id_too(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        claim = _subject_claim(db, absorbed)
        pair = self._pair(db, survivor, absorbed)

        registry.invoke(db, "review.accept", {"pair_id": pair.id}, _ctx())

        after = db.get(KnowledgeClaim, claim.id)
        assert after.subject_entity_id == survivor.id
        assert after.subject_canonical == "Alicia"  # unchanged, per ruling

    def test_accept_then_unmerge_restores_subject(self, db):
        survivor = _entity(db, "Alice")
        absorbed = _entity(db, "Alicia")
        claim = _subject_claim(db, absorbed)
        pair = self._pair(db, survivor, absorbed)

        result = registry.invoke(db, "review.accept", {"pair_id": pair.id}, _ctx())
        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("review.accept")
        inverse = reg.invert(audit.before, audit.after, _ctx())
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        assert db.get(KnowledgeClaim, claim.id).subject_entity_id == absorbed.id
