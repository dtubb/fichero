"""TEI XML, in and out (#4945: `source.format.tei-in`, `.tei-out`, `.round-trip-tei`).

Two kinds of test, on purpose. The round trip (class 1) proves the writer and reader agree,
and **two halves sharing one mistake agree perfectly** -- so every assertion is against the MODEL
page built here, never against what our own writer emitted, and the export is validated against
TEI's real `tei_all.xsd` by the harness before it is handed back. The real-file class (2) reads the
TEI Consortium's own transcription test file (`fixtures/tei_consortium_testtranscr.xml`, CC BY 3.0 / BSD-2, a
file another project wrote and we never edit) and writes it back: that is the only thing here that can break the symmetry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.formats import (
    InvalidExport,
    format_for,
    read_page,
    round_trip,
    validate,
    format_named,
    write_page,
)
from fichero_server.formats.harness import PageOrder, PageSegment, SourcePage
from fichero_server.formats import tei

pytestmark = pytest.mark.source_model

FIXTURE = Path(__file__).parent / "fixtures" / "tei_consortium_testtranscr.xml"

ARABIC = "بسم الله الرحمن الرحيم"


def _page() -> SourcePage:
    return SourcePage(
        producer="Fichero",
        image_name="folio_12r.jpg",
        image_size=(1000, 2000),
        segments=[
            PageSegment(kind="region", ref="r1", language="Arabic", script="Arab", direction="rtl",
                        polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.2], [0.1, 0.2]]),
            PageSegment(kind="line", ref="l1", parent_ref="r1", language="Arabic", script="Arab",
                        direction="rtl",
                        polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.15], [0.1, 0.15]],
                        baseline=[[0.1, 0.145], [0.9, 0.145]],
                        readings=[("transcription", ARABIC)]),
            PageSegment(kind="region", ref="r2", language="Spanish", script="Latn", direction="ltr",
                        polygon=[[0.1, 0.3], [0.9, 0.3], [0.9, 0.4], [0.1, 0.4]]),
            PageSegment(kind="line", ref="l2", parent_ref="r2", language="Spanish", script="Latn",
                        polygon=[[0.1, 0.3], [0.9, 0.3], [0.9, 0.35], [0.1, 0.35]],
                        readings=[("transcription", "En el año de nuestro Señor")]),
        ],
        orders=[PageOrder(name="as-written", refs=["r1", "r2"])],
    )


class TestTheRoundTripHolds:
    def test_every_segment_comes_back_with_its_granularity_and_nesting(self):
        original = _page()
        returned, _ = round_trip("tei", original)
        assert [s.kind for s in returned.segments] == ["region", "line", "region", "line"]
        parents = {s.ref: s.parent_ref for s in returned.segments}
        first_region, first_line = returned.segments[0], returned.segments[1]
        assert first_line.parent_ref == first_region.ref
        assert returned.segments[3].parent_ref == returned.segments[2].ref
        assert parents[first_region.ref] is None

    def test_language_script_and_direction_survive_both_ways(self):
        """Against the ORIGINAL's values: a writer dropping `direction` and a reader that
        defaults it would agree with each other and tell us nothing."""
        original = _page()
        returned, report = round_trip("tei", original)
        for came, was in zip(returned.segments, original.segments):
            assert came.language == was.language
            assert came.script == was.script
            assert came.direction == was.direction
        assert "direction" not in report.lost and "language" not in report.lost

    def test_the_text_survives_byte_for_byte_including_right_to_left(self):
        returned, _ = round_trip("tei", _page())
        assert returned.segments[1].readings == [("transcription", ARABIC)]
        assert returned.segments[3].readings == [("transcription", "En el año de nuestro Señor")]

    def test_shapes_and_baselines_come_back_to_the_pixel(self):
        original = _page()
        returned, _ = round_trip("tei", original)
        def flat(points):
            return [c for point in points for c in point]

        for came, was in zip(returned.segments, original.segments):
            assert flat(came.polygon) == pytest.approx(flat(was.polygon), abs=1 / 1000)
        assert flat(returned.segments[1].baseline) == pytest.approx(flat(original.segments[1].baseline), abs=1 / 1000)
        assert returned.image_size == (1000, 2000) and returned.image_name == "folio_12r.jpg"

    def test_the_reading_order_comes_back_as_a_sequence(self):
        returned, _ = round_trip("tei", _page())
        regions = [s.ref for s in returned.segments if s.kind == "region"]
        assert returned.orders[0].refs == regions

    def test_words_are_segments_inside_their_line(self):
        page = _page()
        page.segments.append(PageSegment(kind="word", ref="w1", parent_ref="l2",
                                         polygon=[[0.1, 0.3], [0.3, 0.3], [0.3, 0.35], [0.1, 0.35]],
                                         readings=[("transcription", "En")]))
        page.segments.append(PageSegment(kind="word", ref="w2", parent_ref="l2",
                                         polygon=[[0.31, 0.3], [0.5, 0.3], [0.5, 0.35], [0.31, 0.35]],
                                         readings=[("transcription", "el")]))
        page.segments[3].readings = [("transcription", "En el")]
        returned, report = round_trip("tei", page)
        words = [s for s in returned.segments if s.kind == "word"]
        assert [w.readings[0][1] for w in words] == ["En", "el"]
        assert all(w.parent_ref == returned.segments[3].ref for w in words)
        assert "line reading beside its words" not in report.lost

    def test_a_word_that_is_punctuation_does_not_gain_a_space(self):
        """Found by the PAGE XML crossing below: joining words with spaces turned
        "Monatsſchrift." into "Monatsſchrift .". The line's own text is written and the words
        are wrapped where they stand."""
        page = SourcePage(image_size=(1000, 1000), segments=[
            PageSegment(kind="line", ref="l", polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.2], [0.1, 0.2]],
                        readings=[("transcription", "Monatsſchrift.")]),
            PageSegment(kind="word", ref="a", parent_ref="l", rect=[0.1, 0.1, 0.5, 0.1],
                        readings=[("transcription", "Monatsſchrift")]),
            PageSegment(kind="word", ref="b", parent_ref="l", rect=[0.6, 0.1, 0.05, 0.1],
                        readings=[("transcription", ".")])])
        returned, report = round_trip("tei", page)
        assert returned.segments[0].readings == [("transcription", "Monatsſchrift.")]
        assert [w.readings[0][1] for w in returned.segments[1:]] == ["Monatsſchrift", "."]
        assert "line reading beside its words" not in report.lost

    def test_rival_readings_survive_as_an_apparatus_and_which_counts_is_reported(self):
        page = _page()
        page.segments[3].readings = [("transcription", "En el año"), ("normalised", "En el ano")]
        returned, report = round_trip("tei", page)
        assert returned.segments[3].readings == [("transcription", "En el año"), ("normalised", "En el ano")]
        assert "which reading counts" in report.lost

    def test_a_reading_kind_other_than_transcription_is_kept(self):
        page = _page()
        page.segments[3].readings = [("normalised", "en el ano")]
        returned, _ = round_trip("tei", page)
        assert returned.segments[3].readings == [("normalised", "en el ano")]

    def test_a_region_with_only_text_and_no_lines_keeps_it(self):
        page = SourcePage(image_size=(100, 100), segments=[
            PageSegment(kind="region", ref="r", polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
                        readings=[("transcription", "just a block")])])
        returned, _ = round_trip("tei", page)
        assert returned.segments[0].readings == [("transcription", "just a block")]


class TestWhatItCannotCarryIsReportedNotDropped:
    def test_extra_orders_are_named_in_the_report(self):
        page = _page()
        page.orders.append(PageOrder(name="by-column", refs=["r2", "r1"]))
        _, report = round_trip("tei", page)
        assert "named reading orders" in report.lost

    def test_a_direction_tei_has_no_hint_for_is_named(self):
        page = _page()
        page.segments[0].direction = "btt"
        _, report = round_trip("tei", page)
        assert "direction" in report.lost

    def test_a_language_outside_iso_639_is_named(self):
        page = _page()
        page.segments[2].language = "Klingonese"
        returned, report = round_trip("tei", page)
        assert "language" in report.lost
        assert returned.segments[2].language is None

    def test_a_granularity_tei_has_no_place_for_is_named(self):
        page = _page()
        page.segments.append(PageSegment(kind="character", ref="c1", parent_ref="l2", rect=[0, 0, 0.1, 0.1]))
        _, report = round_trip("tei", page)
        assert "character segments" in report.lost

    def test_no_page_size_is_named(self):
        page = _page()
        page.image_size = None
        _, report = round_trip("tei", page)
        assert "page size" in report.lost


class TestTheExportIsValidatedAgainstTheRealSchema:
    def test_the_schema_is_on_disk_and_a_broken_export_is_refused(self):
        spec = format_named("tei")
        assert spec.schema_path().exists() and spec.schema_path().stat().st_size > 500_000
        bad = b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body/></text></TEI>'
        assert validate(spec, bad), "a TEI document with no header must fail its own schema"

    def test_an_export_that_fails_the_schema_is_a_failure_and_no_bytes(self, monkeypatch):
        def broken(page, report):
            return b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body/></text></TEI>'

        spec = format_named("tei")
        from fichero_server.formats import _REGISTRY
        from dataclasses import replace

        monkeypatch.setitem(_REGISTRY, "tei", replace(spec, write=broken))
        with pytest.raises(InvalidExport):
            write_page("tei", _page())


class TestARealFileAnotherProjectWrote:
    """The TEI Consortium's own transcription test file (CC BY 3.0 / BSD-2; see the fixtures'
    PROVENANCE). It is thin next to an edition, and it is the honest thing we can ship."""

    @pytest.fixture(scope="class")
    def real_bytes(self) -> bytes:
        data = FIXTURE.read_bytes()
        assert len(data) > 3_000, f"the fixture is {len(data)} bytes; it should be ~3.9 KB"
        return data

    def test_it_is_recognised_as_tei_from_its_own_bytes(self, real_bytes):
        assert tei._sniff(real_bytes) is True
        assert format_for("testtranscr.xml", real_bytes).name == "tei"

    def test_the_surface_frame_has_a_non_zero_origin_and_geometry_is_normalised_by_it(self, real_bytes):
        """`<surface ulx="358" lrx="700" lry="681">`: a frame that does not start at 0. A reader
        that divided by `lrx` instead of `lrx - ulx` would put every line in the wrong place."""
        page = tei.read_pages(real_bytes)[0]
        assert page.image_size == (342, 681) and page.image_name == "gravestone.jpg"
        first = next(s for s in page.segments if s.readings and s.readings[0][1] == "12851 PRIVATE")
        # zone line1: ulx 437 uly 223 lrx 626 lry 256 in a frame starting at x=358
        assert first.rect == pytest.approx([(437 - 358) / 342, 223 / 681, (626 - 437) / 342, (256 - 223) / 681])

    def test_lines_come_from_s_elements_that_point_at_zones_not_from_the_empty_lb(self, real_bytes):
        page = tei.read_pages(real_bytes)[0]
        texts = [s.readings[0][1] for s in page.segments if s.kind == "line" and s.rect]
        assert texts == ["12851 PRIVATE", "H. MOULDS", "NORTHAMPTONSHIRE REGT.", "23RD JULY 1916 AGED 21",
                         "LOVING SON OF", "MRS MOULDS", "PETERBORO, ENGLAND", "FOR EVER WITH US"]

    def test_deleted_text_is_not_the_reading_and_added_text_is(self, real_bytes):
        page = tei.read_pages(real_bytes)[0]
        texts = [s.readings[0][1] for s in page.segments if s.readings]
        assert any(t.endswith("The expressed") or "The expressed" in t for t in texts)
        assert not any("splodge" in t for t in texts), "<del>splodge</del> is deleted text"
        greek = [t for t in texts if "τῷ ὑποδέκτῃ" in t]
        assert greek and "ἐπιτρέψῃ" in greek[0] and "ἐπετρέψῃ" not in greek[0]

    def test_markup_the_model_has_no_field_for_is_kept_by_name(self, real_bytes):
        page = tei.read_pages(real_bytes)[0]
        kept = {name for s in page.segments for name in s.foreign.get("tei-inline", [])}
        assert {"add", "del", "subst"} <= kept

    def test_empty_wrappers_are_not_regions(self, real_bytes):
        page = tei.read_pages(real_bytes)[0]
        assert all(s.readings or s.rect or any(c.parent_ref == s.ref for c in page.segments)
                   for s in page.segments if s.kind == "region")

    def test_written_back_it_validates_and_the_lines_and_shapes_survive(self, real_bytes):
        page = tei.read_pages(real_bytes)[0]
        data, report = write_page("tei", page)  # raises InvalidExport if it does not validate
        assert "inline markup" in report.lost
        again = read_page("tei", data)
        was = [(s.readings, s.rect) for s in page.segments if s.kind == "line"]
        got = [(s.readings, s.rect) for s in again.segments if s.kind == "line"]
        assert [r for r, _ in got] == [r for r, _ in was]
        for (_, a), (_, b) in zip(got, was):
            assert (a is None) == (b is None)
            if a:
                assert a == pytest.approx(b, abs=1 / 300)


class TestDialectsAHandWrittenFileStandsInFor:
    """Shapes seen in a real edition (the Van Gogh Letters, which we may not ship: CC BY-NC-SA)
    and reproduced here as SMALL HAND-WRITTEN files. Labelled as what they are: our idea of a
    dialect, not another project's output. A permissively licensed edition is still wanted."""

    HEADER = ('<teiHeader><fileDesc><titleStmt><title>t</title></titleStmt>'
              '<publicationStmt><p/></publicationStmt><sourceDesc><p/></sourceDesc></fileDesc></teiHeader>')

    def _tei(self, body: str, header: str | None = None) -> bytes:
        return (f'<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:vg="http://example.org/ns">'
                f'{header or self.HEADER}<text><body>{body}</body></text></TEI>').encode()

    def test_a_milestone_written_before_its_block_keeps_the_blocks_first_text(self):
        page = tei.read_pages(self._tei('<div><lb n="1"/><ab>first words <lb n="2"/>second line</ab></div>'))[0]
        lines = [s for s in page.segments if s.kind == "line"]
        assert [l.readings[0][1] for l in lines] == ["first words", "second line"]
        assert all(l.parent_ref for l in lines)

    def test_empty_milestones_are_not_lines(self):
        page = tei.read_pages(self._tei('<div><lb/><lb/><ab>one <lb/>two</ab></div>'))[0]
        assert [s.kind for s in page.segments].count("line") == 2

    def test_pb_splits_pages(self):
        pages = tei.read_pages(self._tei('<div><pb/><ab>page one</ab><pb/><ab>page two</ab></div>'))
        assert [p.segments[0].readings[0][1] for p in pages] == ["page one", "page two"]

    def test_a_project_namespace_header_is_kept_and_reported_not_written(self):
        header = ('<teiHeader><fileDesc><titleStmt><title>t</title></titleStmt><publicationStmt><p/>'
                  '</publicationStmt><sourceDesc><vg:letDesc>x</vg:letDesc></sourceDesc></fileDesc></teiHeader>')
        page = tei.read_pages(self._tei("<div><ab>hi</ab></div>", header))[0]
        assert "vg:letDesc" in page.foreign["tei"]["teiHeader"]
        data, report = write_page("tei", page)
        assert "teiHeader" in report.lost and b"letDesc" not in data

    def test_a_header_that_validates_is_written_back(self):
        page = tei.read_pages(self._tei("<div><ab>hi</ab></div>"))[0]
        data, report = write_page("tei", page)
        assert "teiHeader" not in report.lost and b"<title>t</title>" in data

    def test_zones_with_no_coordinates_give_no_geometry(self):
        body = '<div><ab>x</ab></div>'
        data = self._tei(body).replace(b"</teiHeader>", b'</teiHeader><facsimile><surface xml:id="s"><graphic url="a.tif"/><zone xml:id="z"/></surface></facsimile>')
        page = tei.read_pages(data)[0]
        assert page.image_size is None and all(s.rect is None for s in page.segments)


class TestThroughTheOneModelFromAnotherFormat:
    """`source.format.one-model-one-harness`: PAGE XML in, TEI out -- never a converter."""

    @pytest.mark.xfail(
        strict=True,
        reason="#5083: a word carried only by a <Word> element vanishes from the line's text on "
        "the PAGE XML -> TEI round trip, and the loss report does not mention it",
    )
    def test_a_real_page_xml_file_becomes_valid_tei_with_its_text(self):
        source = (Path(__file__).parent / "fixtures" / "ocrd_gt_aepinus_0020.page.xml").read_bytes()
        page = read_page("pagexml", source)
        data, report = write_page("tei", page)  # validated against tei_all.xsd inside
        back = read_page("tei", data)
        was = [s.readings[0][1] for s in page.segments if s.kind == "line" and s.readings]
        got = [s.readings[0][1] for s in back.segments if s.kind == "line" and s.readings]
        assert got == was and len(was) > 10
        assert len([s for s in back.segments if s.kind == "line"]) == len([s for s in page.segments if s.kind == "line"])
        assert "separator segments" in report.lost, "PAGE XML's separators have no TEI element and say so"
