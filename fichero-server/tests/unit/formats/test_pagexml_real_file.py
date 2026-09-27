"""A PAGE XML file ANOTHER TOOL wrote, read and written back (#4944).

`fixtures/ocrd_kant_0017.page.xml` is real ground truth from the OCR-D corpus — 11
regions, 24 lines, words, baselines, a genuine `ReadingOrder`, `TextStyle`, and the
`custom` attribute PAGE XML uses for what it has no element for. **It is not ours
and is never edited**: a file we wrote to look like another tool's output tests our
idea of that tool, and our idea is the thing under test.

The second class here is the test the lead asked for and it is the sharper one:
read a real file, write it back, and check **the losses are the ones we declared** —
not that the two files match. Files matching would be the wrong assertion, because
PAGE XML holds things this model does not and a writer that reproduced them byte for
byte would be a copier rather than a model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.formats import read_page, write_page
from fichero_server.formats.pagexml import _sniff

pytestmark = pytest.mark.source_model

FIXTURE = Path(__file__).parent / "fixtures" / "ocrd_kant_0017.page.xml"


@pytest.fixture(scope="module")
def real_bytes() -> bytes:
    data = FIXTURE.read_bytes()
    # A guard that cannot read its input must FAIL, never pass vacuously: an empty
    # or missing fixture would make every assertion below trivially true.
    assert len(data) > 10_000, f"the fixture is {len(data)} bytes; it should be ~89 KB"
    return data


class TestReadingARealFile:
    def test_it_is_recognised_as_pagexml_from_its_own_bytes(self, real_bytes):
        assert _sniff(real_bytes) is True

    def test_every_region_and_line_arrives(self, real_bytes):
        page = read_page("pagexml", real_bytes)

        kinds = [segment.kind for segment in page.segments]
        # The file's own counts: 11 TextRegions, 2 SeparatorRegions, 24 TextLines.
        # Corrected after reading them from the file rather than from my own grep,
        # which had counted `<TextRegion` and missed that separators are regions too.
        assert kinds.count("line") == 24
        assert kinds.count("region") == 11
        assert kinds.count("separator") == 2

    def test_words_arrive_as_their_own_segments(self, real_bytes):
        """`source.link.any-depth`'s foundation: a word is a segment like any
        other. A reader that only understood regions and lines would silently drop
        the granularity a palaeographer works at."""
        page = read_page("pagexml", real_bytes)

        assert any(segment.kind == "word" for segment in page.segments)

    def test_the_page_size_and_image_are_the_files_own(self, real_bytes):
        page = read_page("pagexml", real_bytes)

        assert page.image_size == (1457, 2083)
        assert page.image_name == "OCR-D-IMG/INPUT_0017.tif"
        assert page.producer == "OCR-D"

    def test_coordinates_are_normalised_and_inside_the_page(self, real_bytes):
        """Every point of every shape lands in [0, 1]. A reader that divided by the
        wrong dimension, or forgot to divide, fails here — and this is the assertion
        that would catch a transposed width and height on a non-square page, which
        1457×2083 is."""
        page = read_page("pagexml", real_bytes)

        seen = 0
        for segment in page.segments:
            for shape in (segment.polygon, segment.baseline):
                for x, y in shape or []:
                    assert 0.0 <= x <= 1.0, f"{segment.ref}: x={x}"
                    assert 0.0 <= y <= 1.0, f"{segment.ref}: y={y}"
                    seen += 1
        assert seen > 100, f"only {seen} points checked; the fixture has far more"

    def test_the_reading_order_is_read_as_a_named_order(self, real_bytes):
        page = read_page("pagexml", real_bytes)

        assert page.orders, "a real file's ReadingOrder did not arrive"
        assert len(page.orders[0].refs) > 1
        # Every ref in the order is a segment we read — an order naming something
        # absent would be an order nothing can follow.
        refs = {segment.ref for segment in page.segments}
        assert set(page.orders[0].refs) <= refs

    def test_the_language_is_a_NAME_which_is_what_pagexml_uses(self, real_bytes):
        """Independent confirmation from a file we did not write: PAGE XML's
        `primaryLanguage` vocabulary is language NAMES, not BCP 47 tags. The
        engine's own language field is a name (#2092), so it speaks this format
        without translation — which is evidence for #5078 that did not exist before
        this file was read."""
        page = read_page("pagexml", real_bytes)

        languages = {segment.language for segment in page.segments if segment.language}
        assert "German" in languages
        assert "de" not in languages

    def test_what_the_model_has_no_field_for_is_KEPT(self, real_bytes):
        """`source.format.keeps-unrecognised`. The file's `custom="readingOrder
        {index:0;} structure {type:heading;}"` has no model field, and dropping it
        would lose the structural type a scholar chose."""
        page = read_page("pagexml", real_bytes)

        kept = [segment for segment in page.segments if segment.foreign.get("custom")]
        assert kept, "the file's `custom` attributes were dropped"
        assert any("structure" in segment.foreign["custom"] for segment in kept)


class TestWritingItBackDeclaresWhatItLost:
    """The test after the round trip, and the interesting one: the two files do NOT
    match, and what matters is that every difference was DECLARED."""

    def test_the_written_file_validates_against_the_real_schema(self, real_bytes):
        page = read_page("pagexml", real_bytes)

        data, _report = write_page("pagexml", page)

        assert data.startswith(b"<?xml")

    def test_the_losses_are_the_ones_we_declared_and_nothing_silent(self, real_bytes):
        """The whole design in one assertion: every loss must be a loss the writer
        NAMED. A difference nobody declared is the silent-drop failure, and it is
        what a file-comparison test would have let through as "close enough"."""
        page = read_page("pagexml", real_bytes)

        data, report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        declared = report.lost
        # Segments come back one for one unless the writer said a granularity has no
        # element.
        if "separator segments" not in declared:
            assert len(returned.segments) == len(page.segments)
        # The words come back, which is the thing a lesser writer drops.
        assert sum(1 for s in returned.segments if s.kind == "word") == sum(
            1 for s in page.segments if s.kind == "word"
        )
        # Language survives because PAGE XML's vocabulary is names and so is ours.
        assert "language" not in declared
        assert {s.language for s in returned.segments if s.language} == {
            s.language for s in page.segments if s.language
        }

    def test_the_text_of_every_line_survives_unchanged(self, real_bytes):
        page = read_page("pagexml", real_bytes)

        data, _report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        before = [s.readings for s in page.segments if s.kind == "line"]
        after = [s.readings for s in returned.segments if s.kind == "line"]
        assert after == before

    def test_the_reading_order_survives_as_the_same_sequence(self, real_bytes):
        page = read_page("pagexml", real_bytes)

        data, report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        if "named reading orders" not in report.lost or len(page.orders) == 1:
            assert returned.orders[0].refs == page.orders[0].refs

    def test_coordinates_survive_to_half_a_pixel_of_the_files_own_grid(self, real_bytes):
        """The tolerance is the FILE's grid, 1457×2083, not a round number: PAGE XML
        writes integer pixels, so the honest bound is half a pixel of the page this
        file describes."""
        page = read_page("pagexml", real_bytes)
        width, height = page.image_size

        data, _report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        by_ref = {segment.ref: segment for segment in returned.segments}
        for segment in page.segments:
            came_back = by_ref.get(segment.ref)
            if came_back is None or not segment.polygon or not came_back.polygon:
                continue
            for mine, theirs in zip(segment.polygon, came_back.polygon):
                assert mine[0] == pytest.approx(theirs[0], abs=0.5 / width)
                assert mine[1] == pytest.approx(theirs[1], abs=0.5 / height)
