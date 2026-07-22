"""Smoke tests for the PyKEEN scaffolding (#377, #899 Phase E).

Heavy: actually trains a tiny model. Marked slow so CI can opt out
when wall-clock matters.
"""

from __future__ import annotations

import pytest

from fichero.kg import pykeen_predictor
from fichero.models.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


class TestGatherTriples:
    def test_extracts_svo_triples_from_claims(self, db):
        ent = KnowledgeEntity(canonical_name="Juan", entity_type=EntityType.person)
        db.save(ent)
        db.save(KnowledgeClaim(
            text="Juan signed the deed.",
            source_document_id="doc-1",
            entity_ids=[ent.id],
            metadata={"verb": "signed", "object": "the deed"},
        ))
        triples = pykeen_predictor._gather_triples(db)
        assert len(triples) == 1
        subj, pred, obj = triples[0]
        assert subj == ent.id
        assert pred == "signed"
        assert obj == "the deed"

    def test_skips_claims_without_object(self, db):
        ent = KnowledgeEntity(canonical_name="Juan", entity_type=EntityType.person)
        db.save(ent)
        db.save(KnowledgeClaim(
            text="Juan exists.",
            source_document_id="doc-1",
            entity_ids=[ent.id],
            metadata={"verb": "exists", "object": ""},
        ))
        triples = pykeen_predictor._gather_triples(db)
        assert len(triples) == 0


class TestTrainModel:
    def test_skips_training_below_minimum_corpus(self, db):
        """Fewer than 10 triples → no training, returns trained=False
        with a reason. Catches the "tried to train on empty library"
        footgun."""
        ent = KnowledgeEntity(canonical_name="Solo", entity_type=EntityType.person)
        db.save(ent)
        for i in range(3):  # < 10
            db.save(KnowledgeClaim(
                text=f"claim {i}",
                source_document_id=f"doc-{i}",
                entity_ids=[ent.id],
                metadata={"verb": "is", "object": f"object {i}"},
            ))
        stats = pykeen_predictor.train_model(db)
        assert stats["trained"] is False
        assert "insufficient" in (stats.get("reason") or "").lower()

    @pytest.mark.slow
    def test_trains_and_persists_with_sufficient_data(self, db, tmp_path):
        """Slow — actually trains a tiny TransE model. Marked slow so
        the default test run can skip it via -m 'not slow'."""
        # Seed enough triples to satisfy the >=10 minimum.
        ents = []
        for i in range(5):
            ent = KnowledgeEntity(
                canonical_name=f"Entity {i}",
                entity_type=EntityType.person,
            )
            db.save(ent)
            ents.append(ent)
        for i, ent in enumerate(ents):
            for j in range(3):
                db.save(KnowledgeClaim(
                    text=f"Claim {i}/{j}",
                    source_document_id=f"doc-{i}-{j}",
                    entity_ids=[ent.id],
                    metadata={"verb": "knows", "object": f"target-{j}"},
                ))
        stats = pykeen_predictor.train_model(
            db, num_epochs=2, embedding_dim=8, batch_size=4
        )
        assert stats["trained"] is True
        assert stats["triples"] >= 10
        assert stats["entities"] > 0
        assert stats["relations"] > 0
