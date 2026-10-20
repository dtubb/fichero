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
