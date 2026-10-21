"""`activity.log.problems-first` (#5960): `GET /jobs/{id}/log?level=problems` returns warnings and errors only, newest last.

The person's log opens on Problems when any exist; Everything is the default read. Driven through the pure filter the
route applies and through the route's declared parameter (the log itself is read by `test_activity_details_5561.py`)."""
from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.api.routes.system.activity import JobLogLine, problem_lines


def _line(level: str, message: str, at: str = "2026-10-21T12:00:00+00:00") -> JobLogLine:
    return JobLogLine(timestamp=at, level=level, message=message, job_id="run")


def test_problems_are_the_warnings_errors_and_criticals_in_the_order_given():
    lines = [_line("info", "Started"), _line("warning", "Memory is tight"), _line("debug", "tick"),
             _line("error", "IMG_001 could not be read"), _line("critical", "The model server stopped"), _line("info", "Done")]
    assert [line.message for line in problem_lines(lines)] == [
        "Memory is tight", "IMG_001 could not be read", "The model server stopped"]


def test_a_log_with_no_problem_has_none_to_show():
    assert problem_lines([_line("info", "Started"), _line("info", "Done")]) == []


def test_the_route_takes_level_and_everything_is_the_default():
    operation = app.openapi()["paths"]["/api/activity/jobs/{job_id}/log"]["get"]
    level = next(p for p in operation["parameters"] if p["name"] == "level")
    assert level["schema"].get("default") == "all"
    assert set(level["schema"]["enum"]) == {"all", "problems"}
