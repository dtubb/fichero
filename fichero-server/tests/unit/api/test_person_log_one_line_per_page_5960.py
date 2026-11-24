"""`activity.log.one-line-per-page` (#5960): the log keys its lines by (run, stage, page): one line per stage start and end and one per failed
page, never a "Done: <file>" per lane row (a page recurs once per step)."""
from __future__ import annotations

from fichero_server.api.routes.system.activity import _job_rows_log


def _page(doc, state, reason=None):
    return {"id": f"row-{doc}-{state}-{reason}", "name": "Read", "display_name": doc, "state": state, "reason": reason,
            "document_id": doc, "started_at": "2026-11-02T10:00:00+00:00", "finished_at": "2026-11-02T10:00:05+00:00", "children": []}


def _stage():
    steps = [{"id": "w1:find-lines", "kind": "workflow-step", "name": "Find lines", "state": "done", "children": [
                 _page("IMG_1", "done"), _page("IMG_2", "done")]},
             {"id": "w1:read-a-line", "kind": "workflow-step", "name": "Read", "state": "done", "children": [
                 _page("IMG_1", "done"), _page("IMG_2", "failed", "no lines"), _page("IMG_2", "failed", "no lines")]}]
    return {"id": "w1", "kind": "workflow", "name": "Read the pages", "state": "done", "started_at": "2026-11-02T09:59:00+00:00",
            "finished_at": "2026-11-02T10:01:00+00:00", "children": steps}


def test_a_stage_says_its_end_once_and_no_page_says_done():
    messages = [line.message for line in _job_rows_log(_stage())]
    assert messages.count("Done: Read the pages") == 1
    assert not [m for m in messages if m.startswith("Done: IMG")]


def test_a_failed_page_is_one_line_for_the_stage_however_many_rows_it_failed_in():
    failed = [line.message for line in _job_rows_log(_stage()) if line.level == "error"]
    assert failed == ["Failed: IMG_2: no lines"]


def _event(node, level, page=None, message="Image looks blank"):
    from types import SimpleNamespace

    return SimpleNamespace(node_id=node, level=level, message=message, metadata={"document_id": page} if page else {})


def test_the_events_say_a_page_once_a_node_and_level_and_keep_what_is_about_no_page():
    from fichero_server.api.routes.system.activity import one_event_per_page

    events = [_event("find-lines", "warning", "IMG_2"), _event("find-lines", "warning", "IMG_2"),
              _event("find-lines", "error", "IMG_2"), _event("read-a-line", "warning", "IMG_2"),
              _event("find-lines", "warning", "IMG_3"), _event("find-lines", "info"), _event("find-lines", "info")]
    kept = one_event_per_page(events)
    assert [(e.node_id, e.level, (e.metadata or {}).get("document_id")) for e in kept] == [
        ("find-lines", "warning", "IMG_2"), ("find-lines", "error", "IMG_2"), ("read-a-line", "warning", "IMG_2"),
        ("find-lines", "warning", "IMG_3"), ("find-lines", "info", None), ("find-lines", "info", None)]
