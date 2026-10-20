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

    monkeypatch.setattr(llm, "call_llm_with_cache", stopped)
    config = llm.LLMConfig(provider="openai", model="gpt-x")
    with pytest.raises(type(exc)):
        asyncio.run(text_reflow._refine_with_llm("some text", config))


def test_the_text_refinement_still_falls_back_to_the_text_on_an_ordinary_failure(monkeypatch):
    from fichero_server import llm
    from fichero_server.workflows.tools import text_reflow

    async def broken(**_kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "call_llm_with_cache", broken)
    config = llm.LLMConfig(provider="openai", model="gpt-x")
    assert asyncio.run(text_reflow._refine_with_llm("some text", config)) == "some text"
