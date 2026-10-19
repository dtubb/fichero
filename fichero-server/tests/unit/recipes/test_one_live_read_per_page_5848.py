"""#5848: a second run on pages a live run already reads joins it; the pages are never read twice."""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from fichero_server.execution import runner

DB = "/tmp/p.fichero/fichero.duckdb"


@pytest.fixture(autouse=True)
def _clean():
    saved = dict(runner._running_workflows)
    runner._running_workflows.clear()
    yield
    runner._running_workflows.clear()
    runner._running_workflows.update(saved)


def _live(thread, docs, status="running", db=DB, workflow="transcribe"):
    runner._running_workflows[thread] = {"db_path": db, "workflow_id": workflow, "status": status,
                                         "documents": docs}


def test_an_overlapping_live_run_is_found():
    _live("thread-a", ["p1", "p2"])
    assert runner.live_run_reading(DB, "transcribe", ["p2", "p3"]) == "thread-a"


@pytest.mark.parametrize("args", [
    (DB, "transcribe", ["p9"]),             # other pages
    (DB, "other", ["p1"]),                  # other workflow
    ("/elsewhere.duckdb", "transcribe", ["p1"]),  # other project
    (DB, "transcribe", []),                 # no pages named
])
def test_no_overlap_is_not_a_live_read(args):
    _live("thread-a", ["p1", "p2"])
    assert runner.live_run_reading(*args) is None


def test_an_ended_run_is_not_a_live_read():
    _live("thread-a", ["p1"], status="completed")
    assert runner.live_run_reading(DB, "transcribe", ["p1"]) is None


def test_start_run_refuses_the_second_and_names_the_live_one():
    _live("thread-a", ["p1", "p2"])
    request = SimpleNamespace(workflow_id="transcribe", inputs={"selected_doc_ids": ["p2"]})
    with pytest.raises(runner.AlreadyReading) as joined:
        asyncio.run(runner.start_run(SimpleNamespace(path=DB), SimpleNamespace(name="Transcribe"), request, "thread-b"))
    assert joined.value.thread_id == "thread-a"
    assert "thread-b" not in runner._running_workflows


def test_a_recipe_step_waits_for_the_live_run_and_reports_its_outcome():
    from fichero_server.recipes import runner as recipe

    _live("thread-a", ["p1"])

    def end():
        time.sleep(0.2)
        runner._running_workflows["thread-a"]["status"] = "completed"

    threading.Thread(target=end).start()
    child, state, why = recipe._join_live_run(SimpleNamespace(), "thread-a", "job-1")
    assert (child, state) == ("thread-a", "done")
    assert "thread-a" in (why or "")
