"""Tests for lang_detect — auto-detection of English vs Spanish (#809)."""

from __future__ import annotations

from fichero.llm.lang_detect import detect_language, resolve_output_language


class TestDetectLanguage:
    def test_empty_returns_default(self):
        assert detect_language("") == "English"
        assert detect_language("   ") == "English"

    def test_clearly_english(self):
        text = (
            "This document describes the case of Antonio Asprilla, who "
            "filed a petition with the court of first instance. The "
            "petition was reviewed and a ruling was issued in 1931."
        )
        assert detect_language(text) == "English"

    def test_clearly_spanish_via_stop_words(self):
        text = (
            "El documento describe el caso de Antonio Asprilla, que "
            "presentó una petición con el juzgado de primera instancia. "
            "La petición fue revisada y se emitió un fallo en 1931."
        )
        assert detect_language(text) == "Spanish"

    def test_spanish_diacritics_tip_the_balance(self):
        # Few stop words but heavy ñ/á/é signal — still Spanish.
        text = "España, año, niño, señor, mañana, corazón, café, cañón, baño."
        assert detect_language(text) == "Spanish"

    def test_too_short_falls_back_to_default(self):
        # 2 stop-word hits below the >=3 threshold → default.
        assert detect_language("the a") == "English"

    def test_english_with_spanish_loanwords_stays_english(self):
        # Real source pattern from Tubb's English chapter on the Chocó
        # — the kind of doc that previously biased to Spanish (#823).
        text = (
            "The author traveled to the Chocó region of Colombia, "
            "documenting artisanal gold mining alongside Leidy and her "
            "family. The work follows the rhythms of rebusque — the "
            "shifting forms of informal labor that miners use to get by. "
            "These are the practices of a remote Pacific community."
        )
        assert detect_language(text) == "English"

    def test_english_prose_with_spanish_proper_nouns_stays_english(self):
        text = (
            "Marshall wrote in English about Popayán, Andagoya, alcalde, "
            "and the Cauca valley, but the passage itself explains the "
            "journey in ordinary English prose with dates, names, and "
            "context about the diary entries and the people he met there. "
            "The document says the travelers crossed the river at dawn and "
            "recorded what they saw in the town that afternoon."
        )
        assert detect_language(text) == "English"

    def test_close_to_tied_breaks_only_with_heavy_diacritics(self):
        # Roughly equal stop-words but no diacritics → English (default).
        text = "the cat el gato in the la the and y of de"
        assert detect_language(text) == "English"

    def test_spanish_must_outweigh_english_by_margin(self):
        # English wins because Spanish doesn't beat it by 1.5×.
        text = "the the the the the el el el de"
        assert detect_language(text) == "English"

    def test_caller_can_override_default(self):
        assert detect_language("", default="Spanish") == "Spanish"


class TestResolveOutputLanguage:
    def test_explicit_language_passes_through(self):
        assert resolve_output_language("Spanish", "ignored text") == "Spanish"
        assert resolve_output_language("English", "ignored text") == "English"
        # Even when the text contradicts the explicit pick.
        spanish_text = "El documento describe el caso del señor."
        assert resolve_output_language("English", spanish_text) == "English"

    def test_auto_falls_to_detector(self):
        spanish_text = (
            "El documento describe el caso de Antonio Asprilla, que "
            "presentó una petición con el juzgado de primera instancia."
        )
        assert resolve_output_language("auto", spanish_text) == "Spanish"

    def test_empty_or_none_treated_as_auto(self):
        english_text = (
            "This document describes the case of Antonio Asprilla, who "
            "filed a petition with the court of first instance."
        )
        assert resolve_output_language(None, english_text) == "English"
        assert resolve_output_language("", english_text) == "English"

    def test_default_used_when_text_too_short(self):
        # Empty text + auto → falls back to the default kwarg.
        assert resolve_output_language("auto", "", default="English") == "English"
        assert resolve_output_language("auto", "", default="Spanish") == "Spanish"

    def test_primary_language_override_wins_over_auto(self):
        english_text = "This note is mostly English prose about Popayán and Andagoya."
        assert resolve_output_language(
            "auto",
            english_text,
            default="English",
            primary_language="Spanish",
        ) == "Spanish"

    def test_explicit_language_beats_primary_language_override(self):
        spanish_text = "El documento describe el caso de Antonio Asprilla."
        assert resolve_output_language(
            "English",
            spanish_text,
            default="English",
            primary_language="Spanish",
        ) == "English"
