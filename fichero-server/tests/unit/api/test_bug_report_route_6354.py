"""`run.fail.bug-report-route` and `run.fail.bug-report-contents` (#6354): `POST /api/activity/jobs/{id}/bug-report` over HTTP
builds the report of a failed run: a title, a plain-text body, `run.json` and `log.txt`; 409 in words for a run that did not fail,
404 for a run the project does not have."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fichero_server.llm.failure import classify
from fichero_server.workflows.activity import get_activity_tracker


def _run(db, run_id: str, *, status: str, failure: dict | None = None) -> None:
    store = get_activity_tracker(str(db.path)).store

    async def seed():
        await store.save_workflow_run(thread_id=run_id, workflow_id="wf", workflow_name="Read each line",
                                      started_at=datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc))
        await store.update_workflow_run(run_id, status=status, error="boom" if failure else None, failure=failure,
                                        duration_ms=61000, completed_at=datetime(2026, 11, 5, 9, 1, tzinfo=timezone.utc))

    asyncio.run(seed())


def test_a_failed_run_has_a_report_with_every_named_field(client, db):
    failure = classify(RuntimeError("boom"), "boom", step="Read each line", provider="openrouter", model="some/model",
                       done=12, total=203).model_dump(mode="json")
    _run(db, "run-bug-1", status="failed", failure=failure)
    r = client.post("/api/activity/jobs/run-bug-1/bug-report")
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["title"].startswith("unexpected: Something went wrong inside Fichero")
    body = report["body"]
    for needed in ("run_id: run-bug-1", "workflow: Read each line", "step: Read each line", "provider: OpenRouter",
                   "model: some/model", "pages_done: 12", "pages_total: 203", "started_at: 2026-11-05T09:00",
                   "ended_at: 2026-11-05T09:01", "duration_ms: 61000", "engine_version:", "tier:", "macos:",
                   "exception: RuntimeError: boom"):
        assert needed in body, needed
    assert [a["name"] for a in report["attachments"]] == ["run.json", "log.txt"]


def test_a_run_that_did_not_fail_answers_409_in_words(client, db):
    _run(db, "run-bug-2", status="completed")
    r = client.post("/api/activity/jobs/run-bug-2/bug-report")
    assert r.status_code == 409 and "did not fail" in r.json()["detail"]


def test_a_run_the_project_does_not_have_is_404(client, db):
    assert client.post("/api/activity/jobs/no-such-run/bug-report").status_code == 404


def test_an_unexpected_failure_carries_its_traceback_from_the_engine_log(client, db, tmp_path, monkeypatch):
    log = tmp_path / "engine.log"
    log.write_text(
        "2026-11-05 09:00:30,000 - fichero_server.execution.runner - ERROR - Background workflow error for wf (run run-bug-3)\n"
        "Traceback (most recent call last):\n  File \"x.py\", line 1, in f\nRuntimeError: boom\n"
        "2026-11-05 09:00:31,000 - fichero_server.db - INFO - later line\n")
    monkeypatch.setenv("FICHERO_ENGINE_LOG_PATH", str(log))
    failure = classify(RuntimeError("boom"), "boom", step="Read").model_dump(mode="json")
    _run(db, "run-bug-3", status="failed", failure=failure)
    body = client.post("/api/activity/jobs/run-bug-3/bug-report").json()["body"]
    assert "traceback:" in body and "Traceback (most recent call last)" in body and "later line" not in body
