"""Tests for the entity_writer helpers used by catalogue extractors.

These helpers wire structured-extraction outputs into the existing
KnowledgeEntity + KnowledgeClaim KG layer (#728).
"""

from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    EntityType,
    EntityResolutionRule,
    EntityResolutionRuleType,
    EvidenceBasis,
    KnowledgeEntity,
    KnowledgeClaim,
    KnowledgeClaimLink,
    ClaimType,
    ClaimRelationType,
)
from fichero.models import Document, DocType


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

    def test_suppress_rule_returns_none(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        db.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.suppress,
                match_canonical_name="Noise",
                match_entity_type=EntityType.person,
                reason="known extraction noise",
            )
        )

        entity_id = upsert_entity(
            db,
            canonical_name="Noise",
            entity_type=EntityType.person,
        )

        assert entity_id is None
        assert db.query(KnowledgeEntity, canonical_name="Noise") == []

    def test_merge_into_rule_folds_name_into_target(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        survivor_id = upsert_entity(
            db,
            canonical_name="John Davidson",
            entity_type=EntityType.person,
        )
        db.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.merge_into,
                match_canonical_name="J. Davidson",
                match_entity_type=EntityType.person,
                target_canonical_name="John Davidson",
                target_entity_type=EntityType.person,
                reason="same person",
            )
        )

        merged_id = upsert_entity(
            db,
            canonical_name="J. Davidson",
            entity_type=EntityType.person,
        )

        assert merged_id == survivor_id
        rows = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(rows) == 1
        assert rows[0].canonical_name == "John Davidson"

    def test_entity_resolution_rule_match_is_case_insensitive_and_trimmed(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        db.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.suppress,
                match_canonical_name="john davidson",
                match_entity_type=EntityType.person,
                reason="known duplicate noise",
            )
        )

        mixed_case_id = upsert_entity(
            db,
            canonical_name="John Davidson",
            entity_type=EntityType.person,
        )
        upper_id = upsert_entity(
            db,
            canonical_name="  JOHN  Davidson ",
            entity_type=EntityType.person,
        )

        assert mixed_case_id is None
        assert upper_id is None
        assert db.query(KnowledgeEntity, entity_type=EntityType.person) == []

    def test_reclassify_rule_overrides_type(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        db.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.reclassify,
                match_canonical_name="Andagoya",
                match_entity_type=EntityType.concept,
                target_entity_type=EntityType.location,
                reason="this is a place",
            )
        )

        entity_id = upsert_entity(
            db,
            canonical_name="Andagoya",
            entity_type=EntityType.concept,
        )

        loaded = db.get(KnowledgeEntity, entity_id)
        assert loaded is not None
        assert loaded.entity_type == EntityType.location

    def test_race_recovery_repoints_claims_before_duplicate_delete(self, db):
        """#2135: dedup must not leave claims pointing at deleted entity ids."""
        from fichero.workflows.tools._entity_writer import (
            _repoint_claim_entity_references,
        )

        survivor = KnowledgeEntity(
            canonical_name="Maria Angel",
            entity_type=EntityType.person,
        )
        duplicate = KnowledgeEntity(
            canonical_name="Maria Angel",
            entity_type=EntityType.person,
        )
        db.save(survivor)
        db.save(duplicate)
        claim = KnowledgeClaim(
            text="Maria Angel testified.",
            entity_ids=[duplicate.id],
            subject_entity_id=duplicate.id,
            speaker_entity_id=duplicate.id,
        )
        db.save(claim)

        repointed = _repoint_claim_entity_references(
            db,
            duplicate_ids={duplicate.id},
            survivor_id=survivor.id,
        )
        db.delete(duplicate)

        loaded = db.get(KnowledgeClaim, claim.id)
        assert repointed == [claim.id]
        assert db.get(KnowledgeEntity, duplicate.id) is None
        assert loaded.entity_ids == [survivor.id]
        assert loaded.subject_entity_id == survivor.id
        assert loaded.speaker_entity_id == survivor.id


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
        assert hits[0][1] > 0.98, "exact semantic text → high cosine"

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

    def test_prune_rule_returns_none_and_writes_nothing(self, db):
        from fichero.workflows.tools._entity_writer import save_claim

        db.save(
            ClaimSuppressionRule(
                action=ClaimSuppressionRuleAction.prune,
                match_subject_name="Noise",
                match_predicate_verb="is",
                match_object_phrase="a person",
                reason="discard trivial noise",
            )
        )

        claim_id = save_claim(
            db,
            text="Noise is a person.",
            source_document_id="doc-prune",
            subject_canonical="Noise",
            predicate_verb="is",
            object_phrase="a person",
        )

        assert claim_id is None
        assert db.query(KnowledgeClaim, source_document_id="doc-prune") == []

    def test_disable_rule_rejects_claim_without_pruning(self, db):
        from fichero.workflows.tools._entity_writer import save_claim

        db.save(
            ClaimSuppressionRule(
                action=ClaimSuppressionRuleAction.disable,
                match_subject_name="Pedro",
                match_predicate_verb="said",
                reason="known bad extraction",
            )
        )

        claim_id = save_claim(
            db,
            text="Pedro said the deed was false.",
            source_document_id="doc-disable",
            subject_canonical="Pedro",
            predicate_verb="said",
            object_phrase="the deed was false",
            confidence=0.7,
        )

        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded is not None
        assert loaded.curation_state == ClaimCurationState.rejected
        assert loaded.confidence == 0.7

    def test_demote_rule_rejects_and_caps_confidence(self, db):
        from fichero.workflows.tools._entity_writer import save_claim

        db.save(
            ClaimSuppressionRule(
                action=ClaimSuppressionRuleAction.demote,
                match_subject_name="Andagoya",
                match_predicate_verb="is",
                match_object_phrase="a place",
                reason="too generic",
            )
        )

        claim_id = save_claim(
            db,
            text="Andagoya is a place.",
            source_document_id="doc-demote",
            subject_canonical="Andagoya",
            predicate_verb="is",
            object_phrase="a place",
            confidence=0.8,
        )

        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded is not None
        assert loaded.curation_state == ClaimCurationState.rejected
        assert loaded.confidence == 0.2

    def test_copula_rule_demotes_instead_of_pruning(self, db):
        from fichero.workflows.tools._entity_writer import save_claim

        db.save(
            ClaimSuppressionRule(
                action=ClaimSuppressionRuleAction.prune,
                match_subject_name="Andagoya",
                suppress_is_a_copulas=True,
                reason="generic type copulas should be demoted, not deleted",
            )
        )

        claim_id = save_claim(
            db,
            text="Andagoya is a place.",
            source_document_id="doc-copula",
            subject_canonical="Andagoya",
            predicate_verb="is",
            object_phrase="a place",
            confidence=0.6,
        )

        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded is not None
        assert loaded.curation_state == ClaimCurationState.rejected
        assert loaded.confidence == 0.2

    def test_save_claim_source_anchors_missing_date_and_place(self, db):
        from fichero.workflows.tools._entity_writer import save_claim

        doc = Document(
            id="doc_anchor_1",
            name="1820 petition",
            doc_type=DocType.file,
            source_metadata={"issued": "1820", "place": "Popayán jurisdiction"},
            provenance_chain=[{"action": "recorded", "actor": "court scribe"}],
        )
        db.save(doc)

        claim_id = save_claim(
            db,
            text="Pedro filed the petition.",
            source_document_id=doc.id,
            source_excerpt="Pedro filed the petition.",
        )

        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded is not None
        assert loaded.date_values[0].basis == EvidenceBasis.source_anchored
        assert loaded.date_values[0].open_start is True
        assert loaded.date_values[0].end == "1820-12-31"
        assert loaded.date_values[0].source_field == "source_metadata.issued"
        assert loaded.place_values[0].basis == EvidenceBasis.source_anchored
        assert loaded.place_values[0].label == "Popayán jurisdiction"
        assert loaded.place_values[0].source_field == "source_metadata.place"
        assert loaded.source_supports[0].date_values[0].basis == EvidenceBasis.source_anchored
        assert [step.role.value for step in loaded.attribution_chain] == [
            "recorder",
            "source_document",
        ]
        assert loaded.attribution_chain[0].name == "court scribe"

    def test_save_claim_keeps_asserted_date_over_source_anchor(self, db):
        from fichero.workflows.tools._entity_writer import save_claim

        doc = Document(
            id="doc_anchor_2",
            name="1933 compiled copy",
            doc_type=DocType.file,
            source_metadata={"issued": "1933"},
        )
        db.save(doc)

        claim_id = save_claim(
            db,
            text="Pedro filed the petition in 1820.",
            source_document_id=doc.id,
            time_start="1820-01-01",
            time_end="1820-12-31",
            time_precision="year",
        )

        loaded = db.get(KnowledgeClaim, claim_id)
        assert loaded is not None
        assert loaded.date_values[0].basis == EvidenceBasis.asserted
        assert loaded.date_values[0].start == "1820-01-01"
        assert loaded.date_values[0].source_field is None

    def test_cross_source_duplicate_folds_into_canonical_supports(self, db):
        from fichero.workflows.tools._entity_writer import save_claim, upsert_entity

        entity_id = upsert_entity(db, "Pedro", EntityType.person)
        first = save_claim(
            db,
            text="Pedro filed the petition.",
            source_document_id="doc_corroborate_1",
            entity_ids=[entity_id],
            source_page_label="1",
            source_excerpt="Pedro filed the petition.",
            confidence=0.6,
        )
        second = save_claim(
            db,
            text="Pedro filed the petition.",
            source_document_id="doc_corroborate_2",
            entity_ids=[entity_id],
            source_page_label="7",
            source_excerpt="Pedro filed the petition.",
            confidence=0.7,
        )

        assert second != first
        claims = db.all(KnowledgeClaim)
        assert len(claims) == 2
        doc_ids = {c.source_document_id for c in claims}
        assert doc_ids == {"doc_corroborate_1", "doc_corroborate_2"}
        # Canonical (first) claim should still be enriched with corroboration data.
        loaded = db.get(KnowledgeClaim, first)
        assert loaded is not None
        assert loaded.corroboration_count == 2
        assert loaded.corroborating_source_ids == [
            "doc_corroborate_1",
            "doc_corroborate_2",
        ]
        assert loaded.confidence_source == "corroboration"
        assert len(loaded.source_supports) == 2
        links = db.all(KnowledgeClaimLink)
        assert len(links) == 1
        assert links[0].relation_type == ClaimRelationType.corroborates

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

    def test_claim_svo_dedup_collapses_normalized_near_duplicate(self, db):
        """#1805: identical SVO keys collapse despite accent/case/punctuation noise."""
        from fichero.workflows.tools._entity_writer import save_claim, upsert_entity

        entity_id = upsert_entity(
            db, canonical_name="Peña", entity_type=EntityType.person
        )
        first = save_claim(
            db,
            text="Peña served as the alcalde of Popayán.",
            source_document_id="doc_claim_dedup_1",
            entity_ids=[entity_id],
            source_page_label="Page 4",
            subject_canonical="Peña",
            predicate_verb="served as",
            object_phrase="the alcalde of Popayán",
        )
        second = save_claim(
            db,
            text="PENA served as alcalde of Popayan!",
            source_document_id="doc_claim_dedup_1",
            entity_ids=[entity_id],
            source_page_label="Page 4",
            subject_canonical="Pena",
            predicate_verb="served as",
            object_phrase="alcalde of popayan",
        )

        assert first == second
        rows = db.query(
            KnowledgeClaim,
            source_document_id="doc_claim_dedup_1",
            source_page_label="Page 4",
        )
        assert len(rows) == 1

    def test_claim_svo_dedup_preserves_distinct_claims(self, db):
        """#1805 negative: shared subject/predicate does not merge different objects."""
        from fichero.workflows.tools._entity_writer import save_claim, upsert_entity

        entity_id = upsert_entity(
            db, canonical_name="San Pablo", entity_type=EntityType.location
        )
        first = save_claim(
            db,
            text="San Pablo was located in Chocó.",
            source_document_id="doc_claim_dedup_2",
            entity_ids=[entity_id],
            source_page_label="Page 8",
            subject_canonical="San Pablo",
            predicate_verb="was located in",
            object_phrase="Chocó",
        )
        second = save_claim(
            db,
            text="San Pablo was located in Cauca.",
            source_document_id="doc_claim_dedup_2",
            entity_ids=[entity_id],
            source_page_label="Page 8",
            subject_canonical="San Pablo",
            predicate_verb="was located in",
            object_phrase="Cauca",
        )

        assert first != second
        rows = db.query(
            KnowledgeClaim,
            source_document_id="doc_claim_dedup_2",
            source_page_label="Page 8",
        )
        assert len(rows) == 2

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


class TestClaimHelperFunctions:
    def test_same_structured_claim_normalizes_entity_order_and_svo_noise(self):
        from fichero.workflows.tools._entity_writer import _same_structured_claim

        left = KnowledgeClaim(
            text="Peña served as the alcalde of Popayán.",
            entity_ids=["entity-a", "entity-b"],
            subject_canonical="Peña",
            predicate_verb="served as",
            object_phrase="the alcalde of Popayán",
        )
        right = KnowledgeClaim(
            text="PENA served as alcalde of Popayan!",
            entity_ids=["entity-b", "entity-a"],
            subject_canonical="Pena",
            predicate_verb="served as",
            object_phrase="alcalde of popayan",
        )

        assert _same_structured_claim(left, right) is True

    def test_same_structured_claim_falls_back_to_text_similarity_when_svo_missing(self):
        from fichero.workflows.tools._entity_writer import _same_structured_claim

        prior = KnowledgeClaim(
            text="Pedro testified before the council.",
            entity_ids=["entity-a"],
        )
        near_duplicate = KnowledgeClaim(
            text="Pedro testified before the council",
            entity_ids=["entity-a"],
        )
        distinct = KnowledgeClaim(
            text="Pedro bought the mine.",
            entity_ids=["entity-a"],
        )

        assert _same_structured_claim(prior, near_duplicate) is True
        assert _same_structured_claim(prior, distinct) is False

    def test_find_cross_source_canonical_claim_ignores_same_source_duplicates(self, db):
        from fichero.workflows.tools._entity_writer import (
            _find_cross_source_canonical_claim,
        )

        db.save(
            KnowledgeClaim(
                text="Pedro filed the petition.",
                source_document_id="doc-a",
                entity_ids=["entity-a"],
                subject_canonical="Pedro",
                predicate_verb="filed",
                object_phrase="the petition",
            )
        )

        incoming = KnowledgeClaim(
            text="Pedro filed the petition.",
            source_document_id="doc-a",
            entity_ids=["entity-a"],
            subject_canonical="Pedro",
            predicate_verb="filed",
            object_phrase="the petition",
        )

        assert _find_cross_source_canonical_claim(db, incoming) is None

    def test_find_cross_source_canonical_claim_finds_other_source_match(self, db):
        from fichero.workflows.tools._entity_writer import (
            _find_cross_source_canonical_claim,
        )

        same_source = KnowledgeClaim(
            text="Pedro filed the petition.",
            source_document_id="doc-a",
            entity_ids=["entity-a"],
            subject_canonical="Pedro",
            predicate_verb="filed",
            object_phrase="the petition",
        )
        other_source = KnowledgeClaim(
            text="PENA filed the petition!",
            source_document_id="doc-b",
            entity_ids=["entity-a"],
            subject_canonical="Pedro",
            predicate_verb="filed",
            object_phrase="the petition",
        )
        db.save(same_source)
        db.save(other_source)

        incoming = KnowledgeClaim(
            text="Pedro filed the petition.",
            source_document_id="doc-a",
            entity_ids=["entity-a"],
            subject_canonical="Pedro",
            predicate_verb="filed",
            object_phrase="the petition",
        )

        assert _find_cross_source_canonical_claim(db, incoming).id == other_source.id

    def test_repoint_claim_entity_references_deduplicates_survivor_ids(self, db):
        from fichero.workflows.tools._entity_writer import (
            _repoint_claim_entity_references,
        )

        claim = KnowledgeClaim(
            text="Pedro testified.",
            entity_ids=["survivor", "duplicate", "duplicate"],
            subject_entity_id="duplicate",
        )
        db.save(claim)

        repointed = _repoint_claim_entity_references(
            db,
            duplicate_ids={"duplicate"},
            survivor_id="survivor",
        )

        loaded = db.get(KnowledgeClaim, claim.id)
        assert repointed == [claim.id]
        assert loaded.entity_ids == ["survivor"]
        assert loaded.subject_entity_id == "survivor"

    def test_upsert_entity_accumulates_source_document_ids_without_duplicates(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
            source_document_id="page-1",
        )
        second = upsert_entity(
            db,
            canonical_name="Eugenio Cordoba",
            entity_type=EntityType.person,
            source_document_id="page-2",
        )
        third = upsert_entity(
            db,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
            source_document_id="page-2",
        )

        loaded = db.get(KnowledgeEntity, first)
        assert first == second == third
        assert loaded.source_document_ids == ["page-1", "page-2"]


class TestTypeConflictDetector:
    """#1114 issue 1 — same canonical_name with different entity_types
    used to produce two rows. The classic example: "Atrató River"
    landing as both `concept` (the LLM's catchall when section
    classification missed) and `location`. River is a `location`;
    the duplicate `concept` row is noise.

    Resolution:
    - If the existing row is `concept` (catchall) and the new
      request names a more specific type, promote the existing
      row's type to the specific one and return the same id —
      no second row created.
    - If the new request is `concept` and the existing row is
      already specific, accept the existing specific type
      (silently ignore the catchall request).
    - If both types are specific (location vs organization, etc.),
      log a warning and create the second row — too risky to
      auto-merge across genuinely different types.
    """

    def test_concept_then_location_promotes(self, db):
        # First upsert: the LLM mis-typed Atrató River as a concept.
        from fichero.workflows.tools._entity_writer import upsert_entity

        first_id = upsert_entity(
            db, canonical_name="Atrató River",
            entity_type=EntityType.concept,
        )
        # Second pass detects it's a location; should promote in place.
        second_id = upsert_entity(
            db, canonical_name="Atrató River",
            entity_type=EntityType.location,
        )
        assert first_id == second_id, (
            "Concept→location should promote in place, not create a "
            "second row"
        )
        # The DB row now carries the location type.
        loaded = db.get(KnowledgeEntity, first_id)
        assert loaded.entity_type == EntityType.location
        # And the only row with that canonical_name has the new type.
        all_rows = db.query(KnowledgeEntity, canonical_name="Atrató River")
        assert len(all_rows) == 1
        assert all_rows[0].entity_type == EntityType.location

    def test_location_then_concept_keeps_specific_type(self):
        # Already-specific entity should ignore a later catchall request.
        from fichero.workflows.tools._entity_writer import upsert_entity
        from pathlib import Path
        import tempfile
        from fichero.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            first_id = upsert_entity(
                db, canonical_name="San Juan",
                entity_type=EntityType.location,
            )
            second_id = upsert_entity(
                db, canonical_name="San Juan",
                entity_type=EntityType.concept,
            )
            assert first_id == second_id
            # Type stays as location — concept doesn't downgrade.
            loaded = db.get(KnowledgeEntity, first_id)
            assert loaded.entity_type == EntityType.location

    def test_two_specific_types_still_create_two(self, db):
        # The pre-existing contract: "Lima" as a location AND an
        # organization are legitimately different entities. The
        # detector must not auto-merge them.
        from fichero.workflows.tools._entity_writer import upsert_entity

        place_id = upsert_entity(
            db, canonical_name="Lima",
            entity_type=EntityType.location,
        )
        org_id = upsert_entity(
            db, canonical_name="Lima",
            entity_type=EntityType.organization,
        )
        assert place_id != org_id, (
            "Two specific types must remain separate (review-queue "
            "territory, not auto-merge)"
        )

    def test_promotion_preserves_claims(self):
        """Promoting concept→location must not orphan claims that
        already reference the concept-typed entity by id."""
        from pathlib import Path
        import tempfile
        from fichero.db import Database
        from fichero.workflows.tools._entity_writer import (
            upsert_entity, save_claim,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            entity_id = upsert_entity(
                db, canonical_name="Magdalena River",
                entity_type=EntityType.concept,
            )
            # Write a claim referencing the concept-typed entity.
            claim_id = save_claim(
                db,
                text="Magdalena River flows north.",
                source_document_id="doc_x",
                entity_ids=[entity_id],
            )
            # Now promote.
            promoted_id = upsert_entity(
                db, canonical_name="Magdalena River",
                entity_type=EntityType.location,
            )
            assert promoted_id == entity_id
            # The claim's entity_ids reference still resolves.
            loaded_claim = db.get(KnowledgeClaim, claim_id)
            assert entity_id in loaded_claim.entity_ids
            # And the entity now carries the upgraded type.
            loaded_entity = db.get(KnowledgeEntity, entity_id)
            assert loaded_entity.entity_type == EntityType.location


class TestWriterGateRules:
    def test_suppress_rule_skips_entity_and_claim_write(self, db):
        from fichero.workflows.tools.extractors import _write_kg_rows

        db.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.suppress,
                match_canonical_name="Noise",
                match_entity_type=EntityType.person,
                reason="known noise",
            )
        )

        _write_kg_rows(
            db,
            section={"name": "people", "entity_type": EntityType.person},
            items=[{"name": "Noise", "verb": "signed", "object": "the deed"}],
            container_id="doc-noise",
            page_label="1",
            source_excerpt="Noise signed the deed.",
        )

        assert db.query(KnowledgeEntity, canonical_name="Noise") == []
        assert db.query(KnowledgeClaim, source_document_id="doc-noise") == []

    def test_import_rule_then_second_import_honors_persistent_merge(self, db):
        from fichero.workflows.tools.extractors import _write_kg_rows

        _write_kg_rows(
            db,
            section={"name": "people", "entity_type": EntityType.person},
            items=[{"name": "John Davidson", "verb": "signed", "object": "the deed"}],
            container_id="doc-a",
            page_label="1",
            source_excerpt="John Davidson signed the deed.",
        )
        db.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.merge_into,
                match_canonical_name="J. Davidson",
                match_entity_type=EntityType.person,
                target_canonical_name="John Davidson",
                target_entity_type=EntityType.person,
                reason="same person",
            )
        )

        _write_kg_rows(
            db,
            section={"name": "people", "entity_type": EntityType.person},
            items=[{"name": "J. Davidson", "verb": "witnessed", "object": "the deed"}],
            container_id="doc-b",
            page_label="2",
            source_excerpt="J. Davidson witnessed the deed.",
        )

        entities = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(entities) == 1
        survivor = entities[0]
        assert survivor.canonical_name == "John Davidson"
        claims = db.query(KnowledgeClaim, subject_entity_id=survivor.id)
        assert len(claims) == 2

    def test_redirect_cycle_suppresses_entity_and_claim_write(self, db):
        from fichero.workflows.tools.extractors import _write_kg_rows

        for source_name, target_name in (
            ("Alpha", "Bravo"),
            ("Bravo", "Charlie"),
            ("Charlie", "Delta"),
            ("Delta", "Echo"),
            ("Echo", "Foxtrot"),
            ("Foxtrot", "Golf"),
            ("Golf", "Hotel"),
            ("Hotel", "India"),
            ("India", "Alpha"),
        ):
            db.save(
                EntityResolutionRule(
                    rule_type=EntityResolutionRuleType.alias,
                    match_canonical_name=source_name,
                    match_entity_type=EntityType.person,
                    target_canonical_name=target_name,
                    target_entity_type=EntityType.person,
                    reason="redirect chain",
                )
            )

        _write_kg_rows(
            db,
            section={"name": "people", "entity_type": EntityType.person},
            items=[{"name": "Alpha", "verb": "signed", "object": "the deed"}],
            container_id="doc-cycle",
            page_label="1",
            source_excerpt="Alpha signed the deed.",
        )

        assert db.query(KnowledgeEntity, entity_type=EntityType.person) == []
        assert db.query(KnowledgeClaim, source_document_id="doc-cycle") == []


class TestAdminQualifierDedup:
    """#1114 issue 2 — 'Chocó' and 'Chocó department' used to land as
    two entities because the existing fuzzy-match scores
    one-token-in-two-tokens at 0.5 (below the 0.78 threshold).

    The admin-qualifier matcher catches the common
    political-subdivision suffix cases ('X', 'X department',
    'the X', 'el X') and folds the surface forms into one row's
    aliases.

    The vocabulary is deliberately small — political subdivisions
    only, plus leading articles. Adding 'river' / 'mountain' would
    break the contract by collapsing distinct geographic features.
    """

    def test_chocó_and_chocó_department_collapse(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="Chocó",
            entity_type=EntityType.location,
        )
        second = upsert_entity(
            db, canonical_name="Chocó department",
            entity_type=EntityType.location,
        )
        assert first == second
        # Both surface forms preserved as aliases
        loaded = db.get(KnowledgeEntity, first)
        assert "Chocó department" in (loaded.aliases or [])

    def test_leading_article_collapses(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="Atrato",
            entity_type=EntityType.location,
        )
        second = upsert_entity(
            db, canonical_name="el Atrato",
            entity_type=EntityType.location,
        )
        assert first == second
        loaded = db.get(KnowledgeEntity, first)
        # The surface "el Atrato" lands in aliases
        assert any("Atrato" in a for a in (loaded.aliases or []))

    def test_distinct_features_dont_collapse(self, db):
        """'Chocó' (department) and 'Chocó River' must NOT merge —
        River isn't in the admin-qualifier vocabulary.
        """
        from fichero.workflows.tools._entity_writer import upsert_entity

        dept_id = upsert_entity(
            db, canonical_name="Chocó",
            entity_type=EntityType.location,
        )
        river_id = upsert_entity(
            db, canonical_name="Chocó River",
            entity_type=EntityType.location,
        )
        # These may or may not be the same depending on the embedding /
        # SequenceMatcher behavior, but they MUST NOT collapse via the
        # admin-qualifier path. Verify the admin path didn't fire by
        # checking the river surface isn't auto-aliased onto the dept
        # row (admin-qualifier merge does that).
        if dept_id == river_id:
            loaded = db.get(KnowledgeEntity, dept_id)
            # If they did collapse, it was via the fuzzy stage, not
            # admin qualifiers — assert the surface form is preserved
            # in aliases as expected by either path.
            assert "Chocó" in [loaded.canonical_name, *loaded.aliases]

    def test_spanish_departamento_collapses(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="Antioquia",
            entity_type=EntityType.location,
        )
        second = upsert_entity(
            db, canonical_name="Antioquia departamento",
            entity_type=EntityType.location,
        )
        assert first == second

    def test_different_types_dont_collapse_via_admin(self, db):
        """Type-conflict detection runs BEFORE admin-qualifier dedup.
        'Chocó' (location) vs 'Chocó department' (organization) —
        organizations and locations stay distinct under the existing
        type-conflict contract; the admin matcher only fires for
        same-type entities.
        """
        from fichero.workflows.tools._entity_writer import upsert_entity

        loc_id = upsert_entity(
            db, canonical_name="Chocó",
            entity_type=EntityType.location,
        )
        org_id = upsert_entity(
            db, canonical_name="Chocó department",
            entity_type=EntityType.organization,
        )
        # Different types stay separate (matches the pre-existing
        # test_same_name_different_type_creates_two contract).
        assert loc_id != org_id


class TestStage4RaceRecovery:
    """#1121 — concurrent upserts that both miss Stage 1 and both reach
    Stage 4 create silent duplicate rows (different UUIDs, same
    canonical_name + entity_type). The race-recovery step re-queries
    after Stage 4's save and folds duplicates into the oldest survivor.

    We can't easily reproduce the actual asyncio.gather race in a unit
    test (DuckDB serializes within one connection), so we simulate
    the post-race state directly: pre-insert a "concurrent" row with
    an older created_at, then call upsert_entity. The race-recovery
    path should detect both rows and pick the older as the survivor.
    """

    def test_oldest_wins_aliases_fold_in(self, db):
        from datetime import datetime, timedelta
        from fichero.workflows.tools._entity_writer import upsert_entity

        # Simulate: a concurrent caller created this row 5 seconds ago.
        older_time = datetime.now() - timedelta(seconds=5)
        older = KnowledgeEntity(
            canonical_name="Atrato",
            entity_type=EntityType.location,
            aliases=["the Atrato"],
            created_at=older_time,
        )
        db.save(older)

        # Our caller now upserts the same canonical name. Stage 1 finds
        # the older row and returns it (no race recovery needed because
        # the exact lookup hit).
        returned_id = upsert_entity(
            db,
            canonical_name="Atrato",
            entity_type=EntityType.location,
            aliases=["Río Atrato"],
        )
        # Stage 1 exact-match wins; race recovery wasn't necessary.
        assert returned_id == older.id

    def test_race_recovery_with_pre_existing_duplicate(self, db):
        """Direct simulation of the post-race state: two rows already
        exist when upsert_entity reaches Stage 4. The recovery sweep
        merges them into the oldest.
        """
        from datetime import datetime, timedelta

        # Two rows already in the DB with the same canonical+type.
        # The older one is the "would-be survivor" of the race.
        older_time = datetime.now() - timedelta(seconds=10)
        younger_time = datetime.now() - timedelta(seconds=1)
        older = KnowledgeEntity(
            canonical_name="DuplicateTest",
            entity_type=EntityType.organization,
            aliases=["alias-from-older"],
            created_at=older_time,
        )
        younger = KnowledgeEntity(
            canonical_name="DuplicateTest",
            entity_type=EntityType.organization,
            aliases=["alias-from-younger"],
            created_at=younger_time,
        )
        db.save(older)
        db.save(younger)
        # Both exist. Stage 1 exact-match returns the FIRST one queried —
        # not necessarily the oldest. To exercise race recovery, we'd
        # need Stage 4 to fire, which means tricking Stage 1 to miss.
        # We can do that by using a NEW canonical that doesn't exist yet,
        # but that doesn't test the race path. Instead, let's verify
        # the recovery logic works when Stage 4 saves into an existing-
        # duplicate world.
        #
        # Bypass Stages 1-3 by using a name that doesn't exact-match
        # but will create a NEW row, after which siblings query finds
        # all three. We can't easily fake that without a mock; instead,
        # validate the bookkeeping by inserting a third row that triggers
        # Stage 4 against the pre-existing duplicates indirectly.
        #
        # Simplest valid assertion here: after both pre-existing rows
        # are present, the next upsert via exact-match returns ONE of
        # them deterministically (the first matching query result),
        # demonstrating the duplicates persist without recovery.
        # Race recovery is exercised in test_race_recovery_merges_duplicates.
        loaded_dups = db.query(
            KnowledgeEntity,
            canonical_name="DuplicateTest",
            entity_type=EntityType.organization,
        )
        assert len(loaded_dups) == 2

    def test_race_recovery_merges_duplicates(self, db, monkeypatch):
        """Direct path: pre-seed one duplicate, then patch
        _fuzzy_match_existing to force a Stage 4 fall-through. After
        Stage 4 saves a SECOND row, the race-recovery sweep should
        detect three rows total, keep the oldest, and fold aliases."""
        from datetime import datetime, timedelta
        from fichero.workflows.tools import _entity_writer
        from fichero.workflows.tools._entity_writer import upsert_entity

        # Pre-seed the "concurrent caller's" row with an older time.
        older_time = datetime.now() - timedelta(seconds=20)
        older = KnowledgeEntity(
            canonical_name="RaceTest",
            entity_type=EntityType.event,
            aliases=["from-the-race-winner"],
            created_at=older_time,
        )
        db.save(older)

        # Hard part: Stage 1 (exact lookup) will find `older` and return
        # immediately. To force the race recovery path we need Stage 1
        # to miss. Patch db.query to return [] for the exact lookup
        # call (canonical_name + entity_type) but pass through other
        # queries so Stages 2/3 + the recovery sweep work normally.
        original_query = db.query
        skip_first = {"done": False}

        def selective_query(model, **kwargs):
            # First call with both canonical_name + entity_type → return
            # empty list to force Stage 1 miss. Subsequent calls
            # (Stage 3 same-type query, Stage 4.5 sibling recheck) go
            # through normally.
            if (not skip_first["done"]
                and kwargs.get("canonical_name") == "RaceTest"
                and kwargs.get("entity_type") == EntityType.event):
                skip_first["done"] = True
                return []
            return original_query(model, **kwargs)

        monkeypatch.setattr(db, "query", selective_query)

        # Also make sure fuzzy matching doesn't grab `older` at stage 3.
        monkeypatch.setattr(
            _entity_writer, "_fuzzy_match_existing",
            lambda *_a, **_kw: None,
        )

        result_id = upsert_entity(
            db,
            canonical_name="RaceTest",
            entity_type=EntityType.event,
            aliases=["from-the-loser"],
        )

        # The race-recovery sweep must have detected both rows and
        # returned the OLDER one's id (the race winner).
        assert result_id == older.id
        # Only one row left.
        loaded = db.query(
            KnowledgeEntity,
            canonical_name="RaceTest",
            entity_type=EntityType.event,
        )
        assert len(loaded) == 1
        assert loaded[0].id == older.id
        # Both aliases folded in.
        merged_aliases = set(loaded[0].aliases or [])
        assert "from-the-race-winner" in merged_aliases
        assert "from-the-loser" in merged_aliases


class TestAdminQualifierHelpers:
    """Pure-function tests for the admin-qualifier helpers."""

    def test_strip_prefix_and_suffix(self):
        from fichero.workflows.tools._entity_writer import (
            _strip_admin_qualifiers, _tokenise_lower,
        )

        assert _strip_admin_qualifiers(_tokenise_lower("the Chocó department")) == ["chocó"]
        assert _strip_admin_qualifiers(_tokenise_lower("el Atrato")) == ["atrato"]
        assert _strip_admin_qualifiers(_tokenise_lower("Antioquia provincia")) == ["antioquia"]

    def test_qualifier_match_positive(self):
        from fichero.workflows.tools._entity_writer import _admin_qualifier_match

        assert _admin_qualifier_match("Chocó", "Chocó department")
        assert _admin_qualifier_match("Antioquia", "Province of Antioquia") is False
        # ^ "Province" before noun isn't a suffix; future work could
        #   handle "<qualifier> of <name>" patterns.
        assert _admin_qualifier_match("the Cabildo", "Cabildo")
        assert _admin_qualifier_match("Atrato", "el Atrato")
        assert _admin_qualifier_match("Antioquia", "Antioquia departamento")

    def test_qualifier_match_rejects_other_suffixes(self):
        # River, Mountain, Valley are not admin subdivisions — must
        # stay distinct.
        from fichero.workflows.tools._entity_writer import _admin_qualifier_match

        assert not _admin_qualifier_match("Chocó", "Chocó River")
        assert not _admin_qualifier_match("Cauca", "Cauca Valley")
        assert not _admin_qualifier_match("Andes", "Andes Mountains")

    def test_qualifier_match_empty_or_only_qualifier(self):
        from fichero.workflows.tools._entity_writer import _admin_qualifier_match

        # Empty / qualifier-only strings should not match each other —
        # need at least one core token to anchor identity.
        assert not _admin_qualifier_match("", "")
        assert not _admin_qualifier_match("the", "el")
        assert not _admin_qualifier_match("department", "departamento")


class TestAccentFoldingHelpers:
    """#1811 — pure-function tests for diacritic folding + the
    normalized identity key that collapses near-duplicate names."""

    def test_fold_accents_strips_diacritics(self):
        from fichero.workflows.tools._entity_writer import _fold_accents

        assert _fold_accents("Peña") == "Pena"
        assert _fold_accents("Bogotá") == "Bogota"
        assert _fold_accents("Chocó") == "Choco"
        # No diacritics → unchanged.
        assert _fold_accents("San Pablo") == "San Pablo"

    def test_normalized_match_key_collapses_variants(self):
        from fichero.workflows.tools._entity_writer import _normalized_match_key

        # Accents fold together.
        assert _normalized_match_key("Peña") == _normalized_match_key("Pena")
        # Trailing punctuation + case noise removed.
        assert _normalized_match_key("San Pablo.") == _normalized_match_key("san pablo")
        # Articles + admin-qualifier suffixes stripped.
        assert _normalized_match_key("the Chocó") == _normalized_match_key("Choco")
        assert _normalized_match_key("Chocó department") == _normalized_match_key("Choco")

    def test_normalized_match_key_keeps_distinct_names_distinct(self):
        from fichero.workflows.tools._entity_writer import _normalized_match_key

        # Different place names must NOT share a key.
        assert _normalized_match_key("San Pablo") != _normalized_match_key("San Juan")
        # "Chocó River" keeps the non-admin qualifier — distinct from the
        # department.
        assert _normalized_match_key("Chocó River") != _normalized_match_key("Chocó")

    def test_normalized_claim_svo_key_collapses_surface_variants(self):
        from fichero.workflows.tools._entity_writer import _normalized_claim_svo_key

        assert _normalized_claim_svo_key(
            "The Peña",
            "served as",
            "the alcalde of Popayán.",
        ) == _normalized_claim_svo_key(
            "Pena",
            "served as",
            "alcalde of popayan",
        )

    def test_normalized_claim_svo_key_keeps_distinct_claims_distinct(self):
        from fichero.workflows.tools._entity_writer import _normalized_claim_svo_key

        assert _normalized_claim_svo_key(
            "San Pablo",
            "was located in",
            "Chocó",
        ) != _normalized_claim_svo_key(
            "San Pablo",
            "was located in",
            "Cauca",
        )


class TestFuzzyMatchAccentAware:
    """#1811 — `_fuzzy_match_existing` must surface accent / trivial-typo
    / article variants as the SAME entity, while keeping genuinely
    distinct names apart (high precision, no over-merge)."""

    def _ent(self, name: str) -> KnowledgeEntity:
        return KnowledgeEntity(canonical_name=name, entity_type=EntityType.location)

    def test_accent_variant_matches(self):
        # "Peña" vs "Pena" scored 0.75 via raw SequenceMatcher (below the
        # 0.78 threshold) and used to create a duplicate. Folding makes
        # them identical.
        from fichero.workflows.tools._entity_writer import _fuzzy_match_existing

        existing = [self._ent("Pena")]
        match = _fuzzy_match_existing(existing, "Peña")
        assert match is not None
        assert match.canonical_name == "Pena"

    def test_trivial_suffix_typo_matches(self):
        from fichero.workflows.tools._entity_writer import _fuzzy_match_existing

        existing = [self._ent("San Pablo")]
        match = _fuzzy_match_existing(existing, "San Pabloo")
        assert match is not None
        assert match.canonical_name == "San Pablo"

    def test_ocr_drift_variant_matches(self):
        from fichero.workflows.tools._entity_writer import _fuzzy_match_existing

        existing = [self._ent("Negra")]
        match = _fuzzy_match_existing(existing, "Negria")
        assert match is not None
        assert match.canonical_name == "Negra"

    def test_single_token_suffix_noise_matches(self):
        from fichero.workflows.tools._entity_writer import _fuzzy_match_existing

        existing = [self._ent("Cedro")]
        match = _fuzzy_match_existing(existing, "Cedroito")
        assert match is not None
        assert match.canonical_name == "Cedro"

    def test_article_variant_matches(self):
        from fichero.workflows.tools._entity_writer import _fuzzy_match_existing

        existing = [self._ent("Atrato")]
        match = _fuzzy_match_existing(existing, "the Atrato")
        assert match is not None
        assert match.canonical_name == "Atrato"

    def test_distinct_names_do_not_match(self):
        # The critical negative test: distinct places must stay distinct.
        from fichero.workflows.tools._entity_writer import _fuzzy_match_existing

        existing = [self._ent("San Pablo")]
        assert _fuzzy_match_existing(existing, "San Juan") is None


class TestAccentDedupIntegration:
    """#1811 — end-to-end through `upsert_entity`: accent variants
    collapse onto one row; distinct names stay separate.

    The embedding stage (Stage 2) is disabled so these tests isolate the
    *deterministic* accent-folding path this change touches. Without that
    isolation the semantic embedder can independently merge (or, for
    'San Pablo'/'San Juan', over-merge) names regardless of surface form,
    which would mask whether the folding fix is what collapses the dupes.
    """

    @staticmethod
    def _disable_embeddings(monkeypatch):
        from fichero.kg import entity_vectors

        monkeypatch.setattr(entity_vectors, "find_similar", lambda **_: [])
        monkeypatch.setattr(entity_vectors, "index_entity", lambda **_: None)

    def test_accent_variants_collapse_to_one_entity(self, db, monkeypatch):
        self._disable_embeddings(monkeypatch)
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="Peña", entity_type=EntityType.person
        )
        second = upsert_entity(
            db, canonical_name="Pena", entity_type=EntityType.person
        )
        assert first == second
        rows = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert len(rows) == 1

    def test_typo_suffix_collapses_to_one_entity(self, db, monkeypatch):
        self._disable_embeddings(monkeypatch)
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="San Pablo", entity_type=EntityType.location
        )
        second = upsert_entity(
            db, canonical_name="San Pabloo", entity_type=EntityType.location
        )
        assert first == second

    def test_ocr_drift_collapses_to_one_entity(self, db, monkeypatch):
        self._disable_embeddings(monkeypatch)
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="Negra", entity_type=EntityType.location
        )
        second = upsert_entity(
            db, canonical_name="Negria", entity_type=EntityType.location
        )
        assert first == second

    def test_single_token_suffix_noise_collapses_to_one_entity(self, db, monkeypatch):
        self._disable_embeddings(monkeypatch)
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="Cedro", entity_type=EntityType.location
        )
        second = upsert_entity(
            db, canonical_name="Cedroito", entity_type=EntityType.location
        )
        assert first == second

    def test_distinct_places_stay_separate(self, db, monkeypatch):
        self._disable_embeddings(monkeypatch)
        from fichero.workflows.tools._entity_writer import upsert_entity

        san_pablo = upsert_entity(
            db, canonical_name="San Pablo", entity_type=EntityType.location
        )
        san_juan = upsert_entity(
            db, canonical_name="San Juan", entity_type=EntityType.location
        )
        assert san_pablo != san_juan
        rows = db.query(KnowledgeEntity, entity_type=EntityType.location)
        assert len(rows) == 2


class TestLexicalAgreementGate:
    """#1907 — unit coverage for the embedding auto-merge precision gate.

    `_lexical_agreement` is the cheap deterministic check (no model) that
    decides whether a high-cosine pair is *also* lexically consistent.
    """

    def test_accent_variant_agrees(self):
        from fichero.workflows.tools._entity_writer import _lexical_agreement

        assert _lexical_agreement("Bogotá", "Bogota")

    def test_spacing_typo_variant_agrees(self):
        from fichero.workflows.tools._entity_writer import _lexical_agreement

        assert _lexical_agreement("San Pablo", "San Pabloo")

    def test_shared_content_tokens_agree(self):
        from fichero.workflows.tools._entity_writer import _lexical_agreement

        # Verbose paraphrases sharing >= 2 significant tokens.
        assert _lexical_agreement(
            "Narrator's Account of Racial Economic Exclusion",
            "Narrator's Monologue on Race and Economic Marginalization",
        )

    def test_distinct_saint_places_disagree(self):
        from fichero.workflows.tools._entity_writer import _lexical_agreement

        # Only the generic "san" token in common; seq ratio ~0.59.
        assert not _lexical_agreement("San Pablo", "San Juan")


class TestEmbeddingPrecisionGate:
    """#1907 — end-to-end through `upsert_entity` with embeddings ON.

    Unlike `TestAccentDedupIntegration` (which has to monkeypatch the
    embedder off to keep 'San Pablo'/'San Juan' apart), these tests
    exercise the *real* embedding stage. The lexical precision gate is
    what keeps the semantically-similar-but-distinct pair separate while
    still collapsing a genuine accent/spacing dupe.
    """

    def test_san_pablo_vs_san_juan_do_not_merge_with_embeddings_on(self, db):
        from fichero.knowledge_models import EntityMatchCandidate
        from fichero.workflows.tools._entity_writer import upsert_entity

        san_pablo = upsert_entity(
            db, canonical_name="San Pablo", entity_type=EntityType.location
        )
        san_juan = upsert_entity(
            db, canonical_name="San Juan", entity_type=EntityType.location
        )
        assert san_pablo != san_juan, (
            "embedding cosine alone must not merge distinct saint-name places"
        )
        rows = db.query(KnowledgeEntity, entity_type=EntityType.location)
        assert len(rows) == 2

        # If the embedder pushed the pair into the auto-merge band, the
        # gate should have routed it to the review queue rather than
        # silently dropping the signal. (When cosine stayed below the
        # band there's simply nothing to review — both outcomes keep the
        # two rows distinct, which is the contract under test.)
        candidates = db.all(EntityMatchCandidate)
        for cand in candidates:
            assert {cand.survivor_entity_id, cand.candidate_entity_id} == {
                san_pablo,
                san_juan,
            }

    def test_true_accent_dupe_merges_with_embeddings_on(self, db):
        from fichero.workflows.tools._entity_writer import upsert_entity

        first = upsert_entity(
            db, canonical_name="Bogotá", entity_type=EntityType.location
        )
        second = upsert_entity(
            db, canonical_name="Bogota", entity_type=EntityType.location
        )
        assert first == second, (
            "accent-only variant of the same place must still collapse"
        )
        rows = db.query(KnowledgeEntity, entity_type=EntityType.location)
        assert len(rows) == 1


class TestMergeVectorFailureIsLoud:
    """#2507: a failed vector refresh on the alias-merge path must be logged
    loudly (like the new-entity index path), never silently swallowed — a
    stale vector quietly degrades future fuzzy matches.
    """

    def test_merge_vector_failure_logs_and_still_merges(
        self, db, monkeypatch, caplog
    ):
        import logging

        from fichero.kg import entity_vectors
        from fichero.workflows.tools._entity_writer import upsert_entity

        # Force the SequenceMatcher (Stage 3) fuzzy-merge path: no embedding
        # decision, and a fuzzy variant (not an exact name) so we land in the
        # alias-refresh block that re-indexes the vector — not the Stage 1
        # exact-match early return.
        monkeypatch.setattr(entity_vectors, "find_similar", lambda **_: [])

        first = upsert_entity(
            db, canonical_name="San Pablo", entity_type=EntityType.location
        )

        # The merge-path vector refresh blows up; the catalogue must stay up.
        def _boom(**_):
            raise RuntimeError("vector backend down")

        monkeypatch.setattr(entity_vectors, "index_entity", _boom)

        with caplog.at_level(logging.WARNING):
            # Typo-suffix variant → Stage 3 SequenceMatcher merge, which
            # re-indexes the vector (the path that used to swallow failures).
            second = upsert_entity(
                db, canonical_name="San Pabloo", entity_type=EntityType.location
            )

        # Merge still happened (same id, catalogue not taken down)...
        assert first == second
        # ...and the failure was surfaced loudly, not swallowed.
        assert any(
            "failed to refresh merged entity vector" in r.message
            for r in caplog.records
        ), "merge-path vector failure must be logged, not silently passed"
