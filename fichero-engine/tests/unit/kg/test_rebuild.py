"""Tests for the KG backfill / rebuild helper (#899)."""

from __future__ import annotations

from fichero.kg import rebuild
from fichero.models.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


class TestRebuildKg:
    def test_returns_counts_for_empty_library(self, db):
        stats = rebuild.rebuild_kg(db, vectors=False, triples=False)
        assert stats == {
            "entities": 0,
            "claims": 0,
            "entity_vectors_indexed": 0,
            "claim_vectors_indexed": 0,
            "triples_written": 0,
        }

    def test_indexes_existing_entities_into_lancedb(self, db):
        ent = KnowledgeEntity(
            canonical_name="Test Person",
            entity_type=EntityType.person,
            description="appears in the test fixture",
        )
        db.save(ent)
        stats = rebuild.rebuild_kg(db, vectors=True, triples=False)
        assert stats["entities"] == 1
        assert stats["entity_vectors_indexed"] == 1
        assert stats["claim_vectors_indexed"] == 0
        # Confirm it's findable.
        from fichero.kg import entity_vectors
        hits = entity_vectors.find_similar(
            db=db,
            canonical_name="Test Person",
            entity_type=EntityType.person,
            description="appears in the test fixture",
            top_k=1,
        )
        assert hits and hits[0][0] == ent.id

    def test_writes_kg_nt_alongside_duckdb(self, db, tmp_path):
        ent = KnowledgeEntity(
            canonical_name="Davidson",
            entity_type=EntityType.person,
            aliases=["Deibinson"],
        )
        db.save(ent)
        claim = KnowledgeClaim(
            text="Davidson signed the deed.",
            source_document_id="doc-1",
            entity_ids=[ent.id],
            metadata={"verb": "signed", "object": "the deed"},
        )
        db.save(claim)

        out = tmp_path / "kg.nt"
        stats = rebuild.rebuild_kg(
            db, vectors=False, triples=True, triples_path=out
        )
        assert out.exists()
        assert stats["triples_written"] > 0
        text = out.read_text(encoding="utf-8")
        # Spot-check key triples in the N-Triples output.
        assert "Davidson" in text
        assert "signed" in text  # predicate URI carries the slugified verb

    def test_idempotent_rerun(self, db):
        ent = KnowledgeEntity(
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
        )
        db.save(ent)
        rebuild.rebuild_kg(db, vectors=True, triples=False)
        stats2 = rebuild.rebuild_kg(db, vectors=True, triples=False)
        # Vector table contains exactly one row for this id (delete+add).
        from fichero.kg import entity_vectors
        hits = entity_vectors.find_similar(
            db=db,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
            top_k=5,
        )
        # Only one hit for this id even after two backfills.
        ids = [h[0] for h in hits if h[0] == ent.id]
        assert len(ids) == 1
        assert stats2["entity_vectors_indexed"] == 1
        assert stats2["claim_vectors_indexed"] == 0
