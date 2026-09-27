"""A real right-to-left page, from somebody else's corpus (#4944, the north star).

`fixtures/tarima_arabic_0498.page.xml` is a Maghrebi Arabic page from the Calfa
*Tarima* project (Apache-2.0, BULAC), 25 lines with baselines, in PAGE XML's 2013
namespace. **Every other real fixture here is Latin-script European**, so until this
one "any language, any direction" was proven only against pages we wrote.

**The finding is what the file does NOT say.** It declares no `readingDirection`, no
`primaryLanguage` and no `primaryScript` — a real Arabic corpus states none of the
three. So the honest reading is `None` at every one of them, and a reader that
inferred `rtl` from the text would be inventing a fact the source does not state. The
cascade may DERIVE a direction later, from a script somebody records, and say that it
derived it — which is a different claim from the file having said so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.formats import read_page, write_page

pytestmark = pytest.mark.source_model

FIXTURE = Path(__file__).parent / "fixtures" / "tarima_arabic_0498.page.xml"

#: Arabic's Unicode block, for asserting the text really is Arabic rather than
#: transliterated — a test that passed on romanised text would prove nothing.
ARABIC = range(0x0600, 0x0700)


@pytest.fixture(scope="module")
def arabic_page() -> bytes:
    data = FIXTURE.read_bytes()
    assert len(data) > 5_000, f"the fixture is {len(data)} bytes; it should be ~11 KB"
    return data


def _arabic_characters(text: str) -> int:
    return sum(1 for character in text if ord(character) in ARABIC)


class TestReadingARealArabicPage:
    def test_the_lines_and_their_baselines_arrive(self, arabic_page):
        page = read_page("pagexml", arabic_page)

        lines = [s for s in page.segments if s.kind == "line"]
        assert len(lines) == 25
        # Every line has a baseline: this corpus is Kraken-shaped, which is what
        # eScriptorium produces and what a real Arabic HTR workflow works in.
        assert all(line.baseline for line in lines)

    def test_the_arabic_text_arrives_and_is_really_arabic(self, arabic_page):
        page = read_page("pagexml", arabic_page)

        texts = [text for s in page.segments for _kind, text in s.readings]
        assert texts, "no text was read"
        total = sum(_arabic_characters(text) for text in texts)
        assert total > 50, f"only {total} Arabic characters; is this page transliterated?"

    def test_the_text_is_stored_byte_for_byte_in_logical_order(self, arabic_page):
        """`source.dir.logical-order-stored`. A reader that "helpfully" reversed a
        right-to-left string would destroy the original, and the original is the only
        thing a transcription is."""
        import re

        page = read_page("pagexml", arabic_page)
        # Line-level `Unicode` only. This page ALSO carries the whole text on its
        # region, with `/` between lines -- so a naive "every Unicode in the file, in
        # order" comparison fails on the region's copy appearing last in the file and
        # first in the read. The lines are what a line-by-line comparison is about; the
        # region's own copy is covered by the multiset check below.
        in_file = [
            match.decode("utf-8")
            for match in re.findall(
                rb"<TextLine\b.*?<Unicode>([^<]*)</Unicode>", arabic_page, re.S
            )
        ]
        read_back = [
            text
            for segment in page.segments
            if segment.kind == "line"
            for _kind, text in segment.readings
        ]

        assert read_back == in_file
        assert len(read_back) == 25

    def test_every_text_in_the_file_is_read_and_nothing_is_added(self, arabic_page):
        """The multiset, which catches a reader that dropped the region's own copy of
        the page text or invented a line."""
        import re

        page = read_page("pagexml", arabic_page)
        in_file = sorted(
            match.decode("utf-8")
            for match in re.findall(rb"<Unicode>([^<]*)</Unicode>", arabic_page)
        )
        read_back = sorted(text for s in page.segments for _kind, text in s.readings)

        assert read_back == in_file

    def test_the_file_states_NO_direction_and_none_is_invented(self, arabic_page):
        """The finding. An Arabic page with no `readingDirection` must come back with
        `direction=None` — "nothing has determined this" — not with `rtl` guessed from
        the characters. Inventing it would turn our inference into the source's claim,
        which is the whole distinction `says-where-from` exists to keep."""
        page = read_page("pagexml", arabic_page)

        assert page.direction is None
        assert all(segment.direction is None for segment in page.segments)

    def test_the_file_states_no_language_or_script_either(self, arabic_page):
        page = read_page("pagexml", arabic_page)

        assert page.language is None and page.script is None
        assert all(s.language is None and s.script is None for s in page.segments)

    def test_the_2013_namespace_is_read(self, arabic_page):
        """This corpus writes 2013, as eScriptorium does in places. Refusing it would
        refuse the files this project exists to read."""
        assert b"pagecontent/2013-07-15" in arabic_page
        assert read_page("pagexml", arabic_page).segments


class TestWritingItBackDoesNotInventADirection:
    def test_the_round_trip_keeps_the_text_and_adds_no_direction(self, arabic_page):
        page = read_page("pagexml", arabic_page)

        data, report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        assert [s.readings for s in returned.segments] == [s.readings for s in page.segments]
        assert returned.direction is None
        assert all(s.direction is None for s in returned.segments)
        assert "direction" not in report.lost

    def test_a_direction_WE_recorded_is_written_and_comes_back(self, arabic_page):
        """The other half: once a curator records `rtl` on the page, PAGE XML can state
        it and a re-import reads it back. So the absence above is the FILE's, not a
        limitation of ours."""
        page = read_page("pagexml", arabic_page)
        page.direction = "rtl"
        page.language = "Arabic"
        page.script = "Arab"

        data, _report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        assert b'readingDirection="right-to-left"' in data
        assert returned.direction == "rtl"
        assert returned.language == "Arabic"
        assert returned.script == "Arab"

    def test_the_arabic_survives_a_crossing_to_alto(self, arabic_page):
        """Through the model, not through a PAGE-to-ALTO path — and the text is what
        must survive a format that carries no direction at all."""
        page = read_page("pagexml", arabic_page)

        data, report = write_page("alto", page)
        crossed = read_page("alto", data)

        # The LINES survive. The region's own copy of the whole page text does not:
        # ALTO carries text on `String` elements only, so a reading attached to a region
        # has nowhere to go -- and that is DECLARED rather than silent, which is the
        # difference between a format's limit and a bug.
        crossed_lines = [
            text for s in crossed.segments if s.kind == "line" for _kind, text in s.readings
        ]
        original_lines = [
            text for s in page.segments if s.kind == "line" for _kind, text in s.readings
        ]
        assert crossed_lines == original_lines
        assert sum(_arabic_characters(t) for t in crossed_lines) > 50
        assert "text on a region" in report.lost
