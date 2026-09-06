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


class TestReadableSurfaceForm:
    """Dotted paleographic surface forms must read naturally (Daniel, 2026-09).

    Page text layers export "." where the word space belongs, and NER carried
    that through verbatim — "Antonio.de.guzman.vezino.dela.cibdad.de.uitoria".
    """

    def test_the_reported_names_read_naturally(self):
        assert spacy_ner.readable_surface_form(
            "Antonio.de.guzman.vezino.dela.cibdad.de.uitoria"
        ) == "Antonio de guzman vezino dela cibdad de uitoria"
        assert spacy_ner.readable_surface_form(
            "el.capitan.galarza.vz.detuniça"
        ) == "el capitan galarza vz detuniça"
        assert spacy_ner.readable_surface_form("la.cibdad.de.uitoria") == "la cibdad de uitoria"

    def test_an_initial_keeps_its_period(self):
        # "C." is followed by a space, so the period is not a separator.
        assert spacy_ner.readable_surface_form("Laura C. Hall") == "Laura C. Hall"

    def test_a_decimal_is_left_alone(self):
        # A period between digits is not a word separator.
        assert spacy_ner.readable_surface_form("3.5 varas") == "3.5 varas"

    def test_a_clean_name_passes_through(self):
        assert spacy_ner.readable_surface_form("Juan Pérez") == "Juan Pérez"

    def test_empty_is_returned_unchanged(self):
        assert spacy_ner.readable_surface_form("") == ""


class TestTrimPersonName:
    """A PERSON span must stop at the name, not swallow a trailing descriptor.

    Daniel, 2026-09: "Antonio de Guzman vezino de la cibdad de uitoria" is a
    run-on — the person is "Antonio de Guzman"; the rest is "resident of the
    city of Vitoria", an appositive that corrupts identity and fragments the
    graph.
    """

    def test_the_run_on_is_cut_at_the_residence_descriptor(self):
        assert spacy_ner.trim_person_name(
            "Antonio de Guzman vezino de la cibdad de uitoria"
        ) == "Antonio de Guzman"

    @pytest.mark.parametrize(
        "descriptor", ["vecino", "morador", "natural", "difunto", "alcalde", "cacique"]
    )
    def test_common_descriptors_all_cut(self, descriptor):
        assert spacy_ner.trim_person_name(f"Juan Pérez {descriptor} de Popayán") == "Juan Pérez"

    def test_a_kinship_descriptor_is_cut(self):
        assert spacy_ner.trim_person_name("María muger de Pedro") == "María"

    def test_a_leading_title_is_kept_only_the_trailing_descriptor_is_cut(self):
        # Titles precede the name; only the trailing "vz de Tunja" is a descriptor.
        assert spacy_ner.trim_person_name("el capitan Galarza vz de Tunja") == "el capitan Galarza"

    @pytest.mark.parametrize(
        "name",
        [
            "Antonio de Guzman",
            "Juan de la Cruz",
            "Eugenio Córdoba",
            "Nuestra Señora de la Candelaria",
        ],
    )
    def test_real_multiword_names_are_not_trimmed(self, name):
        assert spacy_ner.trim_person_name(name) == name

    def test_a_span_that_is_only_a_descriptor_is_left_alone(self):
        # The cut fires from the second word on, so a lone descriptor is never
        # emptied — it just isn't a valid person, which the caller handles.
        assert spacy_ner.trim_person_name("vecino") == "vecino"


class TestModelPreference:
    """The gate prefers the medium model WHEN INSTALLED, else the small one.

    Daniel wants a larger default out of the box for the two gate languages,
    with a clean fall-back so a machine that only has the bundled small model
    keeps working. This exercises `_load_pipeline` against a fake spaCy so no
    real ~40 MB wheel has to be present.
    """

    @pytest.fixture
    def fake_spacy(self, monkeypatch):
        import sys
        import types

        loaded: dict[str, object] = {}
        installed: set[str] = set()

        module = types.ModuleType("spacy")
        util = types.ModuleType("spacy.util")
        util.get_installed_models = lambda: sorted(installed)  # type: ignore[attr-defined]
        module.util = util  # type: ignore[attr-defined]

        def _load(name: str):
            if name not in installed:
                raise OSError(f"[E050] Can't find model {name!r}")
            obj = object()
            loaded["last"] = name
            return obj

        module.load = _load  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "spacy", module)
        monkeypatch.setitem(sys.modules, "spacy.util", util)
        return installed, loaded

    def test_medium_is_preferred_when_installed(self, fake_spacy):
        installed, loaded = fake_spacy
        installed.update({"es_core_news_sm", "es_core_news_md"})
        assert spacy_ner._load_pipeline("es") is not None
        assert loaded["last"] == "es_core_news_md"

    def test_falls_back_to_small_when_medium_absent(self, fake_spacy):
        installed, loaded = fake_spacy
        installed.add("es_core_news_sm")
        assert spacy_ner._load_pipeline("es") is not None
        assert loaded["last"] == "es_core_news_sm"

    def test_english_prefers_medium_too(self, fake_spacy):
        installed, loaded = fake_spacy
        installed.update({"en_core_web_sm", "en_core_web_md"})
        assert spacy_ner._load_pipeline("en") is not None
        assert loaded["last"] == "en_core_web_md"

    def test_no_installed_model_returns_none_not_crash(self, fake_spacy):
        installed, _loaded = fake_spacy
        # Nothing installed for Spanish → None, so callers fall through to the
        # LLM-only path rather than the workflow crashing.
        assert spacy_ner._load_pipeline("es") is None

    def test_an_added_language_loads_its_small_model(self, fake_spacy):
        installed, loaded = fake_spacy
        installed.add("fr_core_news_sm")
        assert spacy_ner._load_pipeline("fr") is not None
        assert loaded["last"] == "fr_core_news_sm"


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
