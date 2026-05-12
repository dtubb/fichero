"""Tests for the entity_writer helpers used by catalogue extractors.

These helpers wire structured-extraction outputs into the existing
KnowledgeEntity + KnowledgeClaim KG layer (#728).
"""

from fichero.knowledge_models import (
    EntityType,
    KnowledgeEntity,
    KnowledgeClaim,
    ClaimType,
)


class TestUpsertEntity:
    def test_creates_new_entity_when_absent(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        entity_id = upsert_entity(
            db, canonical_name="María Angel", entity_type=EntityType.person
        )
        loaded = db.get(KnowledgeEntity, entity_id)
        assert loaded is not None
        assert loaded.canonical_name == "María Angel"
        assert loaded.entity_type == EntityType.person

    def test_idempotent_returns_same_id_on_repeat(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        id1 = upsert_entity(
            db, canonical_name="Juan Pérez", entity_type=EntityType.person
        )
        id2 = upsert_entity(
            db, canonical_name="Juan Pérez", entity_type=EntityType.person
        )
        assert id1 == id2
        rows = db.query(
            KnowledgeEntity,
            canonical_name="Juan Pérez",
            entity_type=EntityType.person,
        )
        assert len(rows) == 1

    def test_same_name_different_type_creates_two(self, db):
        # "Lima" the city vs "Lima" the org — different EntityType, separate rows
        from fichero.workflows.tools._entity_writer import upsert_entity

        place_id = upsert_entity(
            db, canonical_name="Lima", entity_type=EntityType.location
        )
        org_id = upsert_entity(
            db, canonical_name="Lima", entity_type=EntityType.organization
        )
        assert place_id != org_id

    def test_aliases_persisted(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        entity_id = upsert_entity(
            db,
            canonical_name="María Angel",
            entity_type=EntityType.person,
            aliases=["M. Angel", "Maria Angel"],
        )
        loaded = db.get(KnowledgeEntity, entity_id)
        assert "M. Angel" in loaded.aliases
        assert "Maria Angel" in loaded.aliases


class TestFuzzyEntityMatch:
    """#897 — cross-page event extraction produces N near-duplicate
    entities for one recurring scene. upsert_entity now fuzzy-matches
    on a fallback path so a rephrased title collapses into the
    existing entity instead of creating a new one."""

    def test_event_rephrasing_collapses_to_one_entity(self, db):
        """The Preface monologue cluster — titles share the same noun
        phrase ("Racial Economic Exclusion") with only the verb
        rephrased (Account / Monologue). These collapse on token-set
        similarity.

        Note: titles that diverge in the core noun phrase (e.g.
        Exclusion → Marginalization) do NOT collapse — pure
        SequenceMatcher can't bridge that semantic gap. Tracked as a
        follow-up at #897 for embedding-based / splink-based
        entity resolution.
        """
        from fichero.workflows.tools._entity_writer import upsert_entity

        first_id = upsert_entity(
            db,
            canonical_name="Narrator's Account of Racial Economic Exclusion",
            entity_type=EntityType.event,
        )
        second_id = upsert_entity(
            db,
            canonical_name="Narrator's Monologue on Racial Economic Exclusion",
            entity_type=EntityType.event,
        )
        assert first_id == second_id, (
            "expected near-identical rephrasings to collapse to one entity"
        )
        # Survivor accumulates the rephrasing as an alias.
        loaded = db.get(KnowledgeEntity, first_id)
        assert "Narrator's Monologue on Racial Economic Exclusion" in (loaded.aliases or [])

    def test_distinct_events_stay_separate(self, db):
        """Two events with low token overlap remain distinct rows."""
        from fichero.workflows.tools._entity_writer import upsert_entity

        a = upsert_entity(
            db, canonical_name="Filing of the Petition", entity_type=EntityType.event
        )
        b = upsert_entity(
            db, canonical_name="Sale of the Estate", entity_type=EntityType.event
        )
        assert a != b

    def test_accent_drift_collapses_for_people(self, db):
        """"Eugenio Córdoba" and "Eugenio Cordoba" (no accent) should
        be one entity — common when one extractor pass drops the accent."""
        from fichero.workflows.tools._entity_writer import upsert_entity

        accented = upsert_entity(
            db, canonical_name="Eugenio Córdoba", entity_type=EntityType.person
        )
        unaccented = upsert_entity(
            db, canonical_name="Eugenio Cordoba", entity_type=EntityType.person
        )
        assert accented == unaccented

    def test_completely_different_names_stay_separate(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        a = upsert_entity(
            db, canonical_name="Juan Pérez", entity_type=EntityType.person
        )
        b = upsert_entity(
            db, canonical_name="Andrés Restrepo", entity_type=EntityType.person
        )
        assert a != b


class TestSaveClaim:
    def test_creates_claim_with_entity_links(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity, save_claim

        entity_id = upsert_entity(
            db, canonical_name="Juan Pérez", entity_type=EntityType.person
        )
        claim_id = save_claim(
            db,
            text="Juan Pérez signed the deed on 1931-08-03",
            source_document_id="doc_test_123",
            entity_ids=[entity_id],
            source_excerpt="...the deed was signed and witnessed...",
        )
        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded is not None
        assert loaded.source_document_id == "doc_test_123"
        assert entity_id in loaded.entity_ids
        assert loaded.claim_type == ClaimType.fact

    def test_save_claim_no_entities_for_dates(self, db):
        from fichero.workflows.tools._entity_writer import save_claim

        # Date claims have no entity_ids — the date IS the claim
        claim_id = save_claim(
            db,
            text="1930-05-12: deed signed by both parties",
            source_document_id="doc_test_456",
            metadata={"date_text": "1930-05-12", "date_normalized": "1930-05-12"},
        )
        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded.entity_ids == []
        assert loaded.metadata.get("date_normalized") == "1930-05-12"
