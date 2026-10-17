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
        anchor = SourceAnchor(document_id=doc.id, rect=[0.1, 0.05 * i, 0.6, 0.04])
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
    mark_no_writing(db, unread)

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
