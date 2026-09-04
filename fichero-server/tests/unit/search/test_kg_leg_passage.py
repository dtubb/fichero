"""A KG search hit shows the part of the page it is about (#4669).

Daniel, twice: "for library search, we should really be showing the RELEVANT
PARTS of the page, not just the keyword."

The claim leg has always carried a sentence. The entity leg carried
``page_content[:500]`` — the top of the page, which is where the match is
not — so a hit on "Bazán" rendered the document's opening line and the reader
had to open the page to find out why it came back at all.

Every case here also pins the ANCHOR, because an excerpt that cannot say
where it sits in the document sends the reader to char 0 (the defect
787b624c2 fixed for search passages) even when the text on screen is right.
"""

from __future__ import annotations

from fichero_server.db import _kg_leg_passage

PAGE = (
    "Sepan quantos esta carta vieren como nos los caciques del pueblo. "
    "Otorgamos poder cumplido a Juan Bazan vecino desta ciudad para que "
    "en nuestro nombre pueda parecer ante la Real Audiencia. "
    "Fecha en Merida a diez dias del mes de abril."
)


class TestClaimQuoteWins:
    def test_a_grounded_quote_is_the_passage_with_its_own_anchor(self):
        # Since #4666 a claim's source_text IS a span of the page, recorded
        # with the offset it was found at: right sentence, already anchored.
        passage, start = _kg_leg_passage(
            PAGE,
            ["Bazán"],
            [("Otorgamos poder cumplido a Juan Bazan", 66)],
        )
        assert passage == "Otorgamos poder cumplido a Juan Bazan"
        assert start == 66
        assert PAGE[start : start + len(passage)] == passage

    def test_the_recorded_anchor_is_trusted_over_a_fresh_search(self):
        # Two identical spans on one page would otherwise resolve to the
        # first; the writer recorded which one this claim came from.
        _, start = _kg_leg_passage(PAGE, ["Bazán"], [("Fecha en Merida", 999)])
        assert start == 999

    def test_a_quote_with_no_offset_is_located_in_the_page(self):
        passage, start = _kg_leg_passage(
            PAGE, ["Bazán"], [("Fecha en Merida", None)]
        )
        assert PAGE[start : start + len(passage)] == passage

    def test_an_empty_quote_falls_through_to_the_next_evidence(self):
        passage, _ = _kg_leg_passage(PAGE, ["Bazán"], [("   ", 5)])
        assert "Bazan" in passage


class TestMentionFallback:
    def test_the_window_is_centred_on_the_mention_not_the_page_top(self):
        page = ("x" * 400) + " Otorgamos poder a Juan Bazan vecino. " + ("y" * 400)
        passage, start = _kg_leg_passage(page, ["Bazán"], [])
        assert "Bazan" in passage
        assert start > 0, "the passage must not claim to start at char 0"
        assert page[start : start + len(passage)] == passage

    def test_an_accented_surface_finds_its_unaccented_transcription(self):
        # The corpus's daily case: the entity is "Bazán", the manuscript
        # says "Bazan". Same fold search already matches with.
        passage, _ = _kg_leg_passage(PAGE, ["Bazán"], [])
        assert "Bazan" in passage

    def test_an_alias_is_searched_too(self):
        page = ("x" * 400) + " ante la Real Audiencia de Santa Fe. " + ("y" * 400)
        passage, start = _kg_leg_passage(page, ["Audiencia Real", "Real Audiencia"], [])
        assert "Real Audiencia" in passage
        assert start > 0

    def test_a_fragment_does_not_match_a_longer_word(self):
        # Whole-word only: "cat" must not window onto "cattle" (#4363's rule).
        page = "the cattle drive went north " * 20
        passage, start = _kg_leg_passage(page, ["cat"], [])
        assert start == 0
        assert passage == page[:500]

    def test_a_two_letter_surface_is_not_searched_at_all(self):
        passage, start = _kg_leg_passage(PAGE, ["de"], [])
        assert (passage, start) == (PAGE[:500], 0)


class TestHonestFallback:
    def test_an_unfindable_entity_gets_the_old_behaviour(self):
        # Neither the KG nor the transcript can say where the match is. The
        # page's opening is the honest best available, and it says so by
        # anchoring at 0 rather than pretending to a position.
        passage, start = _kg_leg_passage(PAGE, ["Nowhere-at-all"], [])
        assert passage == PAGE[:500]
        assert start == 0

    def test_an_empty_page_does_not_raise(self):
        assert _kg_leg_passage("", ["Bazán"], []) == ("", 0)
