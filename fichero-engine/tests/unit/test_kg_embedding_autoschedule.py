from __future__ import annotations

from unittest.mock import Mock

from fichero.models.knowledge import ClaimType, EntityType, KnowledgeClaim, KnowledgeEntity


def test_save_autoschedules_entity_embedding(db):
    entity = KnowledgeEntity(
        canonical_name="Marshall",
        entity_type=EntityType.person,
    )
    db.schedule_entity_embedding = Mock()

    db.save(entity)

    db.schedule_entity_embedding.assert_called_once_with(entity)
    assert db.schedule_entity_embedding.call_count == 1


def test_save_autoschedules_claim_embedding(db):
    claim = KnowledgeClaim(
        text="Marshall kept a diary.",
        claim_type=ClaimType.fact,
        source_document_id="doc-1",
    )
    db.schedule_claim_embedding = Mock()

    db.save(claim)

    db.schedule_claim_embedding.assert_called_once_with(claim)
    assert db.schedule_claim_embedding.call_count == 1
