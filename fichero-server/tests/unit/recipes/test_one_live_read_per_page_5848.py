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


def _live(thread, docs, status="running", db=DB, workflow="transcribe", reader="A"):
    runner._running_workflows[thread] = {"db_path": db, "workflow_id": workflow, "status": status,
                                         "documents": docs, "reader": reader, "workflow_name": "Transcribe"}


def _request(docs, model=None):
    return SimpleNamespace(workflow_id="transcribe", inputs={"selected_doc_ids": docs}, provider_override=None,
                           model_override=model)


def _wf(config=None):
    return SimpleNamespace(name="Transcribe", nodes=[{"id": "n1", "tool": "transcribe", "config": config or {}}],
                           edges=[])


def test_an_overlapping_live_run_is_found_with_the_pages_it_covers():
    _live("thread-a", ["p1", "p2"])
    assert runner.live_run_reading(DB, "transcribe", ["p2", "p3"], "A") == ("thread-a", {"p2"})


@pytest.mark.parametrize("args", [
    (DB, "transcribe", ["p9"], "A"),             # other pages
    (DB, "other", ["p1"], "A"),                  # other workflow
    ("/elsewhere.duckdb", "transcribe", ["p1"], "A"),  # other project
    (DB, "transcribe", [], "A"),                 # no pages named
    (DB, "transcribe", ["p1"], "B"),             # another reader (review 259 MED 2)
])
def test_no_overlap_is_not_a_live_read(args):
    _live("thread-a", ["p1", "p2"])
    assert runner.live_run_reading(*args) is None


@pytest.mark.parametrize("status", ["completed", "paused"])
def test_an_ended_or_paused_run_is_not_a_live_read(status):  # review 259 MED 3
    _live("thread-a", ["p1"], status=status)
    assert runner.live_run_reading(DB, "transcribe", ["p1"], "A") is None


def test_another_model_or_setting_is_another_reader_key():
    assert runner.reader_key(_wf(), _request(["p1"], "a")) != runner.reader_key(_wf(), _request(["p1"], "b"))
    assert runner.reader_key(_wf({"m": 1}), _request(["p1"])) != runner.reader_key(_wf({"m": 2}), _request(["p1"]))
    assert runner.reader_key(_wf(), _request(["p1"])) == runner.reader_key(_wf(), _request(["p2"]))


def test_start_run_refuses_a_second_that_is_wholly_covered_and_names_the_live_one():
    wf, request = _wf(), _request(["p2"])
    _live("thread-a", ["p1", "p2"], reader=runner.reader_key(wf, request))
    with pytest.raises(runner.AlreadyReading) as joined:
        asyncio.run(runner.start_run(SimpleNamespace(path=DB), wf, request, "thread-b"))
    assert joined.value.thread_id == "thread-a"
    assert "thread-b" not in runner._running_workflows


def test_a_partial_overlap_reads_the_rest(monkeypatch):  # review 259 MED 1
    wf, request = _wf(), _request(["p2", "p3"])
    _live("thread-a", ["p1", "p2"], reader=runner.reader_key(wf, request))
    stop = RuntimeError("stop after registering")

    class Store:
        async def save_workflow_run(self, **_):
            raise stop

    monkeypatch.setattr(runner, "get_activity_tracker", lambda _p: SimpleNamespace(store=Store()))
    with pytest.raises(RuntimeError, match="stop after registering"):
        asyncio.run(runner.start_run(SimpleNamespace(path=DB), wf, request, "thread-b"))
    assert runner._running_workflows["thread-b"]["documents"] == ["p3"]
    assert request.inputs["selected_doc_ids"] == ["p3"]


def test_a_paused_run_does_not_hold_back_a_new_start(monkeypatch):  # review 259 MED 3
    wf, request = _wf(), _request(["p1"])
    _live("thread-a", ["p1"], status="paused", reader=runner.reader_key(wf, request))

    class Store:
        async def save_workflow_run(self, **_):
            raise RuntimeError("registered")

    monkeypatch.setattr(runner, "get_activity_tracker", lambda _p: SimpleNamespace(store=Store()))
    with pytest.raises(RuntimeError, match="registered"):
        asyncio.run(runner.start_run(SimpleNamespace(path=DB), wf, request, "thread-b"))


def test_a_recipe_step_waits_for_the_live_run_and_names_it():
    from fichero_server.recipes import runner as recipe

    _live("thread-a", ["p1"])

    def end():
        time.sleep(0.2)
        runner._running_workflows["thread-a"]["status"] = "completed"

    threading.Thread(target=end).start()
    child, state, why = recipe._join_live_run("thread-a", "job-1")
    assert (child, state) == ("thread-a", "done")
    assert "Transcribe" in why and "thread-a" not in why


def test_a_recipe_step_never_waits_on_a_paused_run():  # review 259 MED 3
    from fichero_server.recipes import runner as recipe

    _live("thread-a", ["p1"], status="paused")
    with pytest.raises(recipe.ParkedOnStepRun) as parked:  # returns at once, not after a poll loop: the recipe parks (#5933)
        recipe._join_live_run("thread-a", "job-1")
    assert parked.value.thread_id == "thread-a"


def test_a_second_start_returns_while_the_first_is_joined():  # review 261 MED: the lock is not held while joining
    from fichero_server.recipes import runner as recipe

    wf, request = _wf(), _request(["p1"])
    _live("thread-a", ["p1"], reader=runner.reader_key(wf, request))
    joined = threading.Thread(target=recipe._join_live_run, args=("thread-a", "job-1"), daemon=True)
    joined.start()  # waits on the live run
    time.sleep(0.2)
    assert runner.LIVE_CHECK_LOCK.acquire(timeout=1), "a join must not hold the check lock"
    runner.LIVE_CHECK_LOCK.release()
    with pytest.raises(runner.AlreadyReading):
        asyncio.run(runner.start_run(SimpleNamespace(path=DB), wf, request, "thread-b"))
    runner._running_workflows["thread-a"]["status"] = "completed"
    joined.join(5)
