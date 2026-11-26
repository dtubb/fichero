"""A run a schedule or a file trigger started runs on a background-QoS thread; one a person started does not (#4740)."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from fichero_server.core import background_compute
from fichero_server.execution import runner


def _start(monkeypatch, started_by):
    """Start a run with everything but the thread's QoS stubbed; return the thread names that dropped QoS."""
    dropped: list[str] = []
    monkeypatch.setattr(background_compute, "set_background_qos", lambda *a, **k: dropped.append(threading.current_thread().name))

    async def body(**kw):
        return None

    monkeypatch.setattr(runner, "_run_workflow_in_background", body)
    monkeypatch.setattr(runner, "live_run_reading", lambda *a, **k: None)
    monkeypatch.setattr(runner, "reader_key", lambda *a, **k: "r")
    monkeypatch.setattr(runner, "_set_workflow_state", lambda *a, **k: None)
    save = SimpleNamespace(store=SimpleNamespace(save_workflow_run=_noop))
    monkeypatch.setattr(runner, "get_activity_tracker", lambda *a, **k: save)
    from fichero_server.execution import jobs
    monkeypatch.setattr(jobs, "set_started_by", lambda *a, **k: None)
    workflow = SimpleNamespace(id="wf", name="wf", nodes=[], edges=[])
    request = SimpleNamespace(workflow_id="wf", inputs={})
    db = SimpleNamespace(path="/x/library.db")
    finished = asyncio.run(runner.start_run(db, workflow, request, "t1", started_by=started_by))
    assert finished.wait(10)
    return dropped


async def _noop(**kw):
    return None


@pytest.mark.parametrize("starter", ["schedule", "trigger"])
def test_a_schedule_or_trigger_run_drops_to_background_qos(monkeypatch, starter):
    assert _start(monkeypatch, starter) == ["workflow-t1"]


@pytest.mark.parametrize("starter", [None, "person"])
def test_a_run_a_person_started_keeps_its_priority(monkeypatch, starter):
    assert _start(monkeypatch, starter) == []
