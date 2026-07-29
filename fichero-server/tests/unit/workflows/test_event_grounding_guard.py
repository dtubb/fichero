"""Tests for the event grounding guard (#1114 issue 3).

The event-extraction prompt lists 'Accident, Flood, Death, Fire, Strike'
as exemplars, which leads the LLM to dutifully extract them even for
documents that don't mention any of them. The grounding guard requires
at least one content token of the event's name to appear in the source
chunk text; otherwise the event is dropped as hallucinated.
"""

from __future__ import annotations

from fichero_server.workflows.tools.extractors import _event_grounded_in_text


class TestEventGroundedInText:
    # --- positive: event names supported by the source text ---

    def test_exact_substring_present(self):
        # "Accident" appears in the source → grounded.
        assert _event_grounded_in_text(
            "Accident",
            "The miner suffered an accident in 1820.",
        )

    def test_one_content_token_present(self):
        # "Filing of the Petition" — "filing" is in the source.
        assert _event_grounded_in_text(
            "Filing of the Petition",
            "The widow's filing was rejected by the court.",
        )

    def test_case_insensitive_match(self):
        assert _event_grounded_in_text(
            "MINING BOOM",
            "The mining sector grew rapidly in the 1850s.",
        )

    def test_spanish_event_in_spanish_text(self):
        # Spanish-language source: "petición" appears.
        assert _event_grounded_in_text(
            "Petición al Cabildo",
            "Pedro presentó una petición al cabildo de Popayán.",
        )

    # --- negative: hallucinated events ---

    def test_accident_not_in_mining_text(self):
        # The bug from #1114: a mining-as-way-of-life doc gets "Accident"
        # extracted even though the word doesn't appear. The guard drops it.
        text = (
            "Artisanal mining in the Chocó region is a family livelihood. "
            "Small-scale miners work the San Juan and Atrato rivers, "
            "panning for gold using traditional techniques."
        )
        assert not _event_grounded_in_text("Accident", text)
        assert not _event_grounded_in_text("Death", text)
        assert not _event_grounded_in_text("Strike", text)
        assert not _event_grounded_in_text("Fire", text)
        assert not _event_grounded_in_text("Flood", text)

    def test_multi_word_event_no_token_in_text(self):
        # "Constitutional Hearing" — neither "constitutional" nor "hearing"
        # in the source.
        text = "The widow petitioned the cabildo for relief."
        assert not _event_grounded_in_text("Constitutional Hearing", text)

    # --- edge cases ---

    def test_empty_event_name_fails_open(self):
        # Degenerate empty input fails open — upstream extractor
        # validation should have caught it; we don't want to
        # accidentally suppress an item solely because the name field
        # is malformed.
        assert _event_grounded_in_text("", "anything")

    def test_all_stopwords_event_fails_open(self):
        # "The of the" reduces to no content tokens — fail-open.
        # Real hallucinations are content words, not stopword strings.
        assert _event_grounded_in_text("The of the", "different unrelated source")

    def test_short_tokens_fail_open(self):
        # Tokens of length <= 2 are dropped — fail-open when nothing
        # remains. Single-letter event names ("E") come from test fixtures
        # and degenerate LLM output, not from hallucination patterns.
        assert _event_grounded_in_text("A Of", "different unrelated source")

    def test_no_source_text_fails_open(self):
        # When caller doesn't provide grounding context, we fail-open
        # rather than drop everything — preserves legacy caller behavior.
        assert _event_grounded_in_text("Accident", None)
        assert _event_grounded_in_text("Accident", "")

    def test_stopwords_alone_dont_ground(self):
        # "The" appearing in source can't validate an event named "Accident":
        # stopwords are filtered from the event name too. "accident" has no
        # match in a stopword-only source → guard fires.
        text = "the of the of the"
        assert not _event_grounded_in_text("Accident", text)
