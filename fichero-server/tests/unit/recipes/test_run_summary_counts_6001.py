"""The recipe run's summary counts its pages in two set-based reads, on a worker thread (#6001, `activity.summary.counts-in-two-queries`
and `activity.summary.off-the-loop`).

WHY: on 2026-10-21 the loop-lag watchdog caught `run_view.summary` holding the event loop for 3.7 to 4.4 s a time: about ten database
calls a page, each waiting for the connection's transaction gate behind the writers, all on the loop."""
from __future__ import annotations

import ast
import asyncio
import threading
import time
from pathlib import Path

from fichero_server.llm.working_lines import mark_no_writing
from fichero_server.models.segments import Segment
from fichero_server.recipes import done, run_view
from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

SRC = Path(run_view.__file__).parents[1]


def _pages(db) -> list[str]:
    whole, partial, none, nothing = _page(db, 3, 3), _page(db, 10, 3), _page(db, 0, 0), _page(db, 4, 0)
    looked = _page(db, 4, 2)
    unread = [s.id for s in db.query(Segment, document_id=looked) if s.kind == "line"][2:]
    mark_no_writing(db, unread[:1], model="m")  # one line looked at with no writing: read, counted blank
    return [whole, partial, none, nothing, looked]


def test_the_counts_are_the_per_page_helpers_numbers(db):
    pages = _pages(db)
    got = run_view.reading_counts(db, pages, blank=set())
    assert got.lines_unread == run_view.lines_unread(db, pages)
    assert got.lines_unread_why == run_view.lines_unread_why(db, pages)
    assert got.lines_seen_blank == run_view.lines_seen_blank(db, pages)
    assert got.pages_read_nothing == run_view.pages_read_nothing(db, pages)
    assert got.pages_fully_read == run_view.pages_fully_read(db, pages)


def test_a_page_left_out_as_blank_is_not_counted(db):
    pages = _pages(db)
    kept = [p for p in pages if p != pages[1]]
    got = run_view.reading_counts(db, pages, blank={pages[1]})
    assert got.lines_unread == run_view.lines_unread(db, kept)
    assert got.pages_fully_read == run_view.pages_fully_read(db, kept)


def test_thirty_pages_take_a_handful_of_database_calls_not_hundreds(db, monkeypatch):
    pages = [_page(db, 6, 2) for _ in range(30)]
    calls: list[str] = []
    real = db._execute_fetch_with_columns

    def counting(sql, *args, **kwargs):
        calls.append(sql[:60])
        return real(sql, *args, **kwargs)

    monkeypatch.setattr(db, "_execute_fetch_with_columns", counting)
    run_view.reading_counts(db, pages, blank=set())
    assert len(calls) <= 8, f"{len(calls)} database calls for 30 pages"


def test_the_counts_run_on_a_worker_thread_and_leave_the_loop_free(db, monkeypatch):
    seen: dict[str, int] = {}

    def slow(_db, _pages, blank):
        seen["thread"] = threading.get_ident()
        time.sleep(1.0)  # waiting on the transaction gate behind a writer
        return "counts"

    monkeypatch.setattr(run_view, "reading_counts", slow)

    async def go() -> tuple[str, float]:
        work = asyncio.ensure_future(run_view.counts_off_the_loop(db, ["a"], set()))
        await asyncio.sleep(0.1)
        began = time.monotonic()
        await asyncio.sleep(0)
        took = time.monotonic() - began
        return await work, took

    result, took = asyncio.run(go())
    assert result == "counts" and took < 0.5 and seen["thread"] != threading.get_ident()


PER_PAGE = {"unread_reasons", "lines_state", "unread_on", "failed_reads", "lines_unread", "lines_unread_why", "lines_seen_blank",
            "pages_read_nothing", "pages_fully_read", "_fully_read", "_pages_dated", "_has_reading", "_pages_with", "_knowledge",
            "_found_documents", "_jobs_of_the_run", "reviewed", "read_project_setup", "download_failures", "_pages"}


def test_no_async_function_of_the_run_view_or_activity_calls_a_per_page_counting_helper():
    """The #5843 family (`test_event_loop_not_held_5843`): the loop never waits on the gate once per page."""
    offenders = []
    for rel in ("recipes/run_view.py", "api/routes/system/activity.py"):
        tree = ast.parse((SRC / rel).read_text())
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)):
            for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
                name = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
                if name in PER_PAGE:
                    offenders.append(f"{rel}::{fn.name} calls {name}")
    assert not offenders, offenders


def test_fifty_pages_with_no_lines_take_a_handful_of_database_calls_and_read_as_the_per_page_check_says(db, monkeypatch):
    """Find Lines' window: the pages have no lines yet, and `_has_reading` cost 3-4 queries each (## 826)."""
    from fichero_server.models import Artifact

    pages = [_page(db, 0, 0) for _ in range(50)]
    db.save(Artifact(document_id=pages[3], artifact_type="transcription", content="x", model="m", provider="p"))
    calls: list[str] = []
    real = db._execute_fetch_with_columns

    def counting(sql, *args, **kwargs):
        calls.append(sql[:60])
        return real(sql, *args, **kwargs)

    monkeypatch.setattr(db, "_execute_fetch_with_columns", counting)
    got = run_view.reading_counts(db, pages, blank=set())
    assert len(calls) <= 10, f"{len(calls)} database calls for 50 pages with no lines"
    monkeypatch.setattr(db, "_execute_fetch_with_columns", real)
    assert got.pages_fully_read == run_view.pages_fully_read(db, pages) == [pages[3]]


def test_a_summary_that_raises_leaves_the_tree_whole_with_a_reason(db, monkeypatch):
    from fichero_server.api.routes.system import activity
    from fichero_server.recipes import run_view as view

    async def state(_db, _id):
        return "done", None, {"steps": []}

    async def boom(_db, _id):
        raise RuntimeError("a row went missing")

    monkeypatch.setattr(activity, "_recipe_state", state)
    monkeypatch.setattr(view, "summary", boom)
    found = {"id": "r1", "children": [], "done": 0, "total": 0, "failed": 0}
    asyncio.run(activity._recipe_run(db, found))
    assert found["summary"] is None and "tried again" in found["summary_unavailable"]
    assert found["state"] == "done" and found["stages"] == []  # the rest of the tree is there


def test_a_line_vision_gave_up_on_is_counted_on_its_own_in_the_set_based_counts(db):
    """Folded in from #5901: `lines_vision_could_not_read` comes from the same two reads, apart from the lines found blank."""
    from fichero_server.llm.working_lines import VISION_NOTHING_TWICE, mark_unread_reasons

    page = _page(db, 4, 2)
    lines = [s.id for s in db.query(Segment, document_id=page) if s.kind == "line"][2:]
    mark_no_writing(db, lines, model="apple-vision")
    mark_unread_reasons(db, {lines[0]: VISION_NOTHING_TWICE})
    got = run_view.reading_counts(db, [page], blank=set())
    assert got.lines_vision_could_not_read == run_view.lines_vision_could_not_read(db, [page]) == 1
    assert got.lines_seen_blank == run_view.lines_seen_blank(db, [page]) == 1
