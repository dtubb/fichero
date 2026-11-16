"""`run.fail.run-carries-its-failure`, recipe half (#6354): a recipe run's failed workflow stage carries the run's own
`failure` with `step` filled; its `why` words are not touched; any other stage carries none."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fichero_server.llm.failure import classify
from fichero_server.recipes import run_view
from fichero_server.workflows.activity import get_activity_tracker


class _Db:
    def __init__(self, path):
        self.path = path


@pytest.mark.asyncio
async def test_a_failed_workflow_stage_carries_its_runs_failure_named_for_the_stage(tmp_path):
    db = _Db(tmp_path / "lib.duckdb")
    store = get_activity_tracker(str(db.path)).store
    await store.save_workflow_run(thread_id="child-1", workflow_id="wf", workflow_name="Read",
                                  started_at=datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc))
    failure = classify(RuntimeError("boom"), "boom").model_dump(mode="json")
    await store.update_workflow_run("child-1", status="failed", error="boom", failure=failure,
                                    completed_at=datetime(2026, 11, 5, 9, 5, tzinfo=timezone.utc))
    step = {"state": "failed", "card": "workflow", "child_id": "child-1", "title": "Read each line", "why": "boom"}
    got = await run_view._step_failure(db, step)
    assert got["kind"] == "unexpected" and got["step"] == "Read each line"
    assert step["why"] == "boom"


@pytest.mark.asyncio
async def test_a_stage_that_has_not_failed_carries_none(tmp_path):
    db = _Db(tmp_path / "lib.duckdb")
    for step in ({"state": "done", "card": "workflow", "child_id": "x"}, {"state": "failed", "card": "find-documents", "child_id": "x"},
                 {"state": "failed", "card": "workflow"}):
        assert await run_view._step_failure(db, step) is None
