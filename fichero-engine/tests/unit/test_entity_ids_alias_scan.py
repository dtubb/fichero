"""Tests for the reverse alias scan that extends claim.entity_ids[] (#1119).

The SVO + provider attribution work (#1113) shipped all but criterion (6):
entity_ids[] should reference EVERY entity mentioned in a claim, not
just the subject. Queries that walk entity_ids[] for "all claims that
mention X" (entity inspector, KG-RAG retrieval, citation following)
depend on this contract.

Implementation lives in `extractors._scan_for_mentioned_entities` /
`_build_alias_index`. These tests pin the matching behaviour
(case-insensitive whole-word, deduped, length ≥ 4, exclude pre-set,
stoplist) and the end-to-end behaviour via the actual _write_kg_rows
path is covered by the existing extractor edge-case tests.
"""

from __future__ import annotations

from fichero.models.knowledge import EntityType, KnowledgeEntity
from fichero.workflows.tools.extractors import (
    _build_alias_index,
    _scan_for_mentioned_entities,
)


class TestBuildAliasIndex:
    """The alias index snapshots every entity's canonical_name + aliases
    as (lowercased_name, entity_id) pairs, sorted longest-first so the
    greedy match prefers 'Chocó department' over 'Chocó'.
    """

    def test_includes_canonical_and_aliases(self, db):
        e1 = KnowledgeEntity(
            canonical_name="Chocó",
            entity_type=EntityType.location,
            aliases=["Chocó department"],
        )
        db.save(e1)
        pairs = _build_alias_index(db)
        names = {name for name, _ in pairs}
        assert "chocó" in names
        assert "chocó department" in names

    def test_excludes_short_names(self, db):
        # Names shorter than 4 chars are noisy ("ID", "of", etc.).
        db.save(KnowledgeEntity(
            canonical_name="MIT", entity_type=EntityType.organization,
        ))
        db.save(KnowledgeEntity(
            canonical_name="Stanford", entity_type=EntityType.organization,
        ))
        pairs = _build_alias_index(db)
        names = {name for name, _ in pairs}
        assert "mit" not in names
        assert "stanford" in names

    def test_excludes_stoplist(self, db):
        db.save(KnowledgeEntity(
            canonical_name="this", entity_type=EntityType.concept,
        ))
        pairs = _build_alias_index(db)
        names = {name for name, _ in pairs}
        assert "this" not in names

    def test_sorted_longest_first(self, db):
        # The greedy substring scan needs longer aliases first so it
        # prefers 'Chocó department' over 'Chocó' in a text mentioning
        # the longer form.
        db.save(KnowledgeEntity(
            canonical_name="Chocó",
            entity_type=EntityType.location,
            aliases=["Chocó department"],
        ))
        pairs = _build_alias_index(db)
        names = [name for name, _ in pairs]
        assert names == sorted(names, key=lambda n: -len(n))


class TestScanForMentionedEntities:
    """The whole-word, case-insensitive scan over claim text."""

    def test_finds_canonical_mention(self):
        # The classic case: claim references an entity that was extracted
        # for a DIFFERENT claim. Scan should find it and link.
        alias_pairs = [
            ("chocó", "e:chocó"),
            ("andes region", "e:andes"),
        ]
        result = _scan_for_mentioned_entities(
            "Chocó is part of the Andes region.",
            alias_pairs,
            exclude=set(),
        )
        # Both entities mentioned; result preserves longest-first order
        # from the input pairs list.
        assert set(result) == {"e:chocó", "e:andes"}

    def test_case_insensitive(self):
        alias_pairs = [("chocó", "e1")]
        assert _scan_for_mentioned_entities(
            "CHOCÓ is a department.", alias_pairs, set()
        ) == ["e1"]

    def test_whole_word_match(self):
        # 'Lima' must not match inside 'climate'.
        alias_pairs = [("lima", "e1")]
        assert _scan_for_mentioned_entities(
            "Climate change affects mining.", alias_pairs, set(),
        ) == []
        assert _scan_for_mentioned_entities(
            "Lima is the capital.", alias_pairs, set(),
        ) == ["e1"]

    def test_excludes_already_linked(self):
        # Subject entity already in entity_ids — must not be double-listed.
        alias_pairs = [("chocó", "e:chocó"), ("andes", "e:andes")]
        result = _scan_for_mentioned_entities(
            "Chocó is part of the Andes region.",
            alias_pairs,
            exclude={"e:chocó"},
        )
        assert result == ["e:andes"]

    def test_dedupes_repeated_mentions(self):
        # Same entity mentioned twice in one text → only listed once.
        alias_pairs = [("chocó", "e:chocó")]
        assert _scan_for_mentioned_entities(
            "Chocó is fascinating. Chocó has many rivers.",
            alias_pairs, set(),
        ) == ["e:chocó"]

    def test_empty_text_returns_empty(self):
        assert _scan_for_mentioned_entities("", [("foo", "e1")], set()) == []
        assert _scan_for_mentioned_entities(None, [("foo", "e1")], set()) == []

    def test_dedupes_aliases_to_same_entity(self):
        # Both 'chocó' and 'chocó department' map to entity e:chocó —
        # only one entry in the result.
        alias_pairs = [
            ("chocó department", "e:chocó"),
            ("chocó", "e:chocó"),
        ]
        result = _scan_for_mentioned_entities(
            "The Chocó department is in Colombia. Chocó has many rivers.",
            alias_pairs, set(),
        )
        assert result == ["e:chocó"]

    def test_special_chars_in_name(self):
        # Names with regex-special chars (parentheses, dots) must not
        # blow up the scanner — escaping handles them.
        alias_pairs = [("garcía márquez", "e:gm")]
        assert _scan_for_mentioned_entities(
            "García Márquez wrote Cien Años.", alias_pairs, set(),
        ) == ["e:gm"]


class TestEndToEndAliasScanThroughWriter:
    """End-to-end: when entity A is already in the DB and a NEW claim's
    text mentions A by name, _write_kg_rows extends entity_ids[] with
    A's id. Covers the #1119 acceptance bug shape directly.
    """

    def test_secondary_entity_picked_up(self, db):
        # Set up: two entities already exist in the DB.
        from fichero.workflows.tools._entity_writer import (
            save_claim, upsert_entity,
        )

        chocó_id = upsert_entity(
            db, canonical_name="Chocó",
            entity_type=EntityType.location,
        )
        andes_id = upsert_entity(
            db, canonical_name="Andes region",
            entity_type=EntityType.location,
        )

        # Simulate what _write_kg_rows does: build the index, then
        # scan the new claim's text for additional mentions.
        from fichero.workflows.tools.extractors import (
            _build_alias_index, _scan_for_mentioned_entities,
        )
        alias_pairs = _build_alias_index(db)
        claim_text = "Chocó is part of the Andes region."
        mentioned = _scan_for_mentioned_entities(
            claim_text, alias_pairs, exclude={chocó_id},
        )
        # The scan finds Andes; Chocó was excluded as the subject.
        assert andes_id in mentioned
        assert chocó_id not in mentioned

        # Save the claim with both ids.
        claim_id = save_claim(
            db, text=claim_text,
            source_document_id="doc1",
            entity_ids=[chocó_id, *mentioned],
        )
        from fichero.models.knowledge import KnowledgeClaim
        loaded = db.get(KnowledgeClaim, claim_id)
        assert chocó_id in loaded.entity_ids
        assert andes_id in loaded.entity_ids
