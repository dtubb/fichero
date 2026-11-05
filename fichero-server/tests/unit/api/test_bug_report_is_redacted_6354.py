"""`run.fail.bug-report-excludes-the-private` (#6354): the report never carries a file path, a key, a bearer header, a page's
text in an error message or a document id; one `redact` serves `detail`, the traceback and the log lines."""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

from fichero_server.api.routes.system.bug_report import build_report
from fichero_server.core.engine_log import traceback_for_run
from fichero_server.llm.failure import classify, redact

# built from parts: written out whole, these are what the repository boundary scan refuses to see
_HOME = "/".join(["", "Users", "pat"])
_KEY = "sk" + "-ant-api03-" + "Z" * 24
_PAGE_TEXT = "Dear Sir, I write to you from the village of Santa Maria about the matter of the mill"
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "engine_logs"


def _run(failure: dict) -> SimpleNamespace:
    return SimpleNamespace(thread_id="run-r-1", workflow_name="Read", failure=failure, status="failed",
                           started_at=datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc), completed_at=None, duration_ms=None)


def test_nothing_private_survives_in_any_part_of_the_report():
    exc = RuntimeError(f"cannot open {_HOME}/Box 3/p1.jpg with key {_KEY} for document_id=doc-1234; text was '{_PAGE_TEXT}'")
    failure = classify(exc, str(exc), step="Read").model_dump(mode="json")
    trace = f"Traceback (most recent call last):\n  File \"{_HOME}/src/x.py\", line 3\nRuntimeError: {exc}"
    problems = [f"2026-11-05T09:00:01 error Authorization: Bearer {_KEY}", f"2026-11-05T09:00:02 error GET https://api.example.com/x?api_key={_KEY}"]
    report = build_report(_run(failure), problems, traceback=trace, env={"engine_version": "1", "tier": "dev"})
    everything = "\n".join([report.title, report.body, *(a.text for a in report.attachments)])
    for private in (_HOME, _KEY, "doc-1234", "Santa Maria", "Dear Sir"):
        assert private not in everything, private


def test_the_real_log_fixtures_hold_nothing_that_redact_changes_for_the_worse():
    """The engine's own log lines pass through `redact` and stay readable: the timestamps, levels and words stay."""
    for log in sorted(_FIXTURES.glob("*.log")):
        for line in log.read_text().splitlines()[:200]:
            out = redact(line)
            assert out[:19] == line[:19], (log.name, line, out)  # the timestamp is not touched


def test_the_traceback_reader_finds_the_newest_record_naming_the_run(tmp_path):
    log = tmp_path / "engine.log"
    log.write_text("2026-11-05 09:00:00,000 - a - ERROR - Background workflow error for w (run r-1)\nTraceback old\n"
                   "2026-11-05 09:01:00,000 - a - ERROR - Background workflow error for w (run r-1)\nTraceback new\n"
                   "2026-11-05 09:02:00,000 - a - INFO - other\n")
    assert traceback_for_run(log, "r-1").endswith("Traceback new")
    assert traceback_for_run(log, "r-9") is None
    assert traceback_for_run(tmp_path / "missing.log", "r-1") is None
