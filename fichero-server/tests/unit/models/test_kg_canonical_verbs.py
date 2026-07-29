"""Tests for the canonical-verb vocabulary (#1123 Phase C).

The free-text predicate_verb on every claim gets canonicalised at write
time via ``fichero_server.kg._common.canonical_verb``. These tests pin the
mapping contract: each variant maps to its canonical, lookup is
case-insensitive, unknown verbs return None (honest absence rather
than guessed mapping), and ``save_claim`` populates
``KnowledgeClaim.predicate_canonical`` automatically.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from fichero_server.kg._common import CANONICAL_VERBS, canonical_verb, slug_verb


# ---------------------------------------------------------------------------
# Pure-function lookup
# ---------------------------------------------------------------------------


class TestCanonicalVerbLookup:
    @pytest.mark.parametrize(
        "free_text, expected",
        [
            # ontological
            ("is", "is_a"),
            ("is a", "is_a"),
            ("part of", "part_of"),
            ("belongs to", "belongs_to"),
            # spatial
            ("located in", "located_in"),
            ("lives in", "located_in"),
            ("near", "near"),
            ("borders", "borders"),
            # temporal
            ("before", "preceded_by"),
            ("after", "followed_by"),
            ("dated to", "dated_to"),
            # speech / testimony
            ("said", "said"),
            ("declared", "said"),
            ("asserted", "said"),
            ("testified about", "testified_about"),
            ("petitioned", "petitioned"),
            # role / office
            ("served as", "served_as"),
            ("became", "served_as"),
            ("appointed as", "appointed"),
            ("held the office of", "held_office"),
            # kinship
            ("father of", "parent_of"),
            ("son of", "child_of"),
            ("married to", "married_to"),
            ("wife of", "married_to"),
            ("descended from", "descendant_of"),
            # property / transfer
            ("owns", "owns"),
            ("transferred to", "transferred"),
            ("inherited from", "inherited"),
            ("purchased", "bought"),
            # causal
            ("caused", "caused"),
            ("led to", "caused"),
            ("made possible", "enabled"),
            # authorship / records
            ("wrote", "wrote"),
            ("authored", "wrote"),
            ("signed", "signed"),
            # domain
            ("filed", "filed"),
            ("translated", "translated"),
        ],
    )
    def test_known_variants_map_to_canonical(self, free_text, expected):
        assert canonical_verb(free_text) == expected

    def test_case_insensitive(self):
        assert canonical_verb("SAID") == "said"
        assert canonical_verb("Located In") == "located_in"

    def test_whitespace_stripped(self):
        assert canonical_verb("  married to  ") == "married_to"

    def test_unknown_verb_returns_none(self):
        # Honest absence: better to surface "we don't have a canonical
        # for this verb" than to fabricate one. Aggregations that need a
        # URI fragment fall back to slug_verb().
        assert canonical_verb("blargled") is None
        assert canonical_verb("xyzzy") is None

    def test_empty_input_returns_none(self):
        assert canonical_verb(None) is None
        assert canonical_verb("") is None
        assert canonical_verb("   ") is None


class TestCanonicalVerbsVocabularyShape:
    """The dict itself should stay tight and well-formed."""

    def test_all_keys_are_normalised(self):
        # Keys in the dict are stored lower-stripped — the lookup
        # function lowers+strips its input. If a key wasn't normalised
        # the lookup would silently miss.
        for key in CANONICAL_VERBS:
            assert key == key.lower().strip(), f"un-normalised key: {key!r}"

    def test_all_values_are_snake_case_slugs(self):
        # Canonical slugs must be safe URI fragments — lowercase,
        # underscores, no spaces.
        for canonical in set(CANONICAL_VERBS.values()):
            assert " " not in canonical
            assert canonical == canonical.lower()
            # Allow `[a-z_]` only.
            assert all(c.islower() or c == "_" for c in canonical), (
                f"bad slug: {canonical!r}"
            )

    def test_size_within_target_range(self):
        # The issue spec calls for ~40-50 canonical verbs across the
        # categories. This test pins a soft ceiling; if we cross 80
        # variants or 60 canonicals, the vocabulary is sprawling and
        # the category structure needs a review.
        canonicals = set(CANONICAL_VERBS.values())
        assert 30 <= len(canonicals) <= 60, (
            f"canonical count {len(canonicals)} outside healthy range"
        )
        assert len(CANONICAL_VERBS) <= 120, "variant count too sprawling"


# ---------------------------------------------------------------------------
# Integration with save_claim
# ---------------------------------------------------------------------------


class TestSaveClaimPopulatesPredicateCanonical:
    """save_claim auto-fills predicate_canonical from predicate_verb so
    every existing extractor call site picks up canonicalisation without
    edits at every save site.
    """

    def test_known_verb_canonicalised(self):
        from fichero_server.db import Database
        from fichero_server.models.knowledge import KnowledgeClaim
        from fichero_server.models import Document, DocType
        from fichero_server.workflows.tools._entity_writer import save_claim

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            doc = Document(name="src", doc_type=DocType.file)
            db.save(doc)
            claim_id = save_claim(
                db,
                text="Pedro said he saw the alcalde.",
                source_document_id=doc.id,
                subject_canonical="Pedro",
                predicate_verb="said",
                object_phrase="he saw the alcalde",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded is not None
            assert loaded.predicate_verb == "said"
            assert loaded.predicate_canonical == "said"

    def test_variant_maps_to_canonical_slug(self):
        # "declared" is a variant of the canonical "said". The free-text
        # verb stays in predicate_verb for display; the canonical slug
        # is what downstream SPARQL / aggregation pivots on.
        from fichero_server.db import Database
        from fichero_server.models.knowledge import KnowledgeClaim
        from fichero_server.models import Document, DocType
        from fichero_server.workflows.tools._entity_writer import save_claim

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            doc = Document(name="src", doc_type=DocType.file)
            db.save(doc)
            claim_id = save_claim(
                db,
                text="The petitioner declared her case.",
                source_document_id=doc.id,
                predicate_verb="declared",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded.predicate_verb == "declared"
            assert loaded.predicate_canonical == "said"

    def test_unknown_verb_canonical_is_none(self):
        # "blargled" isn't in the vocabulary — predicate_verb keeps the
        # raw text, predicate_canonical encodes honest absence.
        from fichero_server.db import Database
        from fichero_server.models.knowledge import KnowledgeClaim
        from fichero_server.models import Document, DocType
        from fichero_server.workflows.tools._entity_writer import save_claim

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            doc = Document(name="src", doc_type=DocType.file)
            db.save(doc)
            claim_id = save_claim(
                db,
                text="Pedro blargled the testimony.",
                source_document_id=doc.id,
                predicate_verb="blargled",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded.predicate_verb == "blargled"
            assert loaded.predicate_canonical is None

    def test_no_verb_canonical_is_none(self):
        # A claim written without any predicate_verb at all should not
        # get a fabricated canonical slug.
        from fichero_server.db import Database
        from fichero_server.models.knowledge import KnowledgeClaim
        from fichero_server.models import Document, DocType
        from fichero_server.workflows.tools._entity_writer import save_claim

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            doc = Document(name="src", doc_type=DocType.file)
            db.save(doc)
            claim_id = save_claim(
                db,
                text="A claim with no SVO.",
                source_document_id=doc.id,
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded.predicate_canonical is None


# ---------------------------------------------------------------------------
# slug_verb predicate slugging — multi-word verb preservation
# ---------------------------------------------------------------------------


class TestSlugVerbMultiWordPredicates:
    """Tests for slug_verb with multi-word predicates including prepositions.

    slug_verb must preserve full multi-word verbs (with prepositions) by
    converting spaces/non-alphanumeric to dashes. This enables SPARQL queries
    and aggregation to work on multi-word predicates like "entered into",
    "funded trips to", "is located in".
    """

    def test_single_word_verb(self):
        """Simple verbs without spaces slug to lowercase."""
        assert slug_verb("is") == "is"
        assert slug_verb("Was") == "was"
        assert slug_verb("founded") == "founded"

    def test_two_word_verb_with_preposition(self):
        """Two-word verbs with prepositions preserve both words."""
        assert slug_verb("served as") == "served-as"
        assert slug_verb("located in") == "located-in"
        assert slug_verb("entered into") == "entered-into"
        assert slug_verb("transferred to") == "transferred-to"
        assert slug_verb("appointed as") == "appointed-as"

    def test_three_word_verb_with_preposition(self):
        """Three-word verb phrases preserve all three words."""
        assert slug_verb("funded trips to") == "funded-trips-to"
        assert slug_verb("is located in") == "is-located-in"
        assert slug_verb("was appointed as") == "was-appointed-as"

    def test_whitespace_normalization(self):
        """Extra whitespace is collapsed to single dashes."""
        assert slug_verb("entered  into") == "entered-into"
        assert slug_verb("  entered into  ") == "entered-into"
        assert slug_verb("is   located   in") == "is-located-in"

    def test_case_insensitive_slugging(self):
        """Verb phrases are converted to lowercase."""
        assert slug_verb("ENTERED INTO") == "entered-into"
        assert slug_verb("Served As") == "served-as"
        assert slug_verb("Is Located In") == "is-located-in"
