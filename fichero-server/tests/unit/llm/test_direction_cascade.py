"""Direction is the third fact of the cascade (#4938).

`source.dir.per-segment` and `source.dir.logical-order-stored`. Direction walks
the same rungs as language and script, through the same `_stated_fact` reader, so
there is one cascade and not three — but it has one thing neither of the others
does: when no level states it, it is DERIVED from the resolved script, and says
so at level `derived-from-script`.

Why that derivation is not the mistake `unknown-is-not-unexamined` forbids: a
direction has to be decided either way, because the text is drawn on a screen;
a script is a claim about the source that nobody is forced to make. The level
name is what keeps the two apart.

(`source.dir.reader-lays-out` is app work and is not tested here.)
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.models.anchors import SourceAnchor
from fichero_server.llm.language_policy import (
    DIRECTION_ALTERNATING,
    DIRECTION_FOLLOWS_BASELINE,
    DIRECTION_LTR,
    DIRECTION_RTL,
    DIRECTION_TTB,
    DIRECTIONS,
    SOURCE_DERIVED_FROM_SCRIPT,
    LEVEL_DOCUMENT,
    LEVEL_READING,
    LEVEL_SEGMENT,
    STATUS_UNKNOWN,
    BadDirection,
    assert_known_direction,
    resolve_direction,
    script_may_be_vertical,
)

pytestmark = pytest.mark.source_model


def _holder(**kwargs) -> SimpleNamespace:
    kwargs.setdefault("direction", None)
    kwargs.setdefault("direction_meta", None)
    kwargs.setdefault("script", None)
    kwargs.setdefault("script_meta", None)
    return SimpleNamespace(**kwargs)


class TestItWalksTheSameRungs:
    def test_a_segments_own_direction_wins_over_the_documents(self):
        resolved = resolve_direction(
            segment=_holder(direction=DIRECTION_RTL),
            document=_holder(direction=DIRECTION_LTR),
        )

        assert resolved.language == DIRECTION_RTL
        assert resolved.level == LEVEL_SEGMENT

    def test_a_reading_overrides_its_segment(self):
        resolved = resolve_direction(
            reading=_holder(direction=DIRECTION_LTR),
            segment=_holder(direction=DIRECTION_RTL),
        )

        assert resolved.language == DIRECTION_LTR
        assert resolved.level == LEVEL_READING

    def test_a_segment_that_states_nothing_falls_through_to_the_document(self):
        resolved = resolve_direction(
            segment=_holder(), document=_holder(direction=DIRECTION_TTB)
        )

        assert resolved.language == DIRECTION_TTB
        assert resolved.level == LEVEL_DOCUMENT

    def test_a_pinned_request_outranks_every_level(self):
        resolved = resolve_direction(
            requested=DIRECTION_RTL, segment=_holder(direction=DIRECTION_LTR)
        )

        assert resolved.language == DIRECTION_RTL
        # A pinned value is not inherited from anywhere, so it is not a rung.
        assert resolved.level is None

    def test_examined_and_undetermined_stops_the_walk(self):
        """The same three states as the other two facts: a segment that was
        looked at and could not be told must not silently take the document's
        answer, or the examination is lost."""
        resolved = resolve_direction(
            segment=_holder(direction_meta={"status": STATUS_UNKNOWN}),
            document=_holder(direction=DIRECTION_RTL),
        )

        assert resolved.language is None
        assert resolved.is_known is False
        assert resolved.level == LEVEL_SEGMENT


class TestTheDerivation:
    def test_with_nothing_set_an_arabic_page_reads_right_to_left(self):
        resolved = resolve_direction(segment=_holder(script="Arab"))

        assert resolved.language == DIRECTION_RTL
        assert resolved.source == SOURCE_DERIVED_FROM_SCRIPT
        assert resolved.level is None
        assert "Arab" in resolved.basis

    def test_a_derived_direction_is_never_mistaken_for_a_chosen_one(self):
        """The behaviour, stated once: `says-where-from` is the only thing
        standing between "we worked this out" and "a person decided this"."""
        derived = resolve_direction(segment=_holder(script="Arab"))
        chosen = resolve_direction(segment=_holder(direction=DIRECTION_RTL, script="Arab"))

        assert derived.language == chosen.language == DIRECTION_RTL
        # The distinction is carried by `source`, the field a caller already
        # inspects to decide whether to trust a value. `level` holds RUNGS, and a
        # derivation is not a rung -- no level stated this, so it is None.
        assert derived.source == SOURCE_DERIVED_FROM_SCRIPT
        assert derived.level is None
        assert chosen.level == LEVEL_SEGMENT
        assert derived.source != chosen.source

    def test_an_unlisted_script_derives_left_to_right(self):
        resolved = resolve_direction(segment=_holder(script="Latn"))

        assert resolved.language == DIRECTION_LTR
        assert resolved.source == SOURCE_DERIVED_FROM_SCRIPT
        assert resolved.level is None

    def test_a_may_be_vertical_script_still_derives_left_to_right(self):
        """"May be vertical" is not a direction. Modern horizontal Japanese is
        the common case, and guessing `ttb` would be wrong more often than not —
        but the set is named so a surface can ask about exactly these."""
        resolved = resolve_direction(segment=_holder(script="Hani"))

        assert resolved.language == DIRECTION_LTR
        assert script_may_be_vertical("Hani") is True
        assert script_may_be_vertical("Latn") is False

    def test_with_no_script_either_it_still_answers_and_says_why(self):
        resolved = resolve_direction(segment=_holder())

        assert resolved.language == DIRECTION_LTR
        assert resolved.source == SOURCE_DERIVED_FROM_SCRIPT
        assert resolved.level is None
        assert "no script" in resolved.basis

    def test_the_script_can_be_passed_in_so_one_caller_resolves_it_once(self):
        resolved = resolve_direction(segment=_holder(), script="Hebr")

        assert resolved.language == DIRECTION_RTL

    def test_a_declared_script_derives_left_to_right_and_can_be_overridden(self):
        """A project's own script is in no direction table, so it derives `ltr` —
        and the project sets the real direction on the segment, which is why a
        derivation must never outrank a stated value."""
        assert resolve_direction(segment=_holder(script="Qaaa")).language == DIRECTION_LTR
        assert (
            resolve_direction(segment=_holder(script="Qaaa", direction=DIRECTION_RTL)).language
            == DIRECTION_RTL
        )


class TestTheVocabulary:
    def test_the_six_directions_a_manuscript_needs(self):
        assert set(DIRECTIONS) == {
            "ltr", "rtl", "ttb", "btt", "alternating", "follows-baseline"
        }

    @pytest.mark.parametrize("direction", DIRECTIONS)
    def test_every_listed_direction_is_accepted(self, direction):
        assert_known_direction(direction)

    def test_none_is_accepted_because_it_means_nothing_was_set(self):
        assert_known_direction(None)

    @pytest.mark.parametrize("direction", ["LTR", "left-to-right", "horizontal", ""])
    def test_anything_else_is_refused_and_the_list_is_named(self, direction):
        with pytest.raises(BadDirection) as raised:
            assert_known_direction(direction)
        assert "follows-baseline" in str(raised.value)

    def test_boustrophedon_and_a_curved_baseline_are_in_the_list(self):
        """Not decoration: an inscription that turns at the end of every line and
        a line running along a curve are both real, and neither is one of the
        four axes. Leaving them out would force a wrong answer for each."""
        assert DIRECTION_ALTERNATING in DIRECTIONS
        assert DIRECTION_FOLLOWS_BASELINE in DIRECTIONS


#: A right-to-left line with Latin digits and a Latin word inside it. The digits
#: run left to right INSIDE a right-to-left line, which is the case the Unicode
#: bidirectional algorithm exists for — and the case where a well-meaning
#: "fix the order" would corrupt the text.
MIXED_LINE = "قرش 1847 عام Marshall"


class TestStoredTextIsNeverReordered:
    """`source.dir.logical-order-stored`. Nothing in this slice touches a string.

    Stored text is in READING order, and display order is the renderer's job via
    the Unicode bidirectional rules. The failure this pins is the tempting one: a
    well-meant reversal somewhere in the engine, which cannot be undone later
    because the original order is gone.
    """

    def test_a_mixed_direction_reading_round_trips_byte_for_byte(self, db):
        from fichero_server.models import ContentRepresentation

        row = ContentRepresentation(
            document_id="doc-bidi", kind="transcription", content=MIXED_LINE,
            script="Arab", language="ar",
            source_anchor=SourceAnchor(document_id="doc-bidi"),
        )
        db.save(row)

        stored = db.get(ContentRepresentation, row.id)
        assert stored.content == MIXED_LINE
        # Byte for byte, not merely equal-looking: a normalisation or a reversal
        # would pass a loose comparison of the same characters.
        assert stored.content.encode("utf-8") == MIXED_LINE.encode("utf-8")
        assert list(stored.content) == list(MIXED_LINE)

    def test_resolving_a_direction_does_not_touch_the_text(self, db):
        from fichero_server.models import ContentRepresentation

        row = ContentRepresentation(
            document_id="doc-bidi", kind="transcription", content=MIXED_LINE, script="Arab",
            source_anchor=SourceAnchor(document_id="doc-bidi"),
        )
        db.save(row)

        resolved = resolve_direction(reading=row)

        assert resolved.language == DIRECTION_RTL
        assert resolved.source == SOURCE_DERIVED_FROM_SCRIPT
        assert resolved.level is None
        assert db.get(ContentRepresentation, row.id).content == MIXED_LINE
