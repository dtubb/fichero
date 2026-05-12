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


class TestEmbeddingMatch:
    """#899 Phase B — sentence-transformer embeddings in LanceDB drive
    the fuzzy-match fallback. Catches semantic divergence in noun
    phrases that pure SequenceMatcher misses.

    These tests need the fastembed model downloaded (~220MB) on the
    first run. Subsequent runs are cache hits.
    """

    def test_new_entity_gets_indexed_in_lancedb(self, db):
        from fichero.kg import entity_vectors
        from fichero.workflows.tools._entity_writer import upsert_entity

        description = "The heirs filed the original mining petition."
        entity_id = upsert_entity(
            db,
            canonical_name="Filing of the Petition",
            entity_type=EntityType.event,
            description=description,
        )
        # Pass the same description on the query — the indexed vector
        # is encoded from name + description, so an exact match on
        # both lands at ~1.0 cosine. Querying with only the name
        # would still be findable (~0.7) but the strict assertion is
        # for the indexing-roundtrip, not partial-text recall.
        hits = entity_vectors.find_similar(
            db=db,
            canonical_name="Filing of the Petition",
            entity_type=EntityType.event,
            description=description,
            top_k=1,
        )
        assert hits, "expected the newly-indexed entity to be findable"
        assert hits[0][0] == entity_id
        assert hits[0][1] > 0.99, "exact text → near-1.0 cosine"

    def test_semantic_divergence_collapses_at_high_cosine(self, db):
        """The #897 follow-up: titles that share the underlying claim
        but diverge in surface noun phrase should still collapse via
        embedding similarity.

        "Narrator's Account of Racial Economic Exclusion" should
        embed close to "Narrator's Monologue on Race and Economic
        Marginalization" — both describe the same conceptual scene.
        """
        from fichero.workflows.tools._entity_writer import upsert_entity

        first_id = upsert_entity(
            db,
            canonical_name="Narrator's Account of Racial Economic Exclusion",
            entity_type=EntityType.event,
            description="A Black narrator describes systemic exclusion from stable employment.",
        )
        second_id = upsert_entity(
            db,
            canonical_name="Narrator's Monologue on Race and Economic Marginalization",
            entity_type=EntityType.event,
            description="A Black narrator describes systemic exclusion from stable employment.",
        )
        # Same description → embedding cosine should be high enough to
        # cross the AUTO_MERGE_THRESHOLD even with divergent titles.
        assert first_id == second_id

    def test_genuinely_distinct_events_stay_separate_under_embeddings(self, db):
        """The dual obligation: don't auto-merge events that are
        actually distinct. "Filing of the Petition" and "Sale of the
        Estate" share no semantic content beyond being events; cosine
        should fall well below the auto-merge threshold."""
        from fichero.workflows.tools._entity_writer import upsert_entity

        a = upsert_entity(
            db,
            canonical_name="Filing of the Petition",
            entity_type=EntityType.event,
            description="The heirs filed a mining petition with the Constitutional Court.",
        )
        b = upsert_entity(
            db,
            canonical_name="Sale of the Estate",
            entity_type=EntityType.event,
            description="The estate was sold at public auction.",
        )
        assert a != b

    def test_vector_refreshes_on_alias_merge(self, db):
        """When upsert_entity folds a new surface form into an existing
        entity, the LanceDB vector should refresh so future matches
        see the latest description. Locks the contract that the
        merge path calls index_entity again."""
        from fichero.kg import entity_vectors
        from fichero.workflows.tools._entity_writer import upsert_entity

        entity_id = upsert_entity(
            db,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
            description="alcalde",
        )
        # Trigger a merge via the SequenceMatcher fallback (no accent).
        merged_id = upsert_entity(
            db,
            canonical_name="Eugenio Cordoba",
            entity_type=EntityType.person,
        )
        assert entity_id == merged_id
        hits = entity_vectors.find_similar(
            db=db,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
            top_k=1,
        )
        assert hits and hits[0][0] == entity_id


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

    def test_within_page_dedup_skips_near_duplicate(self, db):
        """Regression test for the #896 dedup guard: a second
        save_claim call with the same (source_doc, page_label,
        entity_ids) and >=90% text overlap returns the prior claim's
        ID instead of writing a near-duplicate row.
        """
        from fichero.workflows.tools._entity_writer import upsert_entity, save_claim

        entity_id = upsert_entity(
            db, canonical_name="Davidson", entity_type=EntityType.person
        )
        first = save_claim(
            db,
            text="Davidson is an alternative spelling of Deibinson",
            source_document_id="doc_book_42",
            entity_ids=[entity_id],
            source_page_label="Page 1",
        )
        # Re-fire with cosmetic differences only (whitespace + period)
        second = save_claim(
            db,
            text="Davidson is an alternative spelling of Deibinson.",
            source_document_id="doc_book_42",
            entity_ids=[entity_id],
            source_page_label="Page 1",
        )
        assert first == second, "Near-duplicate within the same page should fold"
        # And only one row landed
        rows = db.query(
            KnowledgeClaim,
            source_document_id="doc_book_42",
            source_page_label="Page 1",
        )
        assert len(rows) == 1

    def test_within_page_dedup_does_not_cross_pages(self, db):
        """Same text + same entity on a DIFFERENT page is intentional —
        Davidson can be mentioned on both page 1 and page 2 of the
        same document. The dedup is keyed on page_label so the two
        rows survive.
        """
        from fichero.workflows.tools._entity_writer import upsert_entity, save_claim

        entity_id = upsert_entity(
            db, canonical_name="Davidson", entity_type=EntityType.person
        )
        first = save_claim(
            db,
            text="Davidson signed the deed",
            source_document_id="doc_book_99",
            entity_ids=[entity_id],
            source_page_label="Page 1",
        )
        second = save_claim(
            db,
            text="Davidson signed the deed",
            source_document_id="doc_book_99",
            entity_ids=[entity_id],
            source_page_label="Page 2",
        )
        assert first != second
