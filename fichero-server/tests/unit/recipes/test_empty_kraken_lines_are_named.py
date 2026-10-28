"""A Kraken read of a page's working lines that came back mostly empty says so (#6219).

The M4 run (2026-10-26): "26 of 49 lines on IMG_009 came back empty: a failed read, they stay unread", yet the read
step said done and the summary gave those 26 lines "no reader has answered for the line". The read-onto-working-lines
path dropped the empty lines with no reason; now each carries the failed-read reason, so the step is partial, the
summary says the reader came back empty, and the next reader is offered.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.llm.working_lines import empty_lines_why, mark_unread_reasons
from fichero_server.recipes.done import MOSTLY_NOTHING_FOR_PAGE, NOT_ANSWERED, NOTHING_FOR_PAGE


def test_the_m4_page_26_of_49_empty_names_each_line_mostly_empty():
    blank = [f"s{i}" for i in range(26)]
    no_writing, why = empty_lines_why(blank, 49)
    assert no_writing == []
    assert why == dict.fromkeys(blank, MOSTLY_NOTHING_FOR_PAGE)


def test_every_line_empty_says_every_line_came_back_empty():
    assert empty_lines_why(["a", "b", "c"], 3) == ([], dict.fromkeys(["a", "b", "c"], NOTHING_FOR_PAGE))


def test_a_few_blank_lines_on_a_read_page_stay_no_writing():
    assert empty_lines_why(["a", "b"], 30) == (["a", "b"], {})
    assert empty_lines_why([], 30) == ([], {})


def test_the_read_onto_working_lines_path_records_the_reasons():
    """The vision_base closure has no seam of its own: a source scan that it uses the helper and hands the reasons to
    `_write_onto_lines` (which marks them through `mark_unread_reasons`)."""
    import fichero_server.llm.working_lines as wl

    src = (Path(wl.__file__).parents[1] / "workflows" / "tools" / "vision_base.py").read_text()
    assert "_wl.empty_lines_why(_blank, len(geometry.boxes))" in src
    assert '"lines_unanswered": {**(geometry.metadata.get("lines_unanswered") or {}),' in src


def test_in_a_run_the_m4_page_makes_the_read_step_partial_and_the_summary_names_the_reason(db, monkeypatch):
    from fichero_server.models import Document
    from fichero_server.models.segments import Segment
    from fichero_server.models import ContentRepresentation
    from fichero_server.recipes import run_view, runner
    from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

    page = _page(db, 49, 23)
    read = {r.segment_id for r in db.query(ContentRepresentation, document_id=page)}
    blank = [s.id for s in db.query(Segment, document_id=page) if s.kind == "line" and s.id not in read]
    assert len(blank) == 26
    mark_unread_reasons(db, empty_lines_why(blank, 49)[1])

    assert run_view.lines_unread_why(db, [page]) == {MOSTLY_NOTHING_FOR_PAGE: 26}
    assert NOT_ANSWERED not in run_view.lines_unread_why(db, [page])

    monkeypatch.setattr(runner, "_did_no_page", lambda *a, **k: (False, 0, []))
    step = {"state": "done", "child_id": "c", "why": None}
    runner._after_the_step(db, {"card": "model", "job": "read-a-line", "steps": ["read-a-line"]}, step,
                           {"folder": "f"}, [page], "done", "c", None, {}, [], "read-a-line")
    assert step["state"] == "partial"
    assert step["failed_pages"] == [{"page": db.get(Document, page).name, "reason": MOSTLY_NOTHING_FOR_PAGE}]
