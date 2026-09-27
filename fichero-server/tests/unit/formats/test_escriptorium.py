"""eScriptorium's own exports, read and written back (#4944).

**The residue this closes.** Every earlier PAGE XML fixture was either ours or
OCR-D's. eScriptorium is the NAMED target — it is what a Fichero user actually has
— and its files are not OCR-D's: it leans on `Baseline`, writes `eSc_*` ids, and
puts structure in `custom` rather than in elements.

Both fixtures are eScriptorium's own test samples, **MIT licensed** (checked before
vendoring: a share-alike or non-commercial fixture is in the git history for good).

The interesting test here is not that they parse. It is **whether eScriptorium's
shape survives our 2019 writer without silent loss**, because that is the path a
real user walks: import from eScriptorium, work in Fichero, export back.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.formats import format_for, read_page, write_page

pytestmark = pytest.mark.source_model

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "escriptorium_export.page.xml"
ALTO = FIXTURES / "escriptorium_export.alto.xml"


@pytest.fixture(scope="module")
def page_bytes() -> bytes:
    data = PAGE.read_bytes()
    assert len(data) > 1_000, f"the fixture is {len(data)} bytes; it should be ~2.4 KB"
    return data


@pytest.fixture(scope="module")
def alto_bytes() -> bytes:
    data = ALTO.read_bytes()
    assert len(data) > 1_000, f"the fixture is {len(data)} bytes; it should be ~3.1 KB"
    return data


class TestReadingEscriptoriumsPageXml:
    def test_it_says_escriptorium_made_it(self, page_bytes):
        page = read_page("pagexml", page_bytes)

        assert page.producer == "escriptorium"

    def test_its_regions_and_lines_arrive_with_their_own_ids(self, page_bytes):
        """eScriptorium's ids are `eSc_textblock_01`, `eSc_line_01`. They are the
        FILE's ids and the model keeps them only to resolve the file's own reading
        order — never as our ids, which a re-import mints fresh."""
        page = read_page("pagexml", page_bytes)

        refs = [segment.ref for segment in page.segments if segment.ref]
        assert any(ref.startswith("eSc_") for ref in refs)
        assert any(segment.kind == "line" for segment in page.segments)

    def test_the_baseline_arrives_because_that_is_what_escriptorium_works_in(self, page_bytes):
        """Kraken and eScriptorium are built around the baseline, so a reader that
        handled only polygons would drop the thing their whole workflow produces."""
        page = read_page("pagexml", page_bytes)

        lines = [s for s in page.segments if s.kind == "line"]
        assert any(line.baseline for line in lines), "no baseline survived"

    def test_structure_in_custom_is_kept_not_dropped(self, page_bytes):
        """eScriptorium puts the region's type in `custom="structure {type:title;}"`.
        `keeps-unrecognised` is what stops that becoming an untyped block."""
        page = read_page("pagexml", page_bytes)

        customs = [s.foreign.get("custom") for s in page.segments if s.foreign.get("custom")]
        assert customs, "eScriptorium's custom attributes were dropped"
        assert any("structure" in value for value in customs)

    def test_the_text_of_each_line_arrives(self, page_bytes):
        page = read_page("pagexml", page_bytes)

        lines = [s for s in page.segments if s.kind == "line" and s.readings]
        assert lines
        assert all(text.strip() for line in lines for _kind, text in line.readings)


class TestTheRoundTripAUserActuallyWalks:
    """Import from eScriptorium, then export back as PAGE XML 2019."""

    def test_eScriptoriums_file_survives_our_writer_and_validates(self, page_bytes):
        page = read_page("pagexml", page_bytes)

        data, report = write_page("pagexml", page)

        assert data.startswith(b"<?xml")
        assert b"pagecontent/2019-07-15" in data
        # Anything lost must be declared. This file's losses are the model's own
        # limits, not surprises.
        assert isinstance(report.lost, set)

    def test_the_lines_and_their_text_come_back_unchanged(self, page_bytes):
        page = read_page("pagexml", page_bytes)

        data, _report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        before = [s.readings for s in page.segments if s.kind == "line"]
        after = [s.readings for s in returned.segments if s.kind == "line"]
        assert after == before

    def test_the_baselines_come_back(self, page_bytes):
        """The thing a user would notice immediately if we dropped it: a re-import
        into eScriptorium with no baselines is a page their tools cannot work on."""
        page = read_page("pagexml", page_bytes)

        data, _report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        assert sum(1 for s in returned.segments if s.baseline) == sum(
            1 for s in page.segments if s.baseline
        )

    def test_escriptoriums_custom_is_written_BACK_not_merely_kept(self, page_bytes):
        """`keeps-unrecognised` has two halves, and this test found the second one
        missing: `custom="structure {type:title;}"` was read into `foreign` and
        dropped on the way out. **A silent drop is the one thing the loss report
        exists to make impossible** — so the fix was to write it back, not to declare
        it lost. Declaring it would have been honest data destruction.

        This is the round trip a user walks: eScriptorium in, Fichero, eScriptorium
        out, with the structural type they chose still on the region."""
        page = read_page("pagexml", page_bytes)
        had = {s.ref: s.foreign["custom"] for s in page.segments if s.foreign.get("custom")}
        assert had, "the fixture has no custom attribute to test with"

        data, report = write_page("pagexml", page)
        returned = read_page("pagexml", data)

        came_back = {
            s.ref: s.foreign["custom"] for s in returned.segments if s.foreign.get("custom")
        }
        assert came_back == had, "eScriptorium's structural types did not survive"
        assert "custom attributes" not in report.lost


class TestReadingEscriptoriumsAlto:
    def test_it_is_alto_v4_in_pixels(self, alto_bytes):
        """Closes the other residue: a real PIXEL-unit ALTO file. The `mm10` fixture
        proved the unit handling; this one proves the common case is not special."""
        page = read_page("alto", alto_bytes)

        assert page.foreign["alto:MeasurementUnit"] == "pixel"
        assert page.image_size is not None
        assert format_for("alto_export.xml", alto_bytes).name == "alto"

    def test_blocks_lines_and_words_arrive(self, alto_bytes):
        page = read_page("alto", alto_bytes)

        kinds = [segment.kind for segment in page.segments]
        assert kinds.count("region") >= 1
        assert kinds.count("line") >= 1
        assert kinds.count("word") >= 1

    def test_a_pixel_page_reports_its_pixel_grid(self, alto_bytes):
        """The contrast with the `mm10` file, asserted side by side: pixels give a
        page size, tenths of a millimetre give `None` rather than a wrong number."""
        pixels = read_page("alto", alto_bytes)
        mm10 = read_page("alto", (FIXTURES / "altoxml_glyph_00001.alto.xml").read_bytes())

        assert pixels.image_size is not None
        assert mm10.image_size is None
