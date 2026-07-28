"""svo_* are NOT aliases of the display fields (#4172).

`svo_verb` was documented as an "alias for predicate_verb with consistent
naming". It is not: the display field holds the raw natural-language verb while
`svo_verb` holds a SLUG, in one of several shapes depending on which extractor
wrote it. A language or rendering fix that trusts the word "alias" would touch
one and not the other.

Deduplication happens to tolerate the divergence, because the normalizer folds
both '-' and '_' to spaces. That is load-bearing and undocumented, so it is
pinned here — if it ever stops holding, claims written by different extractors
silently stop deduplicating against each other.
"""

from __future__ import annotations

from fichero.knowledge._common import canonical_verb, slug_verb
from fichero.workflows.tools._entity_writer import _normalized_match_key


class TestTheTwoVerbFieldsGenuinelyDiffer:
    def test_slug_form_is_not_the_display_form(self):
        assert slug_verb("entered into") == "entered-into"
        assert slug_verb("entered into") != "entered into"

    def test_canonical_form_uses_a_different_separator_than_the_slug(self):
        """The citation-stance path writes canonical_verb into svo_verb."""
        assert slug_verb("served as") == "served-as"
        assert canonical_verb("served as") == "served_as"
        assert slug_verb("served as") != canonical_verb("served as")

    def test_canonical_vocabulary_is_bounded_and_can_return_none(self):
        """So svo_verb is sometimes None where predicate_verb is populated."""
        assert canonical_verb("entered into") is None


class TestDedupToleratesTheDivergence:
    """The reason the divergence has not caused a visible bug."""

    def test_dash_slug_matches_the_display_form(self):
        assert _normalized_match_key("entered-into") == _normalized_match_key("entered into")

    def test_underscore_canonical_matches_the_display_form(self):
        assert _normalized_match_key("served_as") == _normalized_match_key("served as")

    def test_all_three_verb_shapes_share_one_key(self):
        keys = {
            _normalized_match_key(form)
            for form in ("served as", "served-as", "served_as")
        }

        assert len(keys) == 1, (
            "claims written by different extractors would stop deduplicating "
            f"against each other: {keys}"
        )
