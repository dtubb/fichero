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

from fichero_server.formats import format_for, read_page, write_page
from fichero_server.formats.alto import UnknownMeasurementUnit, _sniff

pytestmark = pytest.mark.source_model

FIXTURE = Path(__file__).parent / "fixtures" / "altoxml_glyph_00001.alto.xml"
PAGEXML_FIXTURE = Path(__file__).parent / "fixtures" / "ocrd_kant_0017.page.xml"


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


class TestAltoExportRefusesUntilItsSchemaIsVendored:
    """**The honest state of ALTO writing, pinned rather than hidden.**

    ALTO's XSD imports `http://www.loc.gov/standards/xlink/xlink.xsd`, which is not
    vendored: `loc.gov` refuses a script, and W3C's modern `xlink.xsd` is NOT a
    substitute — it defines `simpleAttrs` where ALTO references `simpleLink`, so
    mapping one to the other builds a schema missing the definitions ALTO uses.

    So every ALTO export refuses, by design: `write_page` validates before handing
    over bytes, and a file that cannot be validated must not be written. These tests
    pin THAT, so the day the schema is vendored they fail and tell whoever did it to
    enable the real assertions below — which is the opposite of a skip nobody
    notices.
    """

    def test_an_export_refuses_because_the_xlink_import_is_not_vendored(self):
        from fichero_server.formats.harness import PageSegment, SourcePage
        from fichero_server.formats.validation import UnvendoredSchemaImport

        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="word", ref="w1", rect=[0.1, 0.1, 0.1, 0.02],
                            readings=[("transcription", "dios")]),
            ],
        )

        with pytest.raises(UnvendoredSchemaImport) as raised:
            write_page("alto", page)
        assert "xlink" in str(raised.value)
        assert "validate vacuously" in str(raised.value)

    def test_the_bytes_are_NOT_written_when_validation_cannot_run(self):
        """The rule this protects: a file that exists and does not validate is one
        somebody sends to a colleague. "Cannot validate" is not "valid"."""
        from fichero_server.formats.harness import PageSegment, SourcePage
        from fichero_server.formats.validation import UnvendoredSchemaImport

        page = SourcePage(image_size=(1000, 1000), segments=[PageSegment(kind="word")])

        with pytest.raises(UnvendoredSchemaImport):
            write_page("alto", page)


@pytest.mark.skip(
    reason=(
        "ALTO export cannot be validated until the xlink schema ALTO imports is "
        "vendored (see schemas/PROVENANCE.md). The writer itself is complete and "
        "its losses are asserted by TestTheWriterNamesItsLossesWithoutValidating "
        "below, which exercises the same code without going through write_page."
    )
)
class TestWritingAltoDeclaresWhatItCannotCarry:
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


@pytest.mark.skip(reason="needs ALTO validation; see TestTheWriterNamesItsLossesWithoutValidating")
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
