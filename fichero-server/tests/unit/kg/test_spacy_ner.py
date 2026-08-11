"""Tests for the spaCy NER pre-pass (#899 Phase C).

Locks the contract that:
- English text routes to en_core_web_sm; Spanish to es_core_news_sm.
- spaCy entity labels map to the right Fichero EntityType.
- Within-text duplicate mentions collapse to one span.
- Alias clustering folds parenthetical variants under the longest
  surface form (Davidson + [Deibinson] + Davidson [Deibinson] →
  one canonical with two aliases).
"""

from __future__ import annotations

import pytest

from fichero_server.knowledge import spacy_ner


# Reset the module-level pipeline cache between tests so a load
# failure in one test doesn't poison the next. spaCy itself caches
# the underlying model objects so this is cheap.
@pytest.fixture(autouse=True)
def _reset_pipelines():
    spacy_ner._pipelines.clear()
    yield


class TestDetectLanguage:
    def test_english_paragraph_picks_en(self):
        text = "The narrator described systemic exclusion of Black men from stable employment."
        assert spacy_ner.detect_language(text) == "en"

    def test_spanish_paragraph_picks_es(self):
        text = "Eugenio Córdoba, alcalde de Popayán, recibió la petición de los herederos."
        assert spacy_ner.detect_language(text) == "es"

    def test_empty_text_defaults_to_en(self):
        assert spacy_ner.detect_language("") == "en"

    def test_mixed_text_picks_majority(self):
        # Mostly English, with one Spanish phrase.
        text = "The mayor of Popayán signed the deed and recorded it in the official ledger."
        assert spacy_ner.detect_language(text) == "en"


class TestExtractEntities:
    def test_extracts_person_from_english(self):
        spans = spacy_ner.extract_entities(
            "Juan Pérez signed the deed in 1933.", language="en"
        )
        names = [s.text for s in spans if s.fichero_type == "person"]
        assert "Juan Pérez" in names

    def test_extracts_organization_from_english(self):
        spans = spacy_ner.extract_entities(
            "The Constitutional Court ruled on the petition.", language="en"
        )
        orgs = [s.text for s in spans if s.fichero_type == "organization"]
        assert orgs, "expected at least one ORG"

    def test_extracts_location_from_spanish(self):
        spans = spacy_ner.extract_entities(
            "Eugenio Córdoba era alcalde de Popayán en 1933.", language="es"
        )
        locations = [s.text for s in spans if s.fichero_type == "location"]
        assert any("Popayán" in s for s in locations)

    def test_duplicate_mentions_collapse_to_one_span(self):
        """The #896 within-page redundancy attack — same name mentioned
        multiple times should yield one span, not N."""
        text = "Davidson signed it. Later Davidson confirmed. Davidson again."
        spans = spacy_ner.extract_entities(text, language="en")
        davidson = [s for s in spans if s.text == "Davidson"]
        assert len(davidson) == 1

    def test_unknown_label_filtered_out(self):
        """spaCy may emit labels (MONEY, DATE, CARDINAL) that don't
        map to any Fichero EntityType — they should not appear in
        the output."""
        spans = spacy_ner.extract_entities(
            "He paid 500 dollars on Monday.", language="en"
        )
        # MONEY/DATE/CARDINAL aren't in our map, so output is empty.
        # (Or only non-MONEY/DATE entities if any exist.)
        types = {s.fichero_type for s in spans}
        # Either empty, or all in our known set.
        assert types.issubset(
            {"person", "location", "organization", "event", "concept"}
        )

    def test_empty_text_returns_empty_list(self):
        assert spacy_ner.extract_entities("") == []
        assert spacy_ner.extract_entities("   ") == []


class TestClusterAliases:
    def test_substring_variants_cluster_under_longest(self):
        """Davidson + Davidson [Deibinson] should cluster under the
        longer form with the shorter as an alias."""
        spans = [
            spacy_ner.EntitySpan(
                text="Davidson", fichero_type="person",
                start=0, end=8, label="PERSON",
            ),
            spacy_ner.EntitySpan(
                text="Davidson [Deibinson]", fichero_type="person",
                start=20, end=40, label="PERSON",
            ),
        ]
        clusters = spacy_ner.cluster_aliases(spans)
        # Long form is canonical, short form is an alias.
        canonical_texts = [c.text for c in clusters]
        assert "Davidson [Deibinson]" in canonical_texts
        assert "Davidson" not in canonical_texts
        long_span = next(c for c in clusters if c.text == "Davidson [Deibinson]")
        assert "Davidson" in clusters[long_span]

    def test_distinct_persons_stay_unclustered(self):
        """Juan Pérez and Eugenio Córdoba share no substring → two
        separate clusters."""
        spans = [
            spacy_ner.EntitySpan(
                text="Juan Pérez", fichero_type="person",
                start=0, end=10, label="PERSON",
            ),
            spacy_ner.EntitySpan(
                text="Eugenio Córdoba", fichero_type="person",
                start=20, end=35, label="PERSON",
            ),
        ]
        clusters = spacy_ner.cluster_aliases(spans)
        assert len(clusters) == 2

    def test_different_types_dont_cluster(self):
        """A PERSON and a LOCATION with overlapping substring shouldn't
        be merged — type segregation is the safety net."""
        spans = [
            spacy_ner.EntitySpan(
                text="London", fichero_type="person",
                start=0, end=6, label="PERSON",
            ),
            spacy_ner.EntitySpan(
                text="London", fichero_type="location",
                start=20, end=26, label="GPE",
            ),
        ]
        clusters = spacy_ner.cluster_aliases(spans)
        assert len(clusters) == 2
