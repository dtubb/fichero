"""A page whose work raises the run's pause is recorded as paused, not failed, and the text refinement does not swallow a
Stop or Pause (#5919 sweep, ## 602): else Activity says 'failed' for a pause, and a page is marked done unrefined and never redone."""
from __future__ import annotations

import asyncio
import time

import pytest

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowCancelled, WorkflowPaused

KIND = "pausing-page-pp"


def test_work_that_raises_the_pause_leaves_a_paused_row_not_a_failed_one(db, monkeypatch):
    def work(db_, subject):
        raise WorkflowPaused("run-1")

    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=work, model=None, lane="local-ml", name="Read a page"))
    job_id = jobs.enqueue(db, KIND, "p1")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and jobs.read_job(db, job_id)["state"] in ("waiting", "running"):
        time.sleep(0.02)
    row = jobs.read_job(db, job_id)
    assert row["state"] == "cancelled" and row["reason"] == "Paused with its run", row


@pytest.mark.parametrize("exc", [WorkflowPaused("r"), WorkflowCancelled("r")])
def test_the_text_refinement_lets_a_pause_or_stop_through(monkeypatch, exc):
    from fichero_server import llm
    from fichero_server.workflows.tools import text_reflow

    async def stopped(**_kw):
        raise exc

    monkeypatch.setattr(llm, "call_llm_with_cache", stopped, raising=False)  # the name does not exist in llm today: see the last test
    config = llm.LLMConfig(provider="openai", model="gpt-x")
    with pytest.raises(type(exc)):
        asyncio.run(text_reflow._refine_with_llm("some text", config))


def test_the_text_refinement_still_falls_back_to_the_text_on_an_ordinary_failure(monkeypatch):
    from fichero_server import llm
    from fichero_server.workflows.tools import text_reflow

    async def broken(**_kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "call_llm_with_cache", broken, raising=False)
    config = llm.LLMConfig(provider="openai", model="gpt-x")
    assert asyncio.run(text_reflow._refine_with_llm("some text", config)) == "some text"


def test_the_refinement_function_it_calls_does_not_exist_today():
    """Honest pin (found by the M4 run of this file): `fichero_server.llm` has no `call_llm_with_cache`, so the AI refinement
    (`use_ai_refinement`) has always raised ImportError, swallowed into 'return the heuristic text'. The tests above inject the
    name so the Pause/Stop re-raise is exercised; when the refinement is built or removed (#5921) this test is deleted."""
    from fichero_server import llm

    assert not hasattr(llm, "call_llm_with_cache")


def test_a_missing_refinement_keeps_the_reflowed_text_and_says_so_once_per_run(monkeypatch):
    """#5921: the page finishes with its heuristic text (not a raw 'cannot import name'); the run is told once, in words."""
    from fichero_server import llm
    from fichero_server.workflows.tools import text_reflow

    assert not hasattr(llm, "call_llm_with_cache")  # tripwire: delete this test when #5921 builds or removes the refinement
    said: list[str] = []
    monkeypatch.setattr(text_reflow, "_said_for", set())
    monkeypatch.setattr(text_reflow.logger, "warning", lambda message, *a: said.append(message))
    config = llm.LLMConfig(provider="openai", model="gpt-x")
    for _ in range(3):  # three pages of one run
        assert asyncio.run(text_reflow._refine_with_llm("some text", config)) == "some text"
    assert said == [text_reflow.REFINEMENT_UNAVAILABLE] and "#5921" in said[0] and "isn't available yet" in said[0]


def test_the_note_is_an_activity_warning_in_the_runs_library(monkeypatch):
    """#5921 (## 619): with a library the one-per-run note goes to that library's Activity tracker as a warning, in words."""
    from types import SimpleNamespace

    from fichero_server.workflows import activity, node_context
    from fichero_server.workflows.activity_types import ActivityLevel
    from fichero_server.workflows.tools import text_reflow

    logged = []
    monkeypatch.setattr(text_reflow, "_said_for", set())
    monkeypatch.setattr("fichero_server.db.db_manager.get_database", lambda path: SimpleNamespace(path=f"{path}/fichero.duckdb"))
    monkeypatch.setattr(activity, "get_activity_tracker", lambda db_path=None: SimpleNamespace(log=lambda **kw: logged.append((db_path, kw))))
    node_context.set_current_node("n1", "Reflow", "wf1", "run-1", "text_reflow")
    for _ in range(2):
        text_reflow._say_refinement_unavailable("/lib.fichero")
    assert len(logged) == 1
    db_path, entry = logged[0]
    assert db_path == "/lib.fichero/fichero.duckdb" and entry["level"] == ActivityLevel.WARNING
    assert entry["message"] == text_reflow.REFINEMENT_UNAVAILABLE and entry["thread_id"] == "run-1" and entry["workflow_id"] == "wf1"
