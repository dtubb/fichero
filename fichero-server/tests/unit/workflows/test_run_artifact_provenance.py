"""#4313: workflow artifacts must carry their run and step on the live path.

``Artifact.run_id``/``step_name`` existed but the live ``/execute`` path never
populated them — ``_save_artifact_sync`` wrote ``run_id=task_id`` while
``task_id`` was never placed into state, so ``GET /threads/{id}/run`` returned
``run_artifacts == []`` for every run. These tests pin:

- ``_save_artifact_sync`` writes run_id + step_name + workflow_id + a per-run
  monotonic sequence (node identity via workflows.node_context).
- The sequence counter seeds from the DB so a resumed run keeps numbering.
- The background runner puts the thread_id into state as ``task_id`` so a
  stubbed run that saves artifacts ends with a non-empty ``run.run_artifacts``.
- ``GET /api/artifacts`` filters by run_id/step_name DB-side.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fichero_server.models import Artifact, Document
from fichero_server.workflows import node_context


@pytest.fixture
def temp_db():
    from fichero_server.db import Database

    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "fichero.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


@pytest.fixture(autouse=True)
def _fresh_sequences():
    node_context._run_sequences.clear()
    yield
    node_context._run_sequences.clear()


def _tool_config():
    from fichero_server.workflows.tools.llm_base import LLMToolConfig

    return LLMToolConfig(
        artifact_type="transcription",
        update_page_content=False,
        trigger_embedding=False,
    )


def _llm_config():
    from fichero_server.llm import LLMConfig

    return LLMConfig(provider="test", model="test-model")


def _save(temp_db, doc, task_id, content="hola"):
    from fichero_server.workflows.tools.llm_base import _save_artifact_sync

    with patch(
        "fichero_server.db.db_manager.get_database", return_value=temp_db
    ):
        return _save_artifact_sync(
            None,
            doc.id,
            None,
            content,
            None,
            str(temp_db.path.parent),
            _llm_config(),
            task_id,
            _tool_config(),
            None,
            None,
            None,
        )


class TestSaveArtifactProvenance:
    def test_populates_run_step_workflow_and_sequence(self, temp_db):
        doc = Document(name="page.png", path="/tmp/page.png")
        temp_db.save(doc)

        node_context.set_current_node("node-1", "Transcribe", "wf-1")
        first = _save(temp_db, doc, "thread-abc")
        second = _save(temp_db, doc, "thread-abc")

        a1 = temp_db.get(Artifact, first)
        a2 = temp_db.get(Artifact, second)
        assert a1.run_id == "thread-abc"
        assert a1.step_name == "node-1"
        assert a1.workflow_id == "wf-1"
        assert (a1.sequence, a2.sequence) == (1, 2)

    def test_sequence_seeds_from_db_for_resumed_run(self, temp_db):
        doc = Document(name="page.png", path="/tmp/page.png")
        temp_db.save(doc)
        temp_db.save(
            Artifact(
                document_id=doc.id,
                artifact_type="transcription",
                run_id="thread-resume",
                sequence=5,
            )
        )

        node_context.set_current_node("node-2", "Clean", "wf-1")
        saved = _save(temp_db, doc, "thread-resume")
        assert temp_db.get(Artifact, saved).sequence == 6

    def test_no_task_id_leaves_sequence_null(self, temp_db):
        doc = Document(name="page.png", path="/tmp/page.png")
        temp_db.save(doc)
        node_context.set_current_node("node-1", "Transcribe", "wf-1")
        saved = _save(temp_db, doc, None)
        artifact = temp_db.get(Artifact, saved)
        assert artifact.run_id is None
        assert artifact.sequence is None


class TestArtifactRouteFilters:
    def test_list_all_artifacts_filters_by_run_and_step(self, temp_db):
        import asyncio

        from fichero_server.api.routes.document.artifacts import list_all_artifacts

        doc = Document(name="page.png", path="/tmp/page.png")
        temp_db.save(doc)
        temp_db.save(
            Artifact(
                document_id=doc.id,
                artifact_type="transcription",
                run_id="thread-1",
                step_name="node-a",
            )
        )
        temp_db.save(
            Artifact(
                document_id=doc.id,
                artifact_type="transcription",
                run_id="thread-2",
                step_name="node-b",
            )
        )

        by_run = asyncio.run(
            list_all_artifacts(
                artifact_type=None,
                run_id="thread-1",
                step_name=None,
                limit=100,
                offset=0,
                db=temp_db,
            )
        )
        assert by_run.count == 1
        assert by_run.items[0].run_id == "thread-1"

        by_step = asyncio.run(
            list_all_artifacts(
                artifact_type=None,
                run_id=None,
                step_name="node-b",
                limit=100,
                offset=0,
                db=temp_db,
            )
        )
        assert by_step.count == 1
        assert by_step.items[0].step_name == "node-b"


# ---------------------------------------------------------------------------
# Regression: a stubbed background run that saves artifacts must yield a
# non-empty run.run_artifacts (the review's F1 acceptance).
# ---------------------------------------------------------------------------


class _FakeActivityStore:
    async def save_workflow_run(self, **_kwargs):
        return None

    async def update_workflow_run(self, **_kwargs):
        return None


class _FakeActivityTracker:
    def __init__(self):
        self.store = _FakeActivityStore()

    def __getattr__(self, _name):
        return lambda **_kwargs: None


class _FakeCheckpointer:
    async def aget_tuple(self, _config):
        return SimpleNamespace(checkpoint={"id": "ckpt-1", "channel_values": {}})


@pytest.mark.asyncio
async def test_stubbed_run_produces_linked_run_artifacts(monkeypatch, temp_db):
    """The runner puts thread_id into state as task_id; a tool that saves an
    artifact with that task_id makes run_artifacts non-empty for the thread."""
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.api.routes.workflow_execution.threads import (
        WorkflowPlannedStepResponse,
        _flatten_run_artifacts,
        _run_step_records,
    )
    from fichero_server.execution import runner
    from fichero_server.models import Workflow

    thread_id = "thread-provenance"
    doc = Document(name="page.png", path="/tmp/page.png")
    temp_db.save(doc)

    class _FakeRunApp:
        """Fake compiled app whose single node saves an artifact the way a
        real tool does: run_id from state's task_id."""

        def __init__(self, state_capture):
            self._state_capture = state_capture

        async def astream_events(self, initial_state, *_args, **_kwargs):
            self._state_capture.update(initial_state)
            node_context.set_current_node("node-1", "Transcribe", "wf-prov")
            _save(temp_db, doc, initial_state.get("task_id"))
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            yield {
                "event": "on_chain_end",
                "name": "node-1",
                "data": {"output": {}},
            }

    captured_state: dict = {}
    events = runner.WorkflowEventHub()
    runner._set_workflow_state(thread_id, {"events": events})
    monkeypatch.setattr(
        runner, "get_activity_tracker", lambda _p: _FakeActivityTracker()
    )
    monkeypatch.setattr(
        runner,
        "build_graph",
        lambda *_a, **_k: SimpleNamespace(
            get_graph=lambda: SimpleNamespace(draw_mermaid=lambda: "graph TD")
        ),
    )
    monkeypatch.setattr(
        runner,
        "create_compiled_app",
        lambda *_a, **_k: (_FakeRunApp(captured_state), _FakeCheckpointer()),
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.get_database",
        lambda _library_path: temp_db,
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.close_current_thread",
        lambda: None,
    )

    workflow = Workflow(
        id="wf-prov",
        name="Provenance",
        format="nodes",
        nodes=[{"id": "node-1", "tool": "transcribe", "label": "node-1"}],
        edges=[],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-prov", inputs={}),
        temp_db,
    )

    assert captured_state.get("task_id") == thread_id, (
        "the live runner must put the run's thread_id into state as task_id"
    )
    run = SimpleNamespace(progress_timeline={"steps": [], "nodes": {}})
    step_records = _run_step_records(
        temp_db,
        thread_id,
        run=run,
        planned_steps=[
            WorkflowPlannedStepResponse(
                node_id="node-1", node_name="Transcribe", tool="transcribe"
            )
        ],
        node_name_map={"node-1": "Transcribe"},
    )
    rows = _flatten_run_artifacts(step_records)
    assert rows, "run_artifacts must be non-empty for a run that saved artifacts"
    assert rows[0].run_id == thread_id
    assert rows[0].step_name == "node-1"
    assert rows[0].node_name == "Transcribe"
    assert rows[0].sequence == 1
