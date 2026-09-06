"""Entity-dedup QUALITY audit (Daniel: "deduping ... entities ... need to be good").

Proves the dedup is good, not merely that it runs:
  * case/accent variants of ONE person merge (upsert_entity);
  * role/title-only spans are rejected, but a role + a real name is kept
    (a3a752ddb);
  * clearly different people never merge;
  * cluster_aliases groups parenthetical aliases but no longer fuses distinct
    people that merely share letters (6eecd7b0a).

Each assertion fails if dedup regresses toward over- or under-merging. The one
KNOWN over-merge gap (divergent second surname) is captured as xfail so it is
visible in the suite and flips green the moment it is fixed.
"""

from __future__ import annotations

import pytest

from fichero_server.knowledge.spacy_ner import EntitySpan, cluster_aliases
from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from fichero_server.workflows.tools._entity_writer import upsert_entity


def _person_names(db) -> list[str]:
    return sorted(
        r.canonical_name
        for r in db.query(KnowledgeEntity, entity_type=EntityType.person)
    )


def _span(text: str) -> EntitySpan:
    return EntitySpan(text=text, fichero_type="person", start=0, end=len(text), label="PER")


class TestUpsertMergesTrueVariants:
    def test_case_variant_merges_to_one(self, db):
        a = upsert_entity(db, canonical_name="ALEJANDRO PIEDRAHITA", entity_type=EntityType.person)
        b = upsert_entity(db, canonical_name="Alejandro Piedrahita", entity_type=EntityType.person)
        assert a == b
        assert _person_names(db) == ["ALEJANDRO PIEDRAHITA"]

    def test_accent_variant_merges_to_one(self, db):
        a = upsert_entity(db, canonical_name="José Peña", entity_type=EntityType.person)
        b = upsert_entity(db, canonical_name="Jose Pena", entity_type=EntityType.person)
        assert a == b
        assert len(_person_names(db)) == 1


class TestUpsertKeepsDistinctPeople:
    def test_shared_surname_different_first_name_never_merges(self, db):
        upsert_entity(db, canonical_name="Juan Gómez", entity_type=EntityType.person)
        upsert_entity(db, canonical_name="Pedro Gómez", entity_type=EntityType.person)
        assert _person_names(db) == ["Juan Gómez", "Pedro Gómez"]

    def test_bare_surname_stays_separate_from_full_name(self, db):
        # Conservative: a bare surname is not auto-folded into a full name
        # (could be a different Restrepo). Under-merge here is the safe side.
        upsert_entity(db, canonical_name="Restrepo", entity_type=EntityType.person)
        upsert_entity(db, canonical_name="Vicente Restrepo", entity_type=EntityType.person)
        assert _person_names(db) == ["Restrepo", "Vicente Restrepo"]


class TestRoleOnlyRejection:
    def test_role_only_person_is_rejected(self, db):
        assert upsert_entity(db, canonical_name="ALCALDE", entity_type=EntityType.person) is None
        assert upsert_entity(db, canonical_name="EL SEÑOR JUEZ 20", entity_type=EntityType.person) is None
        assert _person_names(db) == []

    def test_role_followed_by_real_name_is_kept(self, db):
        rid = upsert_entity(db, canonical_name="el alcalde Pedro Nieto", entity_type=EntityType.person)
        assert rid is not None
        assert _person_names(db) == ["el alcalde Pedro Nieto"]


class TestClusterAliasesPrecision:
    def test_letter_overlap_does_not_fuse_distinct_people(self):
        # The old raw-substring merge fused "Ana" into "Susana". Must not.
        clusters = cluster_aliases([_span("Ana"), _span("Susana")])
        assert {k.text for k in clusters} == {"Ana", "Susana"}
        assert all(v == [] for v in clusters.values())

    def test_juan_does_not_fuse_into_juana(self):
        clusters = cluster_aliases([_span("Juan"), _span("Juana")])
        assert {k.text for k in clusters} == {"Juan", "Juana"}

    def test_parenthetical_alias_is_grouped(self):
        clusters = cluster_aliases([
            _span("Davidson"),
            _span("Davidson [Deibinson]"),
            _span("[Deibinson]"),
        ])
        # One canonical (the longest), the other two folded in as aliases.
        assert len(clusters) == 1
        canonical, aliases = next(iter(clusters.items()))
        assert canonical.text == "Davidson [Deibinson]"
        assert set(aliases) == {"Davidson", "[Deibinson]"}

    def test_short_mention_is_a_subset_alias(self):
        # A genuine short mention (whole-token subset) still groups.
        clusters = cluster_aliases([_span("Juan"), _span("Juan de la Cruz")])
        assert len(clusters) == 1
        canonical, aliases = next(iter(clusters.items()))
        assert canonical.text == "Juan de la Cruz"
        assert aliases == ["Juan"]


class TestKnownOverMergeGaps:
    @pytest.mark.xfail(
        reason="OVER-MERGE: _fuzzy_match_existing SequenceMatcher.ratio >= 0.78 "
        "merges names sharing first name + first surname when only the SECOND "
        "surname differs — two distinct Spanish people collapse. Routed to the "
        "entity-resolution/backend lane (svo-quality audit 2026-09-06).",
        strict=False,
    )
    def test_divergent_second_surname_should_not_merge(self, db):
        upsert_entity(db, canonical_name="María García López", entity_type=EntityType.person)
        upsert_entity(db, canonical_name="María García Pérez", entity_type=EntityType.person)
        # DESIRED: two different people. CURRENT: they merge into one.
        assert len(_person_names(db)) == 2
