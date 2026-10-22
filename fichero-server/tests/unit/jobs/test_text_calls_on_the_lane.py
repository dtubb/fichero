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
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute, _status, _tree, _wait_for, make_page_sets, no_embedding_model)

pytestmark = pytest.mark.usefixtures("lane_cloud_yes")


@pytest.fixture
def lane_cloud_yes(project_says_yes, monkeypatch):
    """These tests are about the LANE, with stub cloud models: the test project says yes to cloud models and the stub models carry a
    listed price, so the one egress gate and the spending cap (#5368) let the call through. Never use it in a cap or egress test."""
    from fichero_server.llm import usage

    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5})


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
def page_sets(db, tmp_path):
    return make_page_sets(db, tmp_path, text=True)


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


def test_activity_run_lane_cap_per_mac__text_calls_of_three_runs_share_one_cap(client, workflow, page_sets, cloud, monkeypatch):
    """Behaviour `activity.run.lane-cap-per-mac`: "the cap on concurrent model calls is one per Mac,
    shared by every run." Three entity runs (each asks about its letters one after another), with
    the network lane two wide, never make more than two calls at once."""
    monkeypatch.setitem(jobs.LANES, "network", 2)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.seconds = 0.3
    runs = [_execute(client, workflow, page_sets()) for _ in range(3)]
    assert _wait_for(lambda: all(_status(client, run) == "completed" for run in runs))
    assert cloud.calls == 9
    assert cloud.peak <= 2


def test_activity_pause_per_job__stopping_the_run_reaches_its_next_text_calls(client, workflow, pages, cloud, monkeypatch):
    """Behaviour `activity.pause.per-job` ("Cancel on any row, applying to its children"): with the
    first call held, Stop on the run row ends the run, and none of its later calls reaches the
    model. The entity reader now asks pages together (`runtime.cloud-extractors.pages-together`, 10 in flight for a hosted
    model, so all three letters would be in flight before Stop); the width is one here, which is the case this pins: Stop
    is asked before every new call."""
    monkeypatch.setenv("FICHERO_EXTRACT_MAX_IN_FLIGHT", "1")
    cloud.gate = threading.Event()
    run = _execute(client, workflow, pages)
    assert cloud.first_call.wait(30)
    assert client.post(f"/api/activity/jobs/{run}/cancel").status_code == 200
    cloud.gate.set()
    assert _wait_for(lambda: _status(client, run) == "cancelled")
    time.sleep(0.3)
    assert cloud.calls == 1


def test_activity_pause_per_job__no_new_text_call_starts_after_stop_at_the_default_width(monkeypatch):
    """`runtime.cloud-extractors.pages-together` (## 941): 30 letters at the default width (10 for a hosted model). Ten calls are in
    flight; the run is stopped; as they land the loop must not ask for the next letter: no cloud page leaves this Mac after
    Stop, and the step ends with the Stop (not as a part-done answer). The extractors take their Stop from the run
    (`_together.ahead_of_run`); the run's stop is faked here, and the loop is the real one."""
    import asyncio

    from fichero_server.execution.cancellation import WorkflowCancelled
    from fichero_server.workflows.tools import _together

    stopped = [False]
    monkeypatch.setattr(_together, "this_run_stopped", lambda: WorkflowCancelled("run") if stopped[0] else None)
    started: list[int] = []

    async def start(item: int) -> int:
        started.append(item)
        await asyncio.sleep(0)
        return item

    async def consume() -> list[int]:
        seen: list[int] = []
        async for item, _answer in _together.ahead_of_run(range(30), start, _together.CLOUD_WIDTH):
            seen.append(item)
            stopped[0] = True  # the person presses Stop while the first ten are in flight
        return seen

    with pytest.raises(WorkflowCancelled):
        asyncio.run(consume())
    assert len(started) == _together.CLOUD_WIDTH, f"{len(started)} calls started; only the window of ten may"


def test_both_extractors_take_their_stop_from_the_run():
    """The loop of `extract_entities_only` and `extract_svo_only` is `ahead_of_run`, never a bare `ahead` with no stop."""
    import inspect

    from fichero_server.workflows.tools import extract_entities_only, extract_svo_only

    for module in (extract_entities_only, extract_svo_only):
        source = inspect.getsource(module)
        assert "ahead_of_run(" in source and " ahead(" not in source, module.__name__
