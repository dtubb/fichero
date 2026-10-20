"""A Pause through the REAL runner keeps the pages that are reading and reads nothing twice (#5932,
`activity.durable.paused-stays-paused`, `activity.durable.nothing-twice`; Fable runner review 2, finding 1).

The builder-level test (`test_pause_keeps_finished_pages_5919.py`) drives the graph itself. The runner is what returned from its
event stream at the first event after a Pause, which cancelled the page mid-read: its paid result was lost and Resume read it
again (the M4's calls = 4 for three pages). Here a run is started with `POST /api/workflow-execution/execute`, paused with the
job control while page 2 is inside the model call, then resumed.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling test module
from __future__ import annotations

import asyncio
import threading
import time

from fichero_server.execution import jobs
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _tree,
    _wait_for,
    no_embedding_model,
    pages,
    workflow,
)


class GatedModel:
    """A cloud vision model whose Nth call waits for its own gate; counts every call made."""

    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()
        self.gates = [threading.Event() for _ in range(8)]
        self.started = [threading.Event() for _ in range(8)]

    async def __call__(self, images, prompt, config, **kwargs):
        with self.lock:
            index = self.calls
            self.calls += 1
        self.started[index].set()
        await asyncio.to_thread(self.gates[index].wait, 30)
        return "vecino de la ciudad"


def test_pages_reading_at_pause_finish_and_nothing_is_read_twice(client, workflow, pages, monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    model = GatedModel()
    monkeypatch.setattr(llm, "vision", model)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())

    run = _execute(client, workflow, pages)
    assert model.started[0].wait(30)
    model.gates[0].set()  # page 0 is done
    assert model.started[1].wait(30)  # page 1 is mid-read
    assert client.put(f"/api/activity/jobs/{run}/paused", json={"paused": True}).status_code == 200
    time.sleep(0.5)  # events keep arriving at the runner; the old runner returned on the first and cancelled page 1
    model.gates[1].set()  # page 1's read ends
    assert _wait_for(lambda: _status(client, run) == "paused")

    tree = _tree(client, run)
    page_rows = [p for step in tree["children"] for p in step["children"]]
    assert [p["state"] for p in page_rows].count("done") == 2, [(p["state"], p["reason"]) for p in page_rows]
    assert not any(p["reason"] and "run had ended" in p["reason"] for p in page_rows), "a paused run's page is never 'run had ended'"
    assert model.calls == 2, "the page reading at Pause finished; nothing else started"

    assert client.put(f"/api/activity/jobs/{run}/paused", json={"paused": False}).status_code == 200
    model.gates[2].set()
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    assert _status(client, run) == "completed"
    assert model.calls == 3, f"each page is read once across Pause and Resume: {model.calls} calls for 3 pages"
