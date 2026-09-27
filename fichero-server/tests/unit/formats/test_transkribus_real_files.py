"""Two real files from the Transkribus ecosystem, and what they broke (#4944).

Every format defect this programme has found came from somebody else's file or from
real data. **Not one came from a round trip**, because a round trip only proves we can
read what we wrote — and our writer never emitted a table, so no round trip could
have found the defect below.

Both files are BSD-3-Clause (NAVER LABS Europe, `Transkribus/TranskribusDU`), licence
read before fetching, recorded in `fixtures/PROVENANCE.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.formats import read_page, round_trip

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = FIXTURES / "transkribus_abp_table_0019.page.xml"
REGIONS_ONLY = FIXTURES / "transkribus_regions_only_0002.page.xml"


class TestATablePageWithCells:
    """`transkribus_abp_table_0019.page.xml` — a parish register: one `TableRegion`,
    172 `TableCell`s, 17 text regions, 355 lines each with a baseline, 2013 namespace.
    """

    @pytest.fixture
    def page(self):
        return read_page("pagexml", TABLE.read_bytes())

    def test_the_cells_are_read_as_regions_and_keep_their_place(self, page):
        """A cell IS a region — PAGE 2019 gives a `TextRegion` inside a `TableRegion`
        a `TableCellRole`, and the 2013 files Transkribus writes use a `TableCell`
        element for the same thing. Its row, column and spans ride in `foreign` until
        `source.segment.table-cells` (#4928) gives the model fields for them: dropping
        them would lose the one thing that makes a table a table, and inventing fields
        here would decide a behaviour this format does not own.
        """
        cells = [s for s in page.segments if "pagexml:row" in s.foreign]

        assert len(cells) == 172, "every cell is read"
        first = next(s for s in cells if s.foreign["pagexml:row"] == "0")
        assert first.foreign["pagexml:col"] is not None
        assert first.foreign["pagexml:rowSpan"] == "2", "a spanning cell keeps its span"

    def test_every_line_has_a_legal_parent(self, page):
        """THE DEFECT THIS FILE FOUND. Before 2026-09-27 `TableCell` was not in
        `ELEMENT_KINDS`, so the reader skipped cells and the parent walk climbed PAST
        them to the `TableRegion`. All 355 lines came back parented to the table — and
        PAGE XML's schema forbids a `TextLine` directly under a `TableRegion`, so the
        export refused with "This element is not expected". Import worked and export
        could not.
        """
        by_ref = {s.ref: s for s in page.segments if s.ref}
        lines = [s for s in page.segments if s.kind == "line" and s.parent_ref]

        assert lines, "the file has lines with parents"
        parents = {by_ref[s.parent_ref].kind for s in lines if s.parent_ref in by_ref}
        assert parents == {"region"}, (
            f"a line's parent must be a region (a cell is one); got {sorted(parents)}"
        )

    def test_the_page_round_trips_and_loses_nothing(self, page):
        """The acceptance test, and it could only fail on a real file: 576 segments out
        of 576, with no loss report — the table, its cells, its lines and their
        baselines all survive a write and a re-read."""
        back, report = round_trip("pagexml", page)

        assert len(back.segments) == len(page.segments) == 576
        assert [(loss.what, loss.count) for loss in report.losses] == []

    def test_empty_text_is_read_as_no_reading_rather_than_an_empty_one(self, page):
        """This file's `<TextEquiv><Unicode/></TextEquiv>` elements are EMPTY — it is
        layout ground truth, not a transcription. A reader that turned each into an
        empty reading would put 372 blank readings on the page and make an untranscribed
        register look transcribed."""
        assert sum(len(segment.readings) for segment in page.segments) == 0


class TestARegionsOnlyPage:
    """`transkribus_regions_only_0002.page.xml` — layout analysis output: three
    regions, three separators, a reading order, and NO lines and NO text at all.
    """

    @pytest.fixture
    def page(self):
        return read_page("pagexml", REGIONS_ONLY.read_bytes())

    def test_a_page_with_no_lines_and_no_text_is_read_not_refused(self, page):
        """A page that has been segmented and not transcribed is an ordinary state, not
        an error: it is what every page looks like between layout analysis and OCR."""
        kinds = {segment.kind for segment in page.segments}

        assert kinds == {"region", "separator"}
        assert sum(len(segment.readings) for segment in page.segments) == 0

    def test_its_reading_order_over_regions_survives(self, page):
        """The order is the only claim the file makes about sequence, and it is over
        REGIONS — a reader that only ordered lines would drop it silently."""
        assert len(page.orders) == 1
        assert len(page.orders[0].refs) == 3

    def test_it_round_trips(self, page):
        back, report = round_trip("pagexml", page)

        assert len(back.segments) == len(page.segments)
        assert [(loss.what, loss.count) for loss in report.losses] == []
