"""ALTO, read from a real file and written back (#4944).

`fixtures/altoxml_glyph_00001.alto.xml` is real ALTO from the ALTO project's own
corpus — **a different producer from OCR-D's PAGE XML**, which is how you find out
which parts of a format are agreed on and which are one tool's habit. It declares
**`MeasurementUnit` `mm10`**, tenths of a millimetre, which is the trap: a reader
assuming pixels is wrong by a factor on every shape and nothing looks broken.

The last class here is the one-harness test: **PAGE XML in, ALTO out, through the
model** — never a PAGE-to-ALTO path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.formats import format_for, read_page, round_trip, write_page
from fichero_server.formats.alto import UnknownMeasurementUnit, _sniff

pytestmark = pytest.mark.source_model

FIXTURE = Path(__file__).parent / "fixtures" / "altoxml_glyph_00001.alto.xml"
PAGEXML_FIXTURE = Path(__file__).parent / "fixtures" / "ocrd_gt_aepinus_0020.page.xml"


@pytest.fixture(scope="module")
def real_alto() -> bytes:
    data = FIXTURE.read_bytes()
    # A guard that cannot read its input must fail rather than pass vacuously.
    assert len(data) > 10_000, f"the fixture is {len(data)} bytes; it should be ~40 KB"
    return data


class TestTheMeasurementUnitIsHandledNotAssumed:
    def test_the_unit_is_read_and_kept(self, real_alto):
        page = read_page("alto", real_alto)

        assert page.foreign["alto:MeasurementUnit"] == "mm10"

    def test_a_non_pixel_page_reports_NO_pixel_size_rather_than_a_wrong_one(self, real_alto):
        """`image_size` means a PIXEL grid in the model. `1003 x 1469` tenths of a
        millimetre is not pixels, and converting needs a resolution ALTO need not
        state — so it is absent and the unit is recorded. **A page size silently 10×
        wrong is worse than an absent one.**"""
        page = read_page("alto", real_alto)

        assert page.image_size is None

    def test_coordinates_are_unit_free_because_the_page_declares_its_own_size(self, real_alto):
        """The property that makes storing FRACTIONS right rather than lucky:
        `HPOS / Page@WIDTH` cancels the unit, so the geometry is correct whether the
        file counts pixels or tenths of a millimetre."""
        page = read_page("alto", real_alto)

        seen = 0
        for segment in page.segments:
            for x, y in segment.polygon or []:
                assert 0.0 <= x <= 1.0, f"{segment.ref}: x={x}"
                assert 0.0 <= y <= 1.0, f"{segment.ref}: y={y}"
                seen += 1
        assert seen > 100, f"only {seen} points checked"

    def test_an_unknown_unit_is_REFUSED_and_not_assumed_to_be_pixels(self):
        hostile = b"""<?xml version="1.0"?>
        <alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
          <Description><MeasurementUnit>furlongs</MeasurementUnit></Description>
          <Layout><Page ID="P1" WIDTH="100" HEIGHT="100"/></Layout>
        </alto>"""

        with pytest.raises(UnknownMeasurementUnit) as raised:
            read_page("alto", hostile)
        assert "wrong place by a factor" in str(raised.value)


class TestReadingARealAltoFile:
    def test_blocks_lines_and_words_arrive_with_their_granularity(self, real_alto):
        page = read_page("alto", real_alto)

        kinds = [segment.kind for segment in page.segments]
        assert kinds.count("region") == 7
        assert kinds.count("line") == 27
        # ALTO's `String` IS a word -- no ambiguity, which is one place ALTO is
        # clearer than PAGE XML.
        assert kinds.count("word") == 209

    def test_the_words_carry_their_text(self, real_alto):
        page = read_page("alto", real_alto)

        words = [s for s in page.segments if s.kind == "word" and s.readings]
        assert len(words) > 100
        assert all(text.strip() for _kind, text in words[0].readings)

    def test_nesting_is_read_from_the_files_own_ids(self, real_alto):
        page = read_page("alto", real_alto)

        lines = [s for s in page.segments if s.kind == "line"]
        regions = {s.ref for s in page.segments if s.kind == "region"}
        assert all(line.parent_ref in regions for line in lines)

    def test_the_block_order_becomes_the_as_written_order(self, real_alto):
        """ALTO has NO reading-order element: the order is the document order of its
        blocks. Naming that `as-written` is honest — it is what the file says, and
        the file cannot say anything else."""
        page = read_page("alto", real_alto)

        assert page.orders
        assert page.orders[0].name == "as-written"
        assert len(page.orders[0].refs) == 7

    def test_it_is_recognised_as_alto_and_not_as_pagexml(self, real_alto):
        assert _sniff(real_alto) is True
        assert format_for("00001.xml", real_alto).name == "alto"


class TestWritingAltoDeclaresWhatItCannotCarry:
    """The strict xfail that guarded #5084's ALTO half is gone: the writer now invents
    the parent ALTO's schema requires, marks it, and drops it again on re-import."""

    def test_a_language_NAME_cannot_be_written_and_is_reported(self):
        """**The two formats disagree**: ALTO's `LANG` is `xsd:language`, a BCP 47
        TAG; PAGE XML's `primaryLanguage` is a closed list of NAMES. So whichever
        the model stores, one of the two exports has to map — which is evidence for
        #5078 that neither choice avoids a mapping."""
        from fichero_server.formats.harness import PageSegment, SourcePage

        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="word", ref="w1", language="Spanish",
                            rect=[0.1, 0.1, 0.1, 0.02],
                            readings=[("transcription", "dios")]),
            ],
        )

        _data, report = write_page("alto", page)

        assert "language" in report.lost
        assert any("PAGE XML is the opposite" in loss.why for loss in report.losses)

    def test_a_tag_IS_written_because_that_is_what_alto_takes(self):
        from fichero_server.formats.harness import PageSegment, SourcePage

        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="word", ref="w1", language="es",
                            rect=[0.1, 0.1, 0.1, 0.02],
                            readings=[("transcription", "dios")]),
            ],
        )

        data, report = write_page("alto", page)

        assert b'LANG="es"' in data
        assert "language" not in report.lost

    def test_script_and_direction_are_declared_losses(self):
        from fichero_server.formats.harness import PageSegment, SourcePage

        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="word", ref="w1", script="Arab", direction="rtl",
                            rect=[0.1, 0.1, 0.1, 0.02],
                            readings=[("transcription", "دios")]),
            ],
        )

        _data, report = write_page("alto", page)

        assert "script" in report.lost
        assert "direction" in report.lost


class TestOneModelOneHarness:
    """**PAGE XML in, ALTO out, through the model** — never a PAGE-to-ALTO path.

    This is the test that would fail if somebody added a direct converter: the only
    thing between the two formats is `SourcePage`, so a PAGE XML file becomes ALTO
    by being READ and then WRITTEN, and every difference between the formats shows
    up in the loss report rather than in a pairwise mapping table.
    """

    def test_a_real_pagexml_file_becomes_valid_alto_through_the_model(self):
        page = read_page("pagexml", PAGEXML_FIXTURE.read_bytes())

        data, report = write_page("alto", page)

        assert data.startswith(b"<?xml")
        assert b"alto/ns-v4" in data
        # And the conversion is honest about the crossing: PAGE XML carries a
        # language NAME, which ALTO cannot express.
        assert "language" in report.lost

    def test_the_words_survive_the_crossing(self):
        page = read_page("pagexml", PAGEXML_FIXTURE.read_bytes())
        words_in = [s for s in page.segments if s.kind == "word"]

        data, _report = write_page("alto", page)
        crossed = read_page("alto", data)

        words_out = [s for s in crossed.segments if s.kind == "word"]
        assert len(words_out) == len(words_in)

    def test_the_regions_keep_their_sequence_across_the_crossing(self):
        """PAGE XML's `ReadingOrder` has no ALTO element, so the one thing a writer
        can do is emit the blocks in that sequence — the order survives as document
        order, which is all ALTO can say."""
        page = read_page("pagexml", PAGEXML_FIXTURE.read_bytes())
        wanted = page.orders[0].refs

        data, _report = write_page("alto", page)
        crossed = read_page("alto", data)

        got = [s.ref for s in crossed.segments if s.kind == "region"]
        assert [ref for ref in got if ref in wanted] == [
            ref for ref in wanted if ref in got
        ]


class TestTheWriterNamesItsLossesWithoutValidating:
    """The writer's LOSS REPORTING, exercised without `write_page`'s validation.

    Skipping the writer tests entirely while its schema is missing would leave the
    loss report — the part this design rests on — untested for as long as the schema
    takes. So these call the writer directly with a report, which is what
    `write_page` does before it validates.
    """

    @staticmethod
    def _write(page):
        from fichero_server.formats.alto import write
        from fichero_server.formats.harness import LossReport

        report = LossReport(format="alto")
        data = write(page, report)
        return data, report

    def test_a_language_NAME_cannot_be_written_and_is_reported(self):
        """**The two formats disagree**: ALTO's `LANG` is `xsd:language`, a BCP 47
        TAG; PAGE XML's `primaryLanguage` is a closed list of NAMES. So whichever the
        model stores, one of the two exports has to map — evidence for #5078 that
        neither choice avoids a mapping."""
        from fichero_server.formats.harness import PageSegment, SourcePage

        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="word", ref="w1", language="Spanish",
                            rect=[0.1, 0.1, 0.1, 0.02],
                            readings=[("transcription", "dios")]),
            ],
        )

        _data, report = self._write(page)

        assert "language" in report.lost
        assert any("PAGE XML is the opposite" in loss.why for loss in report.losses)

    def test_a_tag_IS_written_because_that_is_what_alto_takes(self):
        from fichero_server.formats.harness import PageSegment, SourcePage

        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="word", ref="w1", language="es",
                            rect=[0.1, 0.1, 0.1, 0.02],
                            readings=[("transcription", "dios")]),
            ],
        )

        data, report = self._write(page)

        assert b'LANG="es"' in data
        assert "language" not in report.lost

    def test_script_and_direction_are_declared_losses(self):
        from fichero_server.formats.harness import PageSegment, SourcePage

        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="word", ref="w1", script="Arab", direction="rtl",
                            rect=[0.1, 0.1, 0.1, 0.02],
                            readings=[("transcription", "\u062f")]),
            ],
        )

        _data, report = self._write(page)

        assert "script" in report.lost
        assert "direction" in report.lost

    def test_a_pagexml_file_crosses_to_alto_through_the_model(self):
        """`one-model-one-harness`: PAGE XML in, ALTO out, and the only thing between
        them is `SourcePage`. This is the test that would fail if somebody added a
        direct PAGE-to-ALTO path."""
        page = read_page("pagexml", PAGEXML_FIXTURE.read_bytes())

        data, report = self._write(page)

        assert b"alto/ns-v4" in data
        crossed_words = data.count(b"<String")
        assert crossed_words == sum(1 for s in page.segments if s.kind == "word")
        # Honest about the crossing: PAGE XML carries a language NAME, ALTO cannot.
        assert "language" in report.lost


class TestTheImplicitParentIsWrittenAndMarked:
    """#5084, both halves of it: **write what the schema demands, mark it, and give
    back what the source said.**

    PAGE XML requires a `TextLine` inside a region and a `Word` inside a line; ALTO
    requires a `String` inside a `TextLine` inside a `TextBlock`. The model allows a
    line nobody put in a region — a marginal note drawn on its own is one. So the
    parent is invented because the format requires it, and marked so a re-import
    returns the page the source described rather than a region nobody drew.

    That is the off-page ruling applied to structure instead of geometry: the format's
    demand is met, and the difference between the file and the page is recorded.
    """

    def _orphan_word(self):
        from fichero_server.formats.harness import PageSegment, SourcePage

        return SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(
                    kind="word", ref="w1", rect=[0.1, 0.1, 0.1, 0.02],
                    readings=[("transcription", "solo")],
                ),
            ],
        )

    def test_alto_invents_the_block_and_line_a_word_needs(self):
        data, report = write_page("alto", self._orphan_word())

        assert b"TextBlock" in data and b"TextLine" in data
        assert b"fichero-implicit-" in data
        assert "implicit parents" in report.lost

    def test_pagexml_invents_the_region_and_line_a_word_needs(self):
        data, report = write_page("pagexml", self._orphan_word())

        assert b"TextRegion" in data and b"TextLine" in data
        assert b"fichero {implicit:true;}" in data
        assert "implicit parents" in report.lost

    @pytest.mark.parametrize("name", ["alto", "pagexml"])
    def test_a_re_import_returns_the_word_with_NO_invented_parent(self, name):
        """The marking earning its place: a scholar who exports and re-imports must get
        their one word back, not a word inside a region they never drew."""
        data, _report = write_page(name, self._orphan_word())

        returned = read_page(name, data)

        kinds = [segment.kind for segment in returned.segments]
        assert kinds == ["word"], kinds
        assert returned.segments[0].parent_ref is None
        assert not any(
            (segment.ref or "").startswith("fichero-implicit-")
            for segment in returned.segments
        )

    def test_a_real_page_with_proper_parents_invents_nothing(self):
        """The other half of the claim: nothing is invented when the source HAS the
        structure. A writer that wrapped everything would pass the tests above and
        produce phantom blocks on every real page."""
        page = read_page("pagexml", PAGEXML_FIXTURE.read_bytes())

        data, report = write_page("pagexml", page)

        assert b"fichero-implicit-" not in data
        assert "implicit parents" not in report.lost

    def test_the_invented_parent_is_exactly_as_big_as_its_child(self):
        """It claims nothing extra about the page: a box the size of the thing inside
        it is the least the format will accept."""
        data, _report = write_page("pagexml", self._orphan_word())

        returned_all = read_page("pagexml", data)
        assert len(returned_all.segments) == 1  # the parent is dropped on read
        # And in the bytes, the invented region carries the word's own box.
        assert data.count(b"100,100") >= 2


class TestTheAltoRoundTrip:
    """`source.format.round-trip-alto`, now that ALTO validates (xlink vendored, #5082).

    The round trip subtracts exactly what the loss report names — and for ALTO that is
    a long list, because it carries geometry and text and almost nothing else.
    """

    def _page(self):
        from fichero_server.formats.harness import PageOrder, PageSegment, SourcePage

        return SourcePage(
            image_name="folio.tif",
            image_size=(1000, 2000),
            segments=[
                PageSegment(kind="region", ref="b1", rect=[0.1, 0.1, 0.8, 0.2]),
                PageSegment(kind="line", ref="l1", parent_ref="b1",
                            rect=[0.1, 0.1, 0.8, 0.05]),
                PageSegment(kind="word", ref="w1", parent_ref="l1",
                            rect=[0.1, 0.1, 0.2, 0.05], language="es",
                            readings=[("transcription", "dios")]),
                PageSegment(kind="word", ref="w2", parent_ref="l1",
                            rect=[0.35, 0.1, 0.2, 0.05], language="es",
                            readings=[("transcription", "nombre")]),
            ],
            orders=[PageOrder(name="as-written", refs=["b1"])],
        )

    def test_the_structure_and_nesting_survive(self):
        from fichero_server.formats import round_trip

        returned, _report = round_trip("alto", self._page())

        by_ref = {s.ref: s for s in returned.segments}
        assert set(by_ref) >= {"b1", "l1", "w1", "w2"}
        assert by_ref["l1"].parent_ref == "b1"
        assert by_ref["w1"].parent_ref == "l1"

    def test_the_words_and_their_text_survive(self):
        from fichero_server.formats import round_trip

        returned, _report = round_trip("alto", self._page())

        words = {s.ref: s.readings for s in returned.segments if s.kind == "word"}
        assert words["w1"] == [("transcription", "dios")]
        assert words["w2"] == [("transcription", "nombre")]

    def test_a_tag_language_survives_where_a_name_would_not(self):
        from fichero_server.formats import round_trip

        returned, report = round_trip("alto", self._page())

        assert {s.language for s in returned.segments if s.language} == {"es"}
        assert "language" not in report.lost

    def test_boxes_survive_to_a_pixel_of_the_declared_page(self):
        from fichero_server.formats import round_trip

        page = self._page()
        returned, _report = round_trip("alto", page)

        by_ref = {s.ref: s for s in returned.segments}
        for segment in page.segments:
            mine, theirs = segment.rect, by_ref[segment.ref].rect
            assert mine[0] == pytest.approx(theirs[0], abs=1 / 1000)
            assert mine[1] == pytest.approx(theirs[1], abs=1 / 2000)

    def test_what_alto_cannot_hold_is_named_and_subtracted(self):
        """The report is the specification of the round trip: script, direction and
        several readings have no ALTO home, and the comparison above never asked for
        them."""
        from fichero_server.formats import round_trip
        from fichero_server.formats.harness import PageSegment

        page = self._page()
        page.segments.append(
            PageSegment(kind="word", ref="w3", parent_ref="l1",
                        rect=[0.6, 0.1, 0.2, 0.05], script="Latn", direction="rtl",
                        readings=[("transcription", "uno"), ("transcription", "una")])
        )

        returned, report = round_trip("alto", page)

        assert {"script", "direction", "several readings"} <= report.lost
        word = next(s for s in returned.segments if s.ref == "w3")
        assert word.script is None and word.direction is None
        assert len(word.readings) == 1


class TestARealHebrewExportStatesItsLanguageWhereAltoDoesNotAllowIt:
    """kraken's own ALTO fixture (Apache-2.0), an eScriptorium export of a Hebrew
    manuscript: `<Page ... LANG="hbo">`, in a file that DECLARES ALTO 4.3, where `Page`
    has no `LANG`. ALTO 4.4 added it.

    The file is non-conformant to the version it names and the fact it states is true: a
    reader that obeyed only the declared schema would drop a real page's language. Our
    writer emits 4.4 (ruled 2026-09-27: we export the latest schema), so the fact is
    written back and our export validates.
    """

    FIXTURE = Path(__file__).parent / "fixtures" / "kraken_alto_multilingual_bsb00084914.alto.xml"

    def test_the_pages_language_is_read_although_the_schema_forbids_it_there(self):
        page = read_page("alto", self.FIXTURE.read_bytes())

        assert page.language == "hbo", (
            "a language the file states is a fact, even when stated in the wrong place"
        )

    def test_three_languages_in_one_file_and_each_lands_where_it_belongs(self):
        """'Any language' is the north star, and this is the first fixture with more
        than one: the page is Ancient Hebrew (`hbo`) and two lines declare `heb` and
        `iai` of their own. A reader that took the page's language for the lines'
        would erase the distinction between the manuscript's language and a line's."""
        page = read_page("alto", self.FIXTURE.read_bytes())

        per_segment = sorted(
            segment.language for segment in page.segments if segment.language
        )
        assert page.language == "hbo"
        assert per_segment == ["heb", "iai"]

    def test_the_page_language_is_written_back_in_4_4_and_is_no_longer_a_loss(self):
        """Until the writer moved to 4.4 this was a declared loss, because 4.2 had nowhere
        for a page's language. `write_page` validates against 4.4 on the way out, so the
        round trip passing is the export validating."""
        page = read_page("alto", self.FIXTURE.read_bytes())

        back, report = round_trip("alto", page)

        assert back.language == "hbo"
        assert "the page's language" not in report.lost

    def test_a_language_NAME_on_the_page_is_still_a_loss_not_an_invalid_file(self):
        """`Page@LANG` is `xsd:language`, a BCP 47 tag. A NAME ("Hebrew", what PAGE XML
        stores) would fail the schema, so it is reported and not written."""
        page = read_page("alto", self.FIXTURE.read_bytes())
        page.language = "Hebrew"

        back, report = round_trip("alto", page)

        assert back.language is None
        assert "the page's language" in report.lost

    def test_the_lines_own_languages_do_survive_the_round_trip(self):
        """Per-element `LANG` is where ALTO does allow it, so those must come back —
        otherwise the loss above would look like a whole-file limitation rather than a
        page-level one."""
        page = read_page("alto", self.FIXTURE.read_bytes())

        back, _report = round_trip("alto", page)

        assert sorted(s.language for s in back.segments if s.language) == ["heb", "iai"]

    def test_the_file_round_trips_otherwise_intact(self):
        page = read_page("alto", self.FIXTURE.read_bytes())

        back, _report = round_trip("alto", page)

        assert len(back.segments) == len(page.segments) == 122
        assert sum(len(s.readings) for s in back.segments) == 86


class TestAnUntranscribedPageExportsValid:
    """#5130: 15 of 239 real pages (ottoman, occitan, makhzan, aljamiado) were refused
    because our writer emitted `<String>` without the required CONTENT. A segmented page
    nobody has transcribed yet is the ORDINARY state, so this is pinned on a minimal file
    of our own -- three of those four sets are NonCommercial and cannot be vendored.

    Decided against the schema, deliberately: a TextLine must hold at least one String
    and `CONTENT` is required but may be empty, so the answer is `CONTENT=""`, not "no
    String".
    """

    SOURCE = b"""
        <?xml version="1.0" encoding="UTF-8"?>
        <alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
          <Description><MeasurementUnit>pixel</MeasurementUnit></Description>
          <Layout><Page ID="p" WIDTH="1000" HEIGHT="1000" PHYSICAL_IMG_NR="1">
            <PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="1000">
              <TextBlock ID="b1" HPOS="100" VPOS="100" WIDTH="800" HEIGHT="300">
                <TextLine ID="l1" HPOS="100" VPOS="100" WIDTH="800" HEIGHT="50">
                  <String ID="w1" HPOS="100" VPOS="100" WIDTH="200" HEIGHT="50" CONTENT=""/>
                  <String ID="w2" HPOS="320" VPOS="100" WIDTH="200" HEIGHT="50" CONTENT="read"/>
                </TextLine>
                <TextLine ID="l2" HPOS="100" VPOS="200" WIDTH="800" HEIGHT="50">
                  <String ID="w3" HPOS="100" VPOS="200" WIDTH="800" HEIGHT="50" CONTENT=""/>
                </TextLine>
              </TextBlock>
            </PrintSpace>
          </Page></Layout>
        </alto>
    """.strip()

    def test_untranscribed_words_and_lines_export_valid(self):
        page = read_page("alto", self.SOURCE)
        data, _ = write_page("alto", page)  # validates against ALTO 4.4, or raises InvalidExport
        assert data.count(b'CONTENT=""') == 2

    def test_a_line_with_no_words_and_no_text_still_exports_valid(self):
        """The other half: a converted page's line with no words and no reading got no
        String at all, which the schema refuses as surely as a String with no CONTENT."""
        page = read_page("alto", self.SOURCE)
        page.segments = [s for s in page.segments if s.kind != "word"]
        for segment in page.segments:
            segment.readings = []
        data, _ = write_page("alto", page)
        assert data.count(b"<String") == 2 and data.count(b'CONTENT=""') == 2

    def test_an_empty_content_comes_back_as_no_reading_not_an_empty_one(self):
        page = read_page("alto", self.SOURCE)
        back, _ = round_trip("alto", page)
        words = [s for s in back.segments if s.kind == "word"]
        assert [s.readings for s in words] == [[], [("transcription", "read")], []]
