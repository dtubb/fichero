"""Unit tests for _synthesize_svo_fallback (#1113).

The combined ``extract_all`` LLM call returns a single JSON payload for
all six entity sections; small/local models (Apple Intelligence) often
omit the verb/object split even when the schema requests it. The
fallback synthesises a deterministic SVO from any predicate text we
have so claim.predicate_verb / object_phrase are never NULL on the
write path. Without this, paragraph composition with citation arrows
(#1111) has nothing to render.
"""

from __future__ import annotations


from fichero_server.workflows.tools.extractors import _synthesize_svo_fallback


class TestSvoPassThrough:
    def test_full_svo_from_llm_passes_through_unchanged(self):
        v, o = _synthesize_svo_fallback(
            "Eugenio Córdoba", "served as", "the alcalde of Popayán", ""
        )
        assert v == "served as"
        assert o == "the alcalde of Popayán"

    def test_full_svo_ignores_legacy_context(self):
        # When the LLM gave us SVO, ignore any legacy context that might
        # also be on the item.
        v, o = _synthesize_svo_fallback(
            "X", "is", "a thing", "X: some legacy description"
        )
        assert v == "is"
        assert o == "a thing"


class TestSvoSynthesis:
    def test_descriptive_colon_form_strips_subject(self):
        # "Chocó: the region where artisanal mining occurs" — the
        # canonical observed shape from #1113. Subject is the canonical
        # name; rest is the description; verb defaults to "is".
        v, o = _synthesize_svo_fallback(
            "Chocó", "", "", "Chocó: the region where artisanal mining occurs"
        )
        assert v == "is"
        assert o == "the region where artisanal mining occurs"

    def test_em_dash_form_strips_subject(self):
        v, o = _synthesize_svo_fallback(
            "San Juan River", "", "", "San Juan River — a tributary of the Pacific"
        )
        assert v == "is"
        assert o == "a tributary of the Pacific"

    def test_legacy_context_without_subject_becomes_object(self):
        # No "Subject:" prefix — the whole context becomes the object,
        # and verb defaults to "is" so the rendered claim still reads
        # as a sentence.
        v, o = _synthesize_svo_fallback(
            "X", "", "", "a free-form description without a leading subject"
        )
        assert v == "is"
        assert o == "a free-form description without a leading subject"

    def test_verb_only_promotes_to_object(self):
        # Pathological item where the LLM gave us a verb but no object —
        # the verb becomes the object so we don't emit "X verbs ."
        v, o = _synthesize_svo_fallback("X", "drains the basin", "", "")
        assert v == "is"
        assert o == "drains the basin"

    def test_object_only_defaults_verb_to_is(self):
        v, o = _synthesize_svo_fallback("X", "", "the alcalde of Popayán", "")
        assert v == "is"
        assert o == "the alcalde of Popayán"

    def test_empty_inputs_return_empty(self):
        # Nothing to synthesise from — caller decides whether to skip.
        v, o = _synthesize_svo_fallback("X", "", "", "")
        assert v == ""
        assert o == ""

    def test_subject_mismatch_keeps_full_context(self):
        # When the prefix before ":" doesn't match the canonical, treat
        # the whole context as the object — we shouldn't strip text
        # belonging to the predicate just because there's a colon.
        v, o = _synthesize_svo_fallback(
            "Chocó", "", "", "Atrato river: drains the region westward"
        )
        # Heuristic doesn't recognise "Atrato river" as the canonical,
        # so we get the full context as the object.
        assert v == "is"
        assert o == "Atrato river: drains the region westward"

    def test_canonical_substring_match_strips(self):
        # "Choc" is a substring of canonical "Chocó" — case-insensitive
        # substring check still strips.
        v, o = _synthesize_svo_fallback(
            "Chocó", "", "", "chocó: a region in the Pacific"
        )
        assert v == "is"
        assert o == "a region in the Pacific"
