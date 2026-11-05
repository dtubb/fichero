"""`run.fail.run-carries-its-failure` and `run.fail.one-failure-per-attempt` (#6354): a run that ends failed keeps its
`RunFailure` beside its `error` words; a run that goes on is not failed any more; the runner's ends write it."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fichero_server.execution import runner
from fichero_server.llm.failure import classify
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.activity_store import ActivityStore


def _store(tmp_path: Path) -> ActivityStore:
    return ActivityStore(str(tmp_path / "activity.duckdb"))


async def _run(store: ActivityStore, thread_id: str = "run-1") -> str:
    await store.save_workflow_run(thread_id=thread_id, workflow_id="wf", workflow_name="Read pages",
                                  started_at=datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc))
    return thread_id


def _failure(kind_exc: BaseException, **where) -> dict:
    return classify(kind_exc, str(kind_exc), **where).model_dump(mode="json")


@pytest.mark.asyncio
async def test_a_failed_run_keeps_its_failure_beside_its_words(tmp_path):
    store = _store(tmp_path)
    run_id = await _run(store)
    failure = _failure(cb.provider_stopped_error("openrouter", "quota"), provider="openrouter", step="Read pages", done=12, total=203)
    await store.update_workflow_run(run_id, status="failed", error="OpenRouter has no credit", failure=failure,
                                    completed_at=datetime(2026, 11, 5, 9, 5, tzinfo=timezone.utc))
    run = await store.get_workflow_run(run_id)
    assert run.error == "OpenRouter has no credit"  # the words stay where everything that reads `reason` finds them
    assert run.failure["kind"] == "no-credit" and run.failure["pages_done"] == 12


@pytest.mark.asyncio
async def test_a_run_that_was_paused_by_a_person_has_no_failure(tmp_path):
    store = _store(tmp_path)
    run_id = await _run(store)
    await store.update_workflow_run(run_id, status="paused")
    assert (await store.get_workflow_run(run_id)).failure is None


@pytest.mark.asyncio
async def test_a_retried_run_is_not_failed_and_a_second_failure_is_a_new_one(tmp_path):
    store = _store(tmp_path)
    run_id = await _run(store)
    first = _failure(cb.provider_stopped_error("openrouter", "quota"))
    await store.update_workflow_run(run_id, status="failed", error="x", failure=first,
                                    completed_at=datetime(2026, 11, 5, 9, 5, tzinfo=timezone.utc))
    await store.update_workflow_run(run_id, status="running")  # Retry
    assert (await store.get_workflow_run(run_id)).failure is None
    second = _failure(cb.provider_stopped_error("openrouter", "key"))
    await store.update_workflow_run(run_id, status="failed", error="y", failure=second,
                                    completed_at=datetime(2026, 11, 5, 9, 9, tzinfo=timezone.utc))
    run = await store.get_workflow_run(run_id)
    assert run.failure["kind"] == "key-refused" and run.completed_at.minute == 9  # told apart by `id@failed_at`


@pytest.mark.asyncio
async def test_the_jobs_list_and_the_status_route_serve_the_runs_failure(tmp_path):
    from fichero_server.api.routes.workflow_execution.schemas import ExecutionStatusResponse

    store = _store(tmp_path)
    run_id = await _run(store)
    failure = _failure(RuntimeError("boom"), step="Read pages")
    await store.update_workflow_run(run_id, status="failed", error="boom", failure=failure,
                                    completed_at=datetime(2026, 11, 5, 9, 5, tzinfo=timezone.utc))
    run = await store.get_workflow_run(run_id)
    served = ExecutionStatusResponse(thread_id=run_id, workflow_id="wf", workflow_name="Read pages", status="failed",
                                     error=run.error, failure=run.failure)
    assert served.failure.kind == "unexpected" and served.failure.exception_type == "RuntimeError"
    from fichero_server.api.routes.system.activity import BackgroundJob

    job = BackgroundJob(id=run_id, task_type="workflow", name="Read pages", current=0, total=0, percent=0, state="failed",
                        reason=run.error, failure=run.failure)
    assert job.failure.kind == "unexpected" and job.reason == "boom"


@pytest.mark.asyncio
async def test_a_run_that_dies_in_a_node_writes_its_failure_once_and_the_stream_says_it(monkeypatch):
    """Driven through the real background runner: the run's end writes one `failure` of the table's kind, and the error event
    on the stream carries the same one."""
    import tempfile

    from fichero_server.db import Database
    from tests.unit.workflows.test_run_step_failure_legibility import _drive_failing_run

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "fichero.duckdb")
        try:
            tracker = await _drive_failing_run(monkeypatch, db, "run-fail-1")  # the app raises "provider returned 401"
            replay = list(runner._get_workflow_state("run-fail-1")["events"]._buffer)
        finally:
            db.close()
    written = [u for u in tracker.store.updates if u.get("status") == "failed"]
    assert len(written) == 1 and written[0]["failure"]["kind"] == "key-refused"
    assert written[0]["failure"]["step"] == "Dies"
    carried = [e for e in replay if getattr(e, "event", None) == "error"]
    assert carried and carried[-1].data["failure"] == written[0]["failure"]


@pytest.mark.asyncio
async def test_the_catch_all_logs_the_whole_traceback_once_with_the_run_id(monkeypatch, caplog):
    """`run.fail.unexpected-is-logged-whole`: a run that dies in a node writes ONE ERROR to the engine log with the run id and the
    traceback (`exc_info`), driven through the real background runner."""
    import tempfile
    from pathlib import Path

    from fichero_server.db import Database
    from tests.unit.workflows.test_run_step_failure_legibility import _drive_failing_run

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "fichero.duckdb")
        try:
            with caplog.at_level(logging.ERROR):
                await _drive_failing_run(monkeypatch, db, "run-log-1")
        finally:
            db.close()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and "run-log-1" in r.getMessage()]
    assert len(errors) == 1 and errors[0].exc_info and errors[0].exc_info[0] is RuntimeError


@pytest.mark.asyncio
async def test_only_an_empty_failure_clears_other_empty_values_are_written_as_they_were(tmp_path):
    """`update_run` is shared: an empty `run_usage` or `progress_timeline` is still stored as `{}`, not NULL."""
    store = _store(tmp_path)
    run_id = await _run(store)
    await store.update_workflow_run(run_id, status="running", run_usage={}, progress_timeline={})
    raw = store.db.execute_fetchone("SELECT run_usage, progress_timeline, failure FROM workflowrunrecords WHERE id = ?", [run_id])
    assert raw[0] == "{}" and raw[1] == "{}" and raw[2] is None
