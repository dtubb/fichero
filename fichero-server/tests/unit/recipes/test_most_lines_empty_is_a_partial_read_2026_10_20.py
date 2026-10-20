"""`source.read.line-with-no-writing-is-read` rate rule (owner's page, 2026-10-20): a Kraken reader that gave no text for
more than half of a page's lines (of at least 5) failed the page. Its empty lines are not 'no writing': they stay unread,
with the reason in words, and the page is not counted read."""
from __future__ import annotations

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.llm.working_lines import reads_mostly_nothing
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import segment_from_box

LINE = {"polygon": [[0, 0], [90, 0], [90, 20], [0, 20]], "baseline": [[0, 15], [90, 15]]}


@pytest.mark.parametrize("empty, found, mostly", [
    (0, 0, False), (3, 3, True), (1, 2, False), (2, 4, False), (3, 4, False),  # under 5 lines: all or nothing
    (2, 5, False), (3, 5, True), (20, 25, True), (12, 25, True), (12, 24, False), (13, 25, True), (1, 30, False)])
def test_a_page_is_mostly_empty_when_more_than_half_of_at_least_five_lines_are(empty, found, mostly):
    assert reads_mostly_nothing(empty, found) is mostly


def _geometry(monkeypatch, texts):
    lines = [dict(LINE, text=t) for t in texts]
    monkeypatch.setattr(kraken_runtime, "recognize_lines",
                        lambda path, model: {"width": 100, "height": 100, "lines": lines, "regions": []})
    return [b for b in kraken_runtime.recognize_to_geometry("p.png", "m").boxes if str(b.level) == "line"]


def test_the_owners_page_five_of_twenty_five_lines_read_marks_the_rest_failed_not_blank(monkeypatch):
    boxes = _geometry(monkeypatch, ["texto"] * 5 + [""] * 20)
    assert all(b.metadata.get("page_read_mostly_nothing") for b in boxes)
    assert not any(b.metadata.get("page_has_readings") or b.metadata.get("page_read_nothing") for b in boxes)


def test_a_blank_line_on_a_page_that_mostly_read_stays_no_writing(monkeypatch):
    boxes = _geometry(monkeypatch, ["texto"] * 20 + [""] * 5)
    assert all(b.metadata.get("page_has_readings") for b in boxes)
    assert not any(b.metadata.get("page_read_mostly_nothing") for b in boxes)


def test_the_empty_lines_of_a_mostly_empty_page_are_unread_with_the_reason_in_words(monkeypatch):
    boxes = _geometry(monkeypatch, ["texto"] * 5 + [""] * 20)

    def saved(box):
        return segment_from_box(document_id="d", artifact_id="a", box_index=0, box=box, rendition_id=None,
                                pass_provenance_kind=ProvenanceKind.workflow).metadata

    empty = saved(next(b for b in boxes if not b.text))
    assert "read_no_writing" not in empty
    assert empty["unread_reason"] == "most lines came back empty: the reader may not suit this hand"
    assert "unread_reason" not in saved(next(b for b in boxes if b.text))


def test_the_read_onto_working_lines_path_follows_the_same_rule(monkeypatch):
    """The vision_base path that reads lines a page already has uses the one helper (a source scan: that closure has
    no seam of its own)."""
    from pathlib import Path

    src = (Path(kraken_runtime.__file__).parents[1] / "workflows" / "tools" / "vision_base.py").read_text()
    assert "_mostly_nothing(len(_blank), len(geometry.boxes))" in src
    assert "len(_blank) == len(geometry.boxes)" not in src


def _owners_page(db):
    """5 of 25 lines read; the 20 empty ones saved as `segment_from_box` saves them (unread, with the reason)."""
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import Segment
    from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

    page = _page(db, 25, 5)
    for seg in db.query(Segment, document_id=page):
        if seg.kind == "line" and not any(r.segment_id == seg.id for r in db.query(ContentRepresentation, document_id=page)):
            seg.metadata = {**(seg.metadata or {}),
                            "unread_reason": "most lines came back empty: the reader may not suit this hand"}
            db.save(seg)
    return page


def test_the_reason_the_segment_saves_is_the_one_the_run_matches():
    from fichero_server.recipes.done import MOSTLY_NOTHING_FOR_PAGE

    box = OCRGeometryBox(text="", bbox=[0.1, 0.1, 0.5, 0.05], level=OCRGeometryLevel.LINE, provider="kraken", model="m",
                         source="kraken-htr",
                         metadata={"polygon_px": [[0, 0], [9, 0], [9, 3]], "page_read_mostly_nothing": True})
    saved = segment_from_box(document_id="d", artifact_id="a", box_index=0, box=box, rendition_id=None,
                             pass_provenance_kind=ProvenanceKind.workflow)
    assert saved.metadata["unread_reason"] == MOSTLY_NOTHING_FOR_PAGE


def test_in_a_run_the_owners_page_makes_the_read_step_partial_naming_the_page_and_why(db, monkeypatch):
    """Review 480: the node succeeded (pages_failed 0), so the step said done and the row plain Done."""
    from fichero_server.models import Document
    from fichero_server.recipes import run_view, runner
    from fichero_server.recipes.done import MOSTLY_NOTHING_FOR_PAGE

    page = _owners_page(db)
    monkeypatch.setattr(runner, "_did_no_page", lambda *a, **k: (False, 0, []))
    card = {"card": "model", "job": "read-a-line", "steps": ["read-a-line"]}
    step = {"state": "done", "child_id": "c", "why": None}
    problems: list[str] = []
    runner._after_the_step(db, card, step, {"folder": "f"}, [page], "done", "c", None, {}, problems, "read-a-line")

    name = db.get(Document, page).name
    assert step["state"] == "partial"
    assert step["failed_pages"] == [{"page": name, "reason": MOSTLY_NOTHING_FOR_PAGE}]
    assert step["why"].startswith(f"0 of 1 pages done; 1 failed: {name}: most lines came back empty")
    assert len(problems) == 1 and "partial" in problems[0]
    words = runner._failures_words(db, [card], [step], 0)
    assert "lost pages" in words and name in words and "most lines came back empty" in words
    assert run_view.pages_read_nothing(db, [page]) == 1
    assert run_view.pages_fully_read(db, [page]) == []


def test_a_page_the_node_already_failed_is_not_counted_twice(db, monkeypatch):
    from fichero_server.recipes import runner
    from fichero_server.workflows.run_account import PageFailure

    page = _owners_page(db)
    lost = [PageFailure(page="p.png", document_id=page, reason="out of memory")]
    monkeypatch.setattr(runner, "_did_no_page", lambda *a, **k: (False, 1, lost))
    step = {"state": "done", "child_id": "c", "why": None}
    runner._after_the_step(db, {"card": "model", "job": "read-a-line", "steps": ["r"]}, step, {"folder": "f"}, [page],
                           "done", "c", None, {}, [], "r")
    assert step["pages_lost"] == 1 and len(step["failed_pages"]) == 1
