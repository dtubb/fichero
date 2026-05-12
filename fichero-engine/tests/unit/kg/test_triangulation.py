"""Tests for cross-source triangulation (#900)."""

from __future__ import annotations

from fichero.kg import triangulation
from fichero.knowledge_models import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _seed_entity(db, name: str, etype=EntityType.person) -> str:
    ent = KnowledgeEntity(canonical_name=name, entity_type=etype)
    db.save(ent)
    return ent.id


def _seed_claim(
    db, *, entity_id: str, source_doc: str,
    verb: str, obj: str,
) -> str:
    claim = KnowledgeClaim(
        text=f"{verb} {obj}",
        source_document_id=source_doc,
        entity_ids=[entity_id],
        metadata={"verb": verb, "object": obj},
    )
    db.save(claim)
    return claim.id


class TestComputeSupportCounts:
    def test_single_source_claim_has_support_one(self, db):
        eid = _seed_entity(db, "Davidson")
        _seed_claim(db, entity_id=eid, source_doc="doc-1",
                    verb="is", obj="an alias of Deibinson")
        supports = triangulation.compute_support_counts(db)
        assert len(supports) == 1
        support = next(iter(supports.values()))
        assert support.support_count == 1
        assert support.corroboration == "single-source"

    def test_two_sources_for_same_fact_corroborated(self, db):
        eid = _seed_entity(db, "Davidson")
        _seed_claim(db, entity_id=eid, source_doc="doc-1",
                    verb="is", obj="an alias of Deibinson")
        _seed_claim(db, entity_id=eid, source_doc="doc-2",
                    verb="is", obj="an alias of Deibinson")
        supports = triangulation.compute_support_counts(db)
        assert len(supports) == 1, "should group across sources"
        support = next(iter(supports.values()))
        assert support.support_count == 2
        assert support.corroboration == "corroborated"

    def test_three_or_more_sources_triangulated(self, db):
        eid = _seed_entity(db, "Davidson")
        for i in range(4):
            _seed_claim(db, entity_id=eid, source_doc=f"doc-{i}",
                        verb="is", obj="an alias of Deibinson")
        supports = triangulation.compute_support_counts(db)
        support = next(iter(supports.values()))
        assert support.support_count == 4
        assert support.corroboration == "triangulated"

    def test_multiple_claims_one_source_count_one(self, db):
        """Six claims about Davidson all from the same source doc
        contribute one to the support count — independence is about
        source diversity, not claim count."""
        eid = _seed_entity(db, "Davidson")
        for _ in range(6):
            _seed_claim(db, entity_id=eid, source_doc="doc-1",
                        verb="is", obj="an alias of Deibinson")
        supports = triangulation.compute_support_counts(db)
        support = next(iter(supports.values()))
        assert support.support_count == 1
        assert len(support.claim_ids) == 6
        assert support.corroboration == "single-source"

    def test_different_objects_dont_merge(self, db):
        """Davidson's surname-alias claim and a Davidson-role claim
        are different facts — they shouldn't fold into one."""
        eid = _seed_entity(db, "Davidson")
        _seed_claim(db, entity_id=eid, source_doc="doc-1",
                    verb="is", obj="an alias of Deibinson")
        _seed_claim(db, entity_id=eid, source_doc="doc-1",
                    verb="is", obj="the addressee of the letter")
        supports = triangulation.compute_support_counts(db)
        assert len(supports) == 2

    def test_case_insensitive_object_grouping(self, db):
        """Surface-form variants of the same object ("the Deed" vs
        "the deed") should group via _normalize_object."""
        eid = _seed_entity(db, "Juan Pérez")
        _seed_claim(db, entity_id=eid, source_doc="doc-1",
                    verb="signed", obj="the Deed")
        _seed_claim(db, entity_id=eid, source_doc="doc-2",
                    verb="signed", obj="the deed")
        supports = triangulation.compute_support_counts(db)
        assert len(supports) == 1
        assert next(iter(supports.values())).support_count == 2


class TestTriplesForEntity:
    def test_returns_only_triples_with_entity_as_subject(self, db):
        d_id = _seed_entity(db, "Davidson")
        e_id = _seed_entity(db, "Eugenio")
        _seed_claim(db, entity_id=d_id, source_doc="doc-1",
                    verb="is", obj="an alias")
        _seed_claim(db, entity_id=e_id, source_doc="doc-1",
                    verb="served as", obj="alcalde")
        davidson_triples = triangulation.triples_for_entity(db, d_id)
        assert len(davidson_triples) == 1
        assert davidson_triples[0].key.subject_id == d_id

    def test_sorts_by_descending_support(self, db):
        eid = _seed_entity(db, "Davidson")
        # Strongly-supported claim (3 sources).
        for i in range(3):
            _seed_claim(db, entity_id=eid, source_doc=f"strong-{i}",
                        verb="is", obj="an alias")
        # Weakly-supported claim (1 source).
        _seed_claim(db, entity_id=eid, source_doc="weak",
                    verb="lives in", obj="Chocó")
        triples = triangulation.triples_for_entity(db, eid)
        assert triples[0].support_count > triples[1].support_count


class TestTriangulatedFacts:
    def test_filters_below_threshold(self, db):
        d_id = _seed_entity(db, "Davidson")
        e_id = _seed_entity(db, "Eugenio")
        # Triangulated.
        for i in range(3):
            _seed_claim(db, entity_id=d_id, source_doc=f"d-{i}",
                        verb="is", obj="an alias")
        # Single-source.
        _seed_claim(db, entity_id=e_id, source_doc="x",
                    verb="served as", obj="alcalde")
        triangulated = triangulation.triangulated_facts(db)
        assert len(triangulated) == 1
        assert triangulated[0].key.subject_id == d_id

    def test_custom_threshold(self, db):
        eid = _seed_entity(db, "Davidson")
        for i in range(2):
            _seed_claim(db, entity_id=eid, source_doc=f"d-{i}",
                        verb="is", obj="an alias")
        # 2 sources — under default threshold (3), over custom (2).
        assert len(triangulation.triangulated_facts(db, threshold=3)) == 0
        assert len(triangulation.triangulated_facts(db, threshold=2)) == 1
