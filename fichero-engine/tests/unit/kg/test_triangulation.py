"""Tests for cross-source triangulation (#900)."""

from __future__ import annotations

import pytest

from fichero.kg import triangulation
from fichero.models import DocType, Document, SourceAuthority
from fichero.models.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _seed_entity(db, name: str, etype=EntityType.person) -> str:
    ent = KnowledgeEntity(canonical_name=name, entity_type=etype)
    db.save(ent)
    return ent.id


def _seed_document(
    db,
    doc_id: str,
    *,
    authority: SourceAuthority = SourceAuthority.unknown,
) -> str:
    doc = Document(
        id=doc_id,
        name=doc_id,
        doc_type=DocType.file,
        source_authority=authority,
    )
    db.save(doc)
    return doc.id


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

    def test_skips_structurally_empty_svo_claims(self, db):
        """Claims with no usable predicate/object should not inflate support."""
        eid = _seed_entity(db, "Davidson")
        _seed_claim(db, entity_id=eid, source_doc="doc-1", verb="", obj="")
        _seed_claim(db, entity_id=eid, source_doc="doc-2", verb="", obj="")

        supports = triangulation.compute_support_counts(db)
        assert supports == {}


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

    def test_weighted_support_required_for_triangulation(self, db):
        """Three low-authority sources should not triangulate just by count."""
        eid = _seed_entity(db, "Davidson")
        for i in range(3):
            doc_id = f"doc-{i}"
            _seed_document(db, doc_id, authority=SourceAuthority.tertiary)
            _seed_claim(db, entity_id=eid, source_doc=doc_id,
                        verb="is", obj="an alias")

        triangulated = triangulation.triangulated_facts(db)
        assert triangulated == []

        supports = triangulation.compute_support_counts(db)
        support = next(iter(supports.values()))
        assert support.support_count == 3
        assert support.weighted_support == pytest.approx(0.9)


class TestPersistSupportCounts:
    """Tests for persist_support_counts — the global aggregation → write-back path."""

    def test_single_source_claim_keeps_count_one(self, db):
        """A claim from one source: corroboration_count stays 1 after recompute.

        The first persist run also populates corroborating_source_ids (was []
        by default), so one write does happen — but the count remains 1 and a
        second run is fully idempotent.
        """
        eid = _seed_entity(db, "Davidson")
        cid = _seed_claim(db, entity_id=eid, source_doc="doc-1",
                          verb="is", obj="an alias of Deibinson")

        updated = triangulation.persist_support_counts(db)
        # corroborating_source_ids went [] → ["doc-1"], so one write.
        assert updated == 1

        from fichero.models.knowledge import KnowledgeClaim
        claim = db.query(KnowledgeClaim, id=cid)[0]
        assert claim.corroboration_count == 1
        assert claim.weighted_corroboration_count == 1.0
        assert claim.corroborating_source_ids == ["doc-1"]

        # Second run: nothing changed — fully idempotent.
        assert triangulation.persist_support_counts(db) == 0

    def test_three_sources_raises_count_and_writes_back(self, db):
        """Three distinct sources for the same SVO triple → corroboration_count=3."""
        eid = _seed_entity(db, "Juan Pérez")
        c_ids = [
            _seed_claim(db, entity_id=eid, source_doc=f"doc-{i}",
                        verb="signed", obj="the deed")
            for i in range(3)
        ]

        updated = triangulation.persist_support_counts(db)
        assert updated == 3  # all three claims updated (were 1, now 3)

        from fichero.models.knowledge import KnowledgeClaim
        for cid in c_ids:
            claim = db.query(KnowledgeClaim, id=cid)[0]
            assert claim.corroboration_count == 3
            assert sorted(claim.corroborating_source_ids) == ["doc-0", "doc-1", "doc-2"]
            assert claim.weighted_corroboration_count == 3.0

    def test_weighted_corroboration_count_uses_source_authority(self, db):
        """persist_support_counts should persist the weighted source mix."""
        eid = _seed_entity(db, "Davidson")
        doc_specs = [
            ("doc-primary", SourceAuthority.primary),
            ("doc-secondary", SourceAuthority.secondary),
            ("doc-tertiary", SourceAuthority.tertiary),
        ]
        for doc_id, authority in doc_specs:
            _seed_document(db, doc_id, authority=authority)
            _seed_claim(db, entity_id=eid, source_doc=doc_id,
                        verb="is", obj="an alias of Deibinson")

        updated = triangulation.persist_support_counts(db)
        assert updated == 3

        from fichero.models.knowledge import KnowledgeClaim
        claims = db.query(KnowledgeClaim)
        assert len(claims) == 3
        for claim in claims:
            assert claim.corroboration_count == 3
            assert claim.weighted_corroboration_count == pytest.approx(1.9)
            assert sorted(claim.corroborating_source_ids) == [
                "doc-primary",
                "doc-secondary",
                "doc-tertiary",
            ]

    def test_distinct_claims_unaffected_by_each_other(self, db):
        """Two different facts from different entities don't bleed into each other."""
        d_id = _seed_entity(db, "Davidson")
        e_id = _seed_entity(db, "Eugenio")

        # Davidson's alias: 2 sources
        for i in range(2):
            _seed_claim(db, entity_id=d_id, source_doc=f"alias-{i}",
                        verb="is", obj="an alias of Deibinson")
        # Eugenio's role: 1 source
        e_cid = _seed_claim(db, entity_id=e_id, source_doc="role-doc",
                            verb="served as", obj="alcalde")

        triangulation.persist_support_counts(db)

        from fichero.models.knowledge import KnowledgeClaim
        e_claim = db.query(KnowledgeClaim, id=e_cid)[0]
        # Eugenio's claim should be untouched (still 1).
        assert e_claim.corroboration_count == 1
        assert e_claim.weighted_corroboration_count == 1.0

    def test_idempotent_second_call_updates_nothing(self, db):
        """Running persist_support_counts twice writes nothing on the second call."""
        eid = _seed_entity(db, "Davidson")
        for i in range(3):
            _seed_claim(db, entity_id=eid, source_doc=f"doc-{i}",
                        verb="is", obj="an alias of Deibinson")

        first = triangulation.persist_support_counts(db)
        second = triangulation.persist_support_counts(db)

        assert first == 3   # all three claims updated
        assert second == 0  # nothing changed on the second run

    def test_date_only_claims_skipped(self, db):
        """Claims with no entity_ids (date-style) are not touched."""
        from fichero.models.knowledge import KnowledgeClaim

        date_claim = KnowledgeClaim(
            text="1933-07-23 records the deed",
            source_document_id="doc-date",
            entity_ids=[],  # no entity → skipped by SVO grouping
            metadata={"verb": "records", "object": "the deed"},
        )
        db.save(date_claim)

        updated = triangulation.persist_support_counts(db)
        assert updated == 0

        reloaded = db.query(KnowledgeClaim, id=date_claim.id)[0]
        assert reloaded.corroboration_count == 1  # unchanged default
        assert reloaded.weighted_corroboration_count == 1.0
