"""A workflow run is a job with its steps and pages as children (#5353, spec steps 3-4).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, "Workflow runs inside the one job
model": "A run is a parent job (kind = workflow) ... Each step is a child job (kind = workflow-step), one
per graph node ... Each page in a fanned-out step is a grandchild job". Written from the spec's text and
driven through the public surface: a real run started with `POST /api/workflow-execution/execute`,
followed with `GET /api/activity/jobs/{run}` and the run's status route, paused and stopped with the
job controls. Only the model call itself is a stub (a cloud model that answers from memory), and the
credential preflight is passed (a key check is not what these prove).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def no_embedding_model(monkeypatch):
    """Each saved page queues its re-embed (a job on the local-model lane). A run does not wait for
    it, but loading the real embedding model beside the run made these flake on a loaded machine
    (#5407: a 60 s wait ran out at load average ~15, while alone it takes 2 s). The embed itself
    is not what these prove, so the stage does nothing here."""
    from fichero_server.importers import derivatives

    monkeypatch.setattr(derivatives, "_embed_stage", lambda doc_id, library: None)


def _png(path: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")
    return path


@pytest.fixture
def pages(db, tmp_path):
    from fichero_server.models import DocType, Document, FileType

    docs = []
    for i in range(3):
        doc = Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image,
                       path=str(_png(tmp_path / f"p{i}.png")))
        db.save(doc)
        docs.append(doc)
    return docs


@pytest.fixture
def workflow(db):
    """Files in, one cloud-model transcription step."""
    from fichero_server.models import Workflow

    wf = Workflow(
        id="wf-cloud-transcribe", name="Transcribe with a cloud model", provider="openai", model="gpt-5",
        nodes=[
            {"id": "files-source", "tool": "files", "label": "Files", "inputs": {}, "config": {}},
            {"id": "transcribe", "tool": "transcribe", "label": "Transcribe",
             "inputs": {"files": "$.nodes.files-source.files", "documents": "$.nodes.files-source.documents"},
             "config": {"vision_mode": "llm", "update_page_content": True}},
        ],
        edges=[{"id": "e1", "source": "files-source", "target": "transcribe", "source_port": "files",
                "target_port": "files"}],
    )
    db.save(wf)
    return wf


class CloudModel:
    """A cloud vision model that answers from memory; records how many calls run at once."""

    def __init__(self, seconds=0.0):
        self.seconds = seconds
        self.calls = 0
        self.live = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.gate: threading.Event | None = None
        self.first_call = threading.Event()

    async def __call__(self, images, prompt, config, **kwargs):
        import asyncio

        with self.lock:
            self.calls += 1
            self.live += 1
            self.peak = max(self.peak, self.live)
        self.first_call.set()
        try:
            if self.gate is not None:
                await asyncio.to_thread(self.gate.wait, 30)
            await asyncio.sleep(self.seconds)
            return "vecino de la ciudad"
        finally:
            with self.lock:
                self.live -= 1


@pytest.fixture
def cloud(monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    model = CloudModel()
    monkeypatch.setattr(llm, "vision", model)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    return model


def _execute(client, workflow, docs):
    r = client.post("/api/workflow-execution/execute", json={
        "workflow_id": workflow.id, "inputs": {"selected_doc_ids": [d.id for d in docs]}, "skip_cache": True})
    assert r.status_code == 202, r.text
    return r.json()["thread_id"]


def _status(client, thread_id):
    return client.get(f"/api/workflow-execution/threads/{thread_id}/status").json().get("status")


def _wait_for(predicate, seconds=180.0):
    # Generous: it returns as soon as the predicate holds, and only a failure waits it out.
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _tree(client, job_id):
    r = client.get(f"/api/activity/jobs/{job_id}")
    assert r.status_code == 200, r.text
    return r.json()


def test_activity_jobs_are_a_tree__a_run_is_a_job_with_its_steps_and_pages(client, workflow, pages, cloud):
    """Behaviour `activity.jobs-are-a-tree`: "a job's children (steps, pages) are jobs; progress, time,
    cost and errors roll up the tree." And from "What a workflow run becomes": a run is a parent job
    (`workflow`), each step a child (`workflow-step`), each page in a fanned-out step a grandchild."""
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    assert _status(client, run) == "completed"

    tree = _tree(client, run)
    assert (tree["kind"], tree["state"]) == ("workflow", "done")
    steps = {child["subject"].split(":")[-1]: child for child in tree["children"]}
    assert set(steps) == {"Files", "Transcribe"}  # the run names its steps as its graph does
    assert all(step["kind"] == "workflow-step" and step["state"] == "done" for step in steps.values())
    page_rows = steps["Transcribe"]["children"]
    assert len(page_rows) == 3 and cloud.calls == 3
    assert {(p["kind"], p["model"], p["state"]) for p in page_rows} == {("read-a-page", "openai:gpt-5", "done")}
    # Progress rolls up: the run counts its three pages done.
    assert (tree["done"], tree["total"]) == (3, 3)


def test_activity_run_lane_cap_per_mac__two_runs_share_one_cap_on_cloud_calls(
        client, db, workflow, pages, cloud, monkeypatch):
    """Behaviour `activity.run.lane-cap-per-mac`: "the cap on concurrent model calls is one per Mac,
    shared by every run. Today it is per run ... three runs measured 12 calls at once against a cap
    of 4." Two runs of three pages each, with the network lane two wide, never make more than two
    cloud calls at once."""
    monkeypatch.setitem(jobs.LANES, "network", 2)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.seconds = 0.2
    first, second = _execute(client, workflow, pages), _execute(client, workflow, pages)
    assert _wait_for(lambda: _status(client, first) == "completed" and _status(client, second) == "completed")
    assert cloud.calls == 6
    assert cloud.peak <= 2


def test_activity_pause_per_job__pausing_the_run_row_holds_the_run(client, workflow, pages, cloud, monkeypatch):
    """Behaviour `activity.pause.per-job`: "Pause, Resume, Cancel on any row, applying to its
    children." Pausing a running run's row pauses the run at its next boundary: with the network lane
    one wide and the first call held, the pages still waiting never call the model, and the run and
    its row say paused."""
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.gate = threading.Event()
    run = _execute(client, workflow, pages)
    assert cloud.first_call.wait(30)
    r = client.put(f"/api/activity/jobs/{run}/paused", json={"paused": True})
    assert r.status_code == 200, r.text
    cloud.gate.set()
    assert _wait_for(lambda: _status(client, run) == "paused")
    time.sleep(0.5)
    assert cloud.calls == 1
    tree = _tree(client, run)
    assert tree["state"] == "paused"
    # The page in flight finishes; any other page that had reached the lane is stopped with the run
    # (a page whose branch had not yet reached it has no row at all).
    page_rows = [p for step in tree["children"] for p in step["children"]]
    assert [p["state"] for p in page_rows].count("done") == 1
    assert {(p["state"], p["reason"]) for p in page_rows if p["state"] != "done"} <= {
        ("cancelled", "Paused with its run"), ("cancelled", "Its run had ended before this page started"),
        ("cancelled", "Its run had ended before this page was read")}


def test_activity_pause_per_job__stopping_the_run_row_reaches_its_waiting_pages(
        client, workflow, pages, cloud, monkeypatch):
    """Behaviour `activity.pause.per-job` ("Cancel on any row, applying to its children") and
    `activity.run.stop-reaches-in-flight-calls` for the pages still waiting: with the network lane one
    wide and the first call held, Stop on the run row cancels the run, its waiting pages never call
    the model, and their rows say they were stopped."""
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.gate = threading.Event()
    run = _execute(client, workflow, pages)
    assert cloud.first_call.wait(30)
    assert _wait_for(lambda: sum(1 for p in _tree(client, run)["children"][-1]["children"]
                                 if p["state"] == "waiting") == 2)
    r = client.post(f"/api/activity/jobs/{run}/cancel")
    assert r.status_code == 200, r.text
    cloud.gate.set()
    assert _wait_for(lambda: _status(client, run) == "cancelled")
    time.sleep(0.3)
    assert cloud.calls == 1
    page_rows = [p for step in _tree(client, run)["children"] for p in step["children"]]
    assert sorted(p["state"] for p in page_rows) == ["cancelled", "cancelled", "done"]
