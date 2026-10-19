"""The person's log and the Developer level (`activity.log.persons-log`, `activity.log.developer-level`; #5850): by default
a job's log holds one line per page or stage done or failed and the warnings and errors, each sentence once per row; the
debug lines ("Node 'x' started", a row's start, what a row waits for now, a server's output) are the Developer level, off
unless asked for."""
from __future__ import annotations

import pytest

from fichero_server.api.routes.system.activity import JobLogLine, _event_detail, _job_rows_log, person_lines


def _line(message, job_id="p1", detail="person", level="info"):
    return JobLogLine(timestamp="2026-10-19T12:00:00+00:00", level=level, message=message, job_id=job_id, detail=detail)


@pytest.mark.parametrize("message", ["Node 'transcribe' started", "Node 'transcribe' completed in 120ms"])
def test_node_started_and_completed_lines_are_the_developer_level(message):
    assert _event_detail("info", message) == "developer"


def test_a_failed_node_and_a_warning_are_the_persons():
    assert _event_detail("error", "Node 'transcribe' failed: the model refused") == "person"
    assert _event_detail("warning", "Memory is short; waiting") == "person"
    assert _event_detail("debug", "anything") == "developer"


def test_a_rows_start_and_wait_are_developer_lines_and_its_end_is_the_persons():
    node = {"id": "p1", "name": "Read a page", "display_name": "p1.png", "state": "failed", "reason": "no model",
            "started_at": "2026-10-19T12:00:00+00:00", "finished_at": "2026-10-19T12:00:05+00:00", "children": []}
    by = {line.message: line.detail for line in _job_rows_log(node)}
    assert by["Started p1.png"] == "developer" and by["Failed: p1.png: no model"] == "person"
    waiting = _job_rows_log({"id": "p2", "name": "x", "state": "waiting", "reason": "Waiting for the model lane",
                             "children": []})
    assert [line.detail for line in waiting] == ["developer"]


def test_the_persons_log_drops_developer_lines_and_never_repeats_a_sentence():
    lines = [_line("Done: p1.png"), _line("Done: p1.png"), _line("Node 'a' started", detail="developer"),
             _line("Done: p1.png", job_id="p2")]
    kept = person_lines(lines)
    assert [(k.job_id, k.message) for k in kept] == [("p1", "Done: p1.png"), ("p2", "Done: p1.png")]
