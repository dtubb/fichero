"""A text model's calls in a run are jobs on the lanes, like a vision model's pages (#5358, #5353).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md: `activity.jobs-are-a-tree`
("pages of tools that do not hand their model calls to a lane (text extraction, chat)" was its
gap) and `activity.run.lane-cap-per-mac` ("text-model calls (extraction, summaries)" was its gap).
Written from the spec's text, and driven through the public surface: a real run started with
`POST /api/workflow-execution/execute`, followed with `GET /api/activity/jobs/{run}`, stopped with
the job controls. Only the model itself is a stub: a cloud chat model that answers from memory,
reached through the real `llm.chat` path; the credential preflight is passed.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fichero_server.execution import jobs
from tests.unit.jobs.test_runs_are_jobs import _execute, _status, _tree, _wait_for, no_embedding_model  # noqa: F401


@pytest.fixture
def pages(db, tmp_path):
    from fichero_server.models import DocType, Document, FileType

    docs = []
    for i in range(3):
        text = f"Letter {i}: the vecino of Cartagena sold a house."
        path = tmp_path / f"letter-{i}.txt"
        path.write_text(text, encoding="utf-8")
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.text, path=str(path),
                       page_content=text)
        db.save(doc)
        docs.append(doc)
    return docs


@pytest.fixture
def workflow(db):
    """Files in, entities read by a cloud model (as Mosquera's entity runs do)."""
    from fichero_server.models import Workflow

    wf = Workflow(
        id="wf-cloud-entities", name="Entities with a cloud model", provider="openai", model="gpt-5",
        nodes=[
            {"id": "files-source", "tool": "files", "label": "Files", "inputs": {}, "config": {}},
            {"id": "entities", "tool": "extract_entities_only", "label": "Entities",
             "inputs": {"documents": "$.nodes.files-source.documents"}, "config": {}},
        ],
        edges=[{"id": "e1", "source": "files-source", "target": "entities", "source_port": "documents",
                "target_port": "documents"}],
    )
    db.save(wf)
    return wf


class ChatModel:
    """A cloud chat model that answers from memory (finding nothing, when asked for structure);
    records how many calls run at once."""

    def __init__(self):
        self.calls = 0
        self.live = 0
        self.peak = 0
        self.seconds = 0.0
        self.lock = threading.Lock()
        self.gate: threading.Event | None = None
        self.first_call = threading.Event()

    async def ainvoke(self, messages, *a, **k):
        from langchain_core.messages import AIMessage

        with self.lock:
            self.calls += 1
            self.live += 1
            self.peak = max(self.peak, self.live)
        self.first_call.set()
        try:
            if self.gate is not None:
                await asyncio.to_thread(self.gate.wait, 30)
            await asyncio.sleep(self.seconds)
            return AIMessage(content="A house was sold.")
        finally:
            with self.lock:
                self.live -= 1

    def with_structured_output(self, schema, **kwargs):
        model = self

        class Structured:
            async def ainvoke(self, messages, *a, **k):
                raw = await model.ainvoke(messages)
                return {"raw": raw, "parsed": schema.model_construct(), "parsing_error": None}

        return Structured()


@pytest.fixture
def cloud(monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    model = ChatModel()
    monkeypatch.setattr(llm, "get_langchain_model", lambda config, *a, **k: model)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    return model


def test_activity_jobs_are_a_tree__a_text_models_calls_are_jobs_under_their_step(client, workflow, pages, cloud):
    """Behaviour `activity.jobs-are-a-tree`: "a job's children (steps, pages) are jobs". A text
    tool's model calls (an entity extraction) are rows under its step, named by model, like a
    vision model's pages."""
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    assert _status(client, run) == "completed"
    assert cloud.calls == 3
    steps = {child["subject"].split(":")[-1]: child for child in _tree(client, run)["children"]}
    calls = steps["Entities"]["children"]
    assert {(c["kind"], c["model"], c["state"]) for c in calls} == {("ask-a-model", "openai:gpt-5", "done")}
    assert len(calls) == 3


def test_activity_run_lane_cap_per_mac__text_calls_of_three_runs_share_one_cap(client, workflow, pages, cloud, monkeypatch):
    """Behaviour `activity.run.lane-cap-per-mac`: "the cap on concurrent model calls is one per Mac,
    shared by every run." Three entity runs (each asks about its letters one after another), with
    the network lane two wide, never make more than two calls at once."""
    monkeypatch.setitem(jobs.LANES, "network", 2)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.seconds = 0.3
    runs = [_execute(client, workflow, pages) for _ in range(3)]
    assert _wait_for(lambda: all(_status(client, run) == "completed" for run in runs))
    assert cloud.calls == 9
    assert cloud.peak <= 2


def test_activity_pause_per_job__stopping_the_run_reaches_its_next_text_calls(client, workflow, pages, cloud):
    """Behaviour `activity.pause.per-job` ("Cancel on any row, applying to its children"): with the
    first call held, Stop on the run row ends the run, and none of its later calls reaches the
    model (the entity reader asks about its letters one after another, each through the lane)."""
    cloud.gate = threading.Event()
    run = _execute(client, workflow, pages)
    assert cloud.first_call.wait(30)
    assert client.post(f"/api/activity/jobs/{run}/cancel").status_code == 200
    cloud.gate.set()
    assert _wait_for(lambda: _status(client, run) == "cancelled")
    time.sleep(0.3)
    assert cloud.calls == 1
