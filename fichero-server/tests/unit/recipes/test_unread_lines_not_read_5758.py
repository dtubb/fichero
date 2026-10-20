"""A page whose found lines mostly have no reading is not "read" (#5758), tested to the spec
`source.onboard.auto.results-summary` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: a handwritten 5-page run found 114 lines, read 51, and said "Read 5 of 5 pages, 0 failed".
"""

from __future__ import annotations

from fichero_server.models import ContentRepresentation, DocType, Document, FileType
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass, bbox_and_tile_from_anchor
from fichero_server.recipes import run_view


def _page(db, lines: int, read: int) -> str:
    doc = Document(name="p.png", doc_type=DocType.file, file_type=FileType.image, path="/p.png")
    db.save(doc)
    pas = SegmentPass(document_id=doc.id, name="lines", provenance_kind=ProvenanceKind.workflow)
    db.save(pas)
    for i in range(lines):
        anchor = SourceAnchor(document_id=doc.id, rect=[0.1, 0.9 * i / lines, 0.6, 0.5 / lines])
        x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
        seg = Segment(document_id=doc.id, pass_id=pas.id, kind="line", anchor=anchor, bbox_x=x, bbox_y=y,
                      bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{doc.id}:line",
                      provenance_kind=ProvenanceKind.workflow)
        db.save(seg)
        if i < read:
            db.save(ContentRepresentation(document_id=doc.id, segment_id=seg.id, kind="transcription",
                                          content="texto", source_anchor=anchor))
    return doc.id


def test_lines_without_a_reading_are_counted_and_the_page_is_not_read(db):
    whole, partial, none = _page(db, 3, 3), _page(db, 10, 3), _page(db, 0, 0)

    assert run_view.lines_unread(db, [whole, partial, none]) == 7
    assert run_view.pages_fully_read(db, [whole, partial, none]) == [whole]


def test_the_summary_words_say_how_many_lines_are_unread():
    s = run_view.RecipeRunSummary(job_id="j", state="done", finished=True, pages=5, pages_read=2, names=[],
                                  dates=0, statements=0, lines_unread=63, failed=[], pages_failed=0,
                                  skipped=[], not_run=[])
    said = run_view._lines(s, 0)
    assert "Read 2 of 5 pages" in said and any("63 lines have no reading" in w for w in said), said


def test_a_second_start_reads_again_every_page_with_unread_lines(db):
    from fichero_server.recipes.done import is_done

    card = {"job": "read-a-line", "model_override": None}
    whole, partial, unread = _page(db, 3, 3), _page(db, 10, 3), _page(db, 4, 0)

    assert is_done(db, card, whole) is True
    assert is_done(db, card, partial) is False
    assert is_done(db, card, unread) is False


def test_a_line_looked_at_with_no_writing_is_read_and_a_second_start_leaves_it(db):
    """A ruled or blank line has no reading to store; recording that it was looked at counts it as read."""
    from fichero_server.llm.working_lines import mark_no_writing
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.done import is_done

    card = {"job": "read-a-line", "model_override": None}
    page = _page(db, 4, 2)
    assert is_done(db, card, page) is False
    unread = [s.id for s in db.query(Segment, document_id=page) if s.kind == "line"
              and not any(r.segment_id == s.id for r in db.query(ContentRepresentation, document_id=page))]
    mark_no_writing(db, unread, model="weak")

    assert is_done(db, card, page) is True
    assert run_view.lines_unread(db, [page]) == 0
    assert run_view.pages_fully_read(db, [page]) == [page]


def test_the_line_reader_names_the_lines_it_looked_at_and_found_blank(tmp_path, monkeypatch):
    import asyncio

    from PIL import Image

    from fichero_server import llm
    from fichero_server.llm import LLMConfig, line_reader
    from fichero_server.llm.working_lines import NO_WRITING_KEY
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    path = tmp_path / "p.png"
    Image.new("RGB", (400, 100), "white").save(path)

    def line(sid, y):
        poly = [[10, y], [390, y], [390, y + 20], [10, y + 20]]
        return OCRGeometryBox(text="", bbox=[0.0, y / 100, 1.0, 0.2], level=OCRGeometryLevel.LINE, provider="kraken",
                              model="m", source="working-pass",
                              metadata={"segment_id": sid, "polygon_px": poly, "baseline_px": [[10, y + 15], [390, y + 15]],
                                        "pixel_frame": {"width": 400, "height": 100}})

    async def fake_vision(**kw):
        return '[null, "hola"]'

    monkeypatch.setattr(llm, "vision", fake_vision)
    geometry = OCRGeometryResult(text="", provider="kraken", model="m", boxes=[line("a", 10), line("b", 50)],
                                 source="working-pass", metadata={})
    out = asyncio.run(line_reader.read_lines(str(path), geometry, LLMConfig(provider="openrouter", model="x")))

    assert out.metadata[NO_WRITING_KEY] == ["a"]
    assert [b.metadata["segment_id"] for b in out.boxes if b.text] == ["b"]


def test_the_mark_is_a_versioned_audited_segment_update_keyed_by_the_model_that_looked(db):
    from fichero_server.llm.working_lines import mark_no_writing
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.done import is_done

    page = _page(db, 1, 0)
    blank = next(s for s in db.query(Segment, document_id=page) if s.kind == "line"
                 and not any(r.segment_id == s.id for r in db.query(ContentRepresentation, document_id=page)))
    before = blank.version
    mark_no_writing(db, [blank.id], model="weak")

    assert db.get(Segment, blank.id).version == before + 1, "saved through segment.update: versioned"
    assert is_done(db, {"job": "read-a-line", "model_override": "weak"}, page) is True
    assert is_done(db, {"job": "read-a-line", "model_override": "better"}, page) is False, "a better reader looks again"


def test_one_blank_line_does_not_finish_a_page_for_a_reader_that_read_none_of_its_text(db):
    from fichero_server.llm.working_lines import mark_no_writing
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.done import is_done

    page = _page(db, 2, 1)  # line 0 has a reading (not by "better"), line 1 has none
    blank = next(s for s in db.query(Segment, document_id=page) if s.kind == "line"
                 and not any(r.segment_id == s.id for r in db.query(ContentRepresentation, document_id=page)))
    mark_no_writing(db, [blank.id], model="better")
    assert is_done(db, {"job": "read-a-line", "model_override": "better"}, page) is False

    blank_page = _page(db, 1, 0)  # every line blank: looked at, nothing to read
    only = next(s for s in db.query(Segment, document_id=blank_page) if s.kind == "line")
    mark_no_writing(db, [only.id], model="better")
    assert is_done(db, {"job": "read-a-line", "model_override": "better"}, blank_page) is True


def test_a_line_a_recognising_reader_gave_no_text_is_saved_marked_with_why():
    """The live run (M4, 2026-10-17) segmented and read in one go: a line read as empty text was saved with no
    reading and no mark, so 36 lines were 'unread' with no reason anywhere."""
    from fichero_server.models.segments import segment_from_box
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel

    def box(text, source, **meta):
        return OCRGeometryBox(text=text, bbox=[0.1, 0.1, 0.5, 0.05], level=OCRGeometryLevel.LINE, provider="kraken",
                              model="m1", source=source, metadata={"polygon_px": [[0, 0], [9, 0], [9, 3]], **meta})

    read = lambda b: segment_from_box(document_id="d", artifact_id="a", box_index=0, box=b, rendition_id=None,
                                      pass_provenance_kind=ProvenanceKind.workflow)
    blank = read(box("", "kraken-htr", page_has_readings=True)).metadata["read_no_writing"]
    assert blank["model"] == "m1" and blank["reason"]
    # a page where the reader returned empty for EVERY line is a failed read, not 'no writing' (review 64)
    nothing = read(box("", "kraken-htr", page_read_nothing=True)).metadata
    assert "read_no_writing" not in nothing and nothing["unread_reason"] == "every line came back empty: the reader may not suit this hand"
    assert "read_no_writing" not in read(box("", "kraken-blla")).metadata, "a finder reads nothing: not looked at"
    assert "read_no_writing" not in read(box("texto", "kraken-htr")).metadata


def test_every_unread_line_has_a_reason(db):
    from fichero_server.recipes.done import unread_reasons

    page = _page(db, 3, 1)
    reasons = unread_reasons(db, page)
    assert len(reasons) == 2 and all(isinstance(r, str) and r for r in reasons.values())
    assert run_view.lines_unread_why(db, [page]) == {next(iter(reasons.values())): 2}


def test_a_page_the_reader_returned_nothing_for_is_unread_failed_and_read_again(db):
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.done import NOTHING_FOR_PAGE, is_done, unread_reasons

    page = _page(db, 3, 0)
    for seg in db.query(Segment, document_id=page):
        if seg.kind == "line":
            seg.metadata = {**(seg.metadata or {}), "unread_reason": NOTHING_FOR_PAGE}
            db.save(seg)
    assert set(unread_reasons(db, page).values()) == {NOTHING_FOR_PAGE}
    assert is_done(db, {"job": "read-a-line", "model_override": None}, page) is False, "a second Start reads it again"
    assert run_view.pages_read_nothing(db, [page]) == 1


def test_the_summary_shows_the_lines_the_reader_saw_as_blank(db):
    """Live M4 run: 36 blank lines on pages that also had text were left out, so 66 lines without text showed as 30."""
    from fichero_server.llm.working_lines import mark_no_writing
    from fichero_server.models.segments import Segment

    page = _page(db, 4, 2)
    unread = [s.id for s in db.query(Segment, document_id=page) if s.kind == "line"
              and not any(r.segment_id == s.id for r in db.query(ContentRepresentation, document_id=page))]
    mark_no_writing(db, unread, model="weak")
    assert run_view.lines_seen_blank(db, [page]) == 2
    summary = run_view.RecipeRunSummary(
        job_id="j", state="done", finished=True, pages=5, pages_read=4, names=[], dates=0, statements=0, failed=[],
        pages_failed=0, skipped=[], not_run=[], lines_seen_blank=36, pages_with_lines=4)
    said = run_view._lines(summary, 0)
    assert "36 lines the reader found no writing on" in said and "No lines found on 1 page" in said, said
