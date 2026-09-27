"""hOCR and YOLO (#4944) — the two formats with no schema, and the one that loses
almost everything.

**hOCR is the honest `schema=None` case the harness was built for.** It is HTML with
an agreed microformat, so there is nothing to validate against — which is a different
fact from a schema missing off an install, and the harness keeps them apart.

**YOLO is the loss report's hardest case.** Five numbers a line: no text, no
language, no order, no nesting, no identity. If the design is right, that makes
YOLO's writer honest rather than impossible. If it were wrong, YOLO is the format
that would have forced a fudge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.formats import (
    format_for,
    format_named,
    read_page,
    round_trip,
    validate,
    write_page,
)
from fichero_server.formats.harness import PageOrder, PageSegment, SourcePage

pytestmark = pytest.mark.source_model

FIXTURES = Path(__file__).parent / "fixtures"

#: hOCR as an engine writes it: a page bbox, content areas, lines with baselines, and
#: word spans with confidences. Hand-written rather than engine-produced, and
#: **labelled as such** — `tesseract` is not installed on this machine, so no genuine
#: engine output could be produced, and the third-party sample available
#: (`ocropus/hocr-tools`, Apache-2.0) has no bounding boxes at all. Recorded as
#: residue in `fixtures/PROVENANCE.md` rather than described as a real file.
HOCR_OURS = b"""<html>
 <head>
  <meta name='ocr-system' content='tesseract 5.3.0' />
  <meta name='ocr-capabilities' content='ocr_page ocr_carea ocr_line ocrx_word' />
 </head>
 <body>
  <div class='ocr_page' id='page_1' title='image "folio.png"; bbox 0 0 1000 1400; ppageno 0'>
   <div class='ocr_carea' id='block_1_1' title="bbox 100 100 900 300">
    <p class='ocr_par' id='par_1_1' lang='deu' title="bbox 100 100 900 300">
     <span class='ocr_line' id='line_1_1' title="bbox 100 100 900 160; baseline 0.008 -9; x_size 44">
      <span class='ocrx_word' id='word_1_1' title='bbox 100 100 300 160; x_wconf 96'>Wenn</span>
      <span class='ocrx_word' id='word_1_2' title='bbox 320 100 560 160; x_wconf 93'>ist</span>
      <span class='ocrx_word' id='word_1_3' title='bbox 580 100 900 160; x_wconf 88'>das</span>
     </span>
    </p>
   </div>
  </div>
 </body>
</html>
"""


class TestHocrNeedsNoSchemaAndSaysSo:
    def test_hocr_declares_no_schema_because_it_has_none(self):
        """The distinction the harness rests on: `schema=None` is "cannot be
        validated, by nature", which is NOT "a schema is missing". A format that
        collapsed them would let a broken install report every export as valid."""
        spec = format_named("hocr")

        assert spec.schema is None
        assert validate(spec, b"<html>anything at all</html>") == []

    def test_an_export_still_succeeds_without_a_schema(self):
        page = SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="line", ref="l1", rect=[0.1, 0.1, 0.5, 0.05],
                            readings=[("transcription", "en el nombre")]),
            ],
        )

        data, report = write_page("hocr", page)

        assert b"ocr_line" in data
        assert "text" not in report.lost


class TestReadingHocr:
    def test_the_page_its_areas_lines_and_words_arrive(self):
        page = read_page("hocr", HOCR_OURS)

        kinds = [segment.kind for segment in page.segments]
        assert kinds.count("region") == 2  # ocr_carea and ocr_par are both regions
        assert kinds.count("line") == 1
        assert kinds.count("word") == 3

    def test_the_page_size_comes_from_the_page_bbox(self):
        page = read_page("hocr", HOCR_OURS)

        assert page.image_size == (1000, 1400)
        assert page.image_name == "folio.png"
        assert page.producer == "tesseract 5.3.0"

    def test_boxes_are_normalised_against_that_page(self):
        page = read_page("hocr", HOCR_OURS)
        word = next(s for s in page.segments if s.ref == "word_1_1")

        assert word.rect == pytest.approx([0.1, 100 / 1400, 0.2, 60 / 1400])

    def test_a_line_with_word_spans_does_not_repeat_their_text(self):
        """A line's `itertext()` includes its words. Storing both would give the page
        every word twice — once as a word and once inside the line."""
        page = read_page("hocr", HOCR_OURS)
        line = next(s for s in page.segments if s.ref == "line_1_1")
        words = [s for s in page.segments if s.kind == "word"]

        assert line.readings == []
        assert [text for _kind, text in (words[0].readings + words[1].readings + words[2].readings)] == [
            "Wenn", "ist", "das"
        ]

    def test_the_language_is_a_TAG_as_in_alto_and_unlike_pagexml(self):
        """Third data point for #5078: hOCR uses HTML's `lang`, a BCP 47 tag. Two of
        the three formats built want tags; PAGE XML wants names. **No choice of
        storage avoids a mapping**, so the question is which mapping loses nothing."""
        page = read_page("hocr", HOCR_OURS)

        langs = {s.language for s in page.segments if s.language}
        assert langs == {"deu"}

    def test_hocrs_own_properties_are_kept(self):
        """`x_wconf`, `x_size` and the baseline POLYNOMIAL are hOCR's own. The
        baseline is slope-and-intercept relative to the line's box, not a polyline —
        kept verbatim rather than converted into points that would claim a precision
        the file does not have."""
        page = read_page("hocr", HOCR_OURS)
        word = next(s for s in page.segments if s.ref == "word_1_1")
        line = next(s for s in page.segments if s.ref == "line_1_1")

        assert word.foreign["hocr:x_wconf"] == "96"
        assert line.foreign["hocr:baseline"] == "0.008 -9"

    def test_it_is_recognised_by_its_classes_not_its_extension(self):
        assert format_for("page.html", HOCR_OURS).name == "hocr"
        assert format_named("hocr").sniff(b"<html><body><p>ordinary page</p></body></html>") is False


class TestHocrRoundTrip:
    def test_the_words_and_their_text_survive(self):
        page = read_page("hocr", HOCR_OURS)

        returned, report = round_trip("hocr", page)

        before = [(s.kind, s.readings) for s in page.segments if s.kind == "word"]
        after = [(s.kind, s.readings) for s in returned.segments if s.kind == "word"]
        assert after == before

    def test_the_boxes_survive_to_a_pixel_of_the_declared_page(self):
        page = read_page("hocr", HOCR_OURS)

        returned, _report = round_trip("hocr", page)

        by_ref = {s.ref: s for s in returned.segments}
        for segment in page.segments:
            came_back = by_ref.get(segment.ref)
            if came_back is None or not segment.rect:
                continue
            for mine, theirs in zip(segment.rect, came_back.rect):
                assert mine == pytest.approx(theirs, abs=1 / 1000)

    def test_hocrs_own_baseline_is_written_back_not_declared_lost(self):
        """`keeps-unrecognised`'s write half, which a real file caught me missing in
        PAGE XML. Here it is asserted from the start."""
        page = read_page("hocr", HOCR_OURS)

        returned, report = round_trip("hocr", page)

        line = next(s for s in returned.segments if s.ref == "line_1_1")
        assert line.foreign["hocr:baseline"] == "0.008 -9"
        assert "baseline" not in report.lost


class TestYoloIsHonestAboutLosingAlmostEverything:
    def _page(self) -> SourcePage:
        return SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="region", ref="r1", rect=[0.1, 0.1, 0.8, 0.2],
                            language="Spanish", script="Latn"),
                PageSegment(kind="line", ref="l1", parent_ref="r1",
                            rect=[0.1, 0.1, 0.8, 0.05],
                            readings=[("transcription", "en el nombre de dios")]),
            ],
            orders=[PageOrder(name="as-written", refs=["r1"])],
        )

    def test_the_geometry_survives_and_that_is_what_round_trips(self):
        returned, _report = round_trip("yolo", self._page())

        assert len(returned.segments) == 2
        original = self._page().segments[0].rect
        assert returned.segments[0].rect == pytest.approx(original, abs=1e-5)

    def test_the_centre_first_conversion_is_not_off_by_half_a_box(self):
        """The one conversion YOLO needs, and the one a naive reader gets wrong: the
        file stores the box's CENTRE, the model its top-left corner."""
        data, _report = write_page("yolo", self._page())

        first = data.decode().splitlines()[0].split()
        assert first[0] == "0"  # region
        assert float(first[1]) == pytest.approx(0.1 + 0.8 / 2)
        assert float(first[2]) == pytest.approx(0.1 + 0.2 / 2)

    def test_every_loss_is_named_and_the_report_is_long_on_purpose(self):
        """A format carrying four numbers per box should produce a LONG report. A
        short one would mean the writer was not looking."""
        _data, report = write_page("yolo", self._page())

        assert "the text of every segment" in report.lost
        assert "language" in report.lost
        assert "script" in report.lost
        assert "named reading orders" in report.lost
        assert "nesting" in report.lost
        assert "segment identity" in report.lost

    def test_the_text_loss_says_WHY_rather_than_only_that(self):
        _data, report = write_page("yolo", self._page())

        text_loss = next(loss for loss in report.losses if loss.what == "the text of every segment")
        assert "trains a detector, not a reader" in text_loss.why

    def test_a_malformed_line_is_refused_rather_than_skipped(self):
        """A training set with silently dropped boxes trains a model to miss exactly
        those, and nothing downstream would ever say so."""
        from fichero_server.formats.yolo import MalformedYoloLine

        with pytest.raises(MalformedYoloLine) as raised:
            read_page("yolo", b"0 0.5 0.5 0.2 0.2\n1 0.5 oops 0.2\n")
        assert "line 2" in str(raised.value)
        assert "teaches a model to miss them" in str(raised.value)

    def test_prose_is_not_mistaken_for_labels(self):
        """`.txt` is the most ambiguous extension there is, so the bytes decide — and
        deliberately strictly: guessing would turn a text file into boxes."""
        assert format_named("yolo").sniff(b"This is a transcription, not a label file.\n") is False
        assert format_named("yolo").sniff(b"0 0.5 0.5 0.2 0.2\n") is True


class TestAYoloDatasetsOwnClassNames:
    """#5130: a YOLO file's numbers mean what its DATASET says. YALTAi's `4` is SegmOnto's
    `MainZone`, with a `classes.txt` beside the labels; the reader turned it into our "character"
    (0 region, 1 line, 2 word, 3 character is only Fichero's own export convention)."""

    LABELS = b"4 0.5 0.5 0.4 0.6\n9 0.5 0.05 0.3 0.04\n0 0.9 0.9 0.05 0.05\n"
    SEGMONTO = ["DamageZone", "DigitizationArtefactZone", "DropCapitalZone", "GraphicZone", "MainZone",
                "MarginTextZone", "MusicZone", "NumberingZone", "QuireMarksZone", "RunningTitleZone"]

    def test_classes_txt_beside_the_labels_names_the_classes(self, tmp_path):
        from fichero_server.formats.yolo import class_names_beside, read

        (tmp_path / "classes.txt").write_text("\n".join(self.SEGMONTO) + "\n", encoding="utf-8")
        (tmp_path / "003.txt").write_bytes(self.LABELS)
        page = read(self.LABELS, class_names_beside(tmp_path / "003.txt"))
        names = [s.foreign["yolo:class_name"] for s in page.segments]
        assert names == ["MainZone", "RunningTitleZone", "DamageZone"]
        assert {s.kind for s in page.segments} == {"region"}, "SegmOnto zones are regions, never words"

    def test_data_yaml_two_folders_up_names_them_too(self, tmp_path):
        from fichero_server.formats.yolo import class_names_beside

        (tmp_path / "data.yaml").write_text("names:\n  0: DefaultLine\n  1: MainZone\n", encoding="utf-8")
        labels = tmp_path / "labels" / "train" / "p.txt"
        labels.parent.mkdir(parents=True)
        labels.write_bytes(b"0 0.5 0.5 0.1 0.1\n")
        assert class_names_beside(labels) == ["DefaultLine", "MainZone"]

    def test_the_class_numbers_and_names_round_trip(self):
        from fichero_server.formats import LossReport
        from fichero_server.formats.yolo import read, write

        page = read(self.LABELS, self.SEGMONTO)
        back = read(write(page, LossReport(format="yolo")), self.SEGMONTO)
        assert [s.foreign["yolo:class_name"] for s in back.segments] == ["MainZone", "RunningTitleZone", "DamageZone"]
        assert [s.foreign["yolo:class"] for s in back.segments] == [4, 9, 0]

    def test_a_line_class_is_a_line(self):
        from fichero_server.formats.yolo import read

        page = read(b"0 0.5 0.5 0.4 0.02\n", ["DefaultLine"])
        assert page.segments[0].kind == "line"

    def test_the_library_import_reads_classes_txt_beside_the_file(self, db, tmp_path):
        import fichero_server.api.routes.document.format_import  # noqa: F401
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models import DocType, Document, FileType, Status
        from fichero_server.models.segments import Segment, SegmentPass

        (tmp_path / "classes.txt").write_text("\n".join(self.SEGMONTO) + "\n", encoding="utf-8")
        (tmp_path / "003.txt").write_bytes(self.LABELS)
        doc = Document(name="003.jpg", doc_type=DocType.file, file_type=FileType.image,
                       path="/p/003.jpg", status=Status.completed)
        db.save(doc)
        registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(tmp_path / "003.txt")},
                        ActionContext(actor="h", library_path=None, is_bootstrap=True))
        [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == doc.id]
        rows = [s for s in db.all(Segment) if s.pass_id == pass_row.id]
        assert sorted(r.metadata["foreign"]["yolo:class_name"] for r in rows) == ["DamageZone", "MainZone", "RunningTitleZone"]
