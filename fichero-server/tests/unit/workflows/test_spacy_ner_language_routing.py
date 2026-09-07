"""The spaCy NER model follows the DECLARED language, not a guess.

Observed live: the SCOOP "Extract Entities" step ran es_core_news_sm
(Spanish) on an English NYTimes page, mislabelling its entities. The cause
was a shape mismatch at the NER boundary — the shared language-policy
resolver (and lang_detect) emit canonical NAMES ("English"/"Spanish"), but
SpacyNERProvider tested `language in {"en", "es"}`, which only matches CODES.
So a resolved "English" silently failed the test, the declared language was
dropped, and spaCy fell back to its own heuristic — which could load the
wrong model.

`normalize_language` maps both shapes (name or code) to the model code, so
"English" and "en" alike route to the English model.
"""

from __future__ import annotations

import asyncio

from fichero_server.knowledge import spacy_ner
from fichero_server.workflows.ner.providers import SpacyNERProvider


class TestNormalizeLanguage:
    def test_english_name_routes_to_en(self):
        assert spacy_ner.normalize_language("English") == "en"

    def test_spanish_name_routes_to_es(self):
        assert spacy_ner.normalize_language("Spanish") == "es"
        assert spacy_ner.normalize_language("Español") == "es"

    def test_iso_codes_pass_through(self):
        assert spacy_ner.normalize_language("en") == "en"
        assert spacy_ner.normalize_language("es") == "es"

    def test_region_tagged_codes_use_their_base(self):
        assert spacy_ner.normalize_language("en-US") == "en"
        assert spacy_ner.normalize_language("es_ES") == "es"

    def test_unknown_or_auto_is_none_so_the_caller_detects(self):
        assert spacy_ner.normalize_language(None) is None
        assert spacy_ner.normalize_language("") is None
        assert spacy_ner.normalize_language("auto") is None
        # A language with no bundled model must not force a wrong one.
        assert spacy_ner.normalize_language("Klingon") is None


class TestProviderRoutesDeclaredLanguage:
    """Capture the language spaCy is actually asked for — no models loaded."""

    def _language_seen(self, monkeypatch, declared):
        seen: dict[str, object] = {}

        def _fake_extract(text, language=None):
            seen["language"] = language
            return []

        monkeypatch.setattr(spacy_ner, "extract_entities", _fake_extract)
        monkeypatch.setattr(spacy_ner, "cluster_aliases", lambda spans: {})
        provider = SpacyNERProvider(model_name="es_core_news_sm")
        asyncio.run(provider.extract("Hindenburg fled to the Dutch frontier.", language=declared))
        return seen["language"]

    def test_english_name_reaches_spacy_as_en(self, monkeypatch):
        # The regression: "English" must NOT be dropped to None (and then
        # risk the Spanish model the node was configured with).
        assert self._language_seen(monkeypatch, "English") == "en"

    def test_spanish_name_reaches_spacy_as_es(self, monkeypatch):
        assert self._language_seen(monkeypatch, "Spanish") == "es"

    def test_no_declared_language_falls_through_to_detection(self, monkeypatch):
        # None → spaCy detects from the text itself, not a forced model.
        assert self._language_seen(monkeypatch, None) is None
