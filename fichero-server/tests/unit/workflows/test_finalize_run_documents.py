"""#4315: cancelled, failed, and resumed runs must never leave documents at
``Status.processing`` forever.

``complete_run_documents`` ran only on the success path; the cancel return and
both except blocks skipped it, so any non-success outcome stranded documents
with a permanent spinner no later run repaired. ``finalize_run_documents``
now owns EVERY terminal boundary: success → completed, failure/cancel →
processing reverts to pending, always with a provenance entry.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.db import Database
from fichero_server.models import Document, Status
from fichero_server.workflows.completion import (
    complete_run_documents,
    finalize_run_documents,
)


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


def _processing_doc(db, name="doc.pdf"):
    doc = Document(name=name, path=f"/tmp/{name}", status=Status.processing)
    db.save(doc)
    return doc


class TestFinalizeRunDocuments:
    def test_cancelled_reverts_processing_to_pending_with_provenance(self, temp_db):
        doc = _processing_doc(temp_db)
        updated = finalize_run_documents(
            temp_db,
            {doc.id},
            "cancelled",
            workflow_run={
                "thread_id": "t-1",
                "workflow_id": "wf-1",
                "workflow_name": "Transcribe",
                "result": {"status": "cancelled"},
            },
        )
        assert updated == 1
        after = temp_db.get(Document, doc.id)
        assert after.status == Status.pending, "no permanent spinner on cancel"
        assert after.workflow_runs
        assert after.workflow_runs[-1]["result"]["status"] == "cancelled"

    def test_failed_reverts_processing_to_pending(self, temp_db):
        doc = _processing_doc(temp_db)
        finalize_run_documents(temp_db, {doc.id}, "failed")
        assert temp_db.get(Document, doc.id).status == Status.pending

    def test_failed_reverts_processing_page_children(self, temp_db):
        parent = _processing_doc(temp_db, "parent.pdf")
        child = Document(
            name="page-1",
            path=None,
            parent_id=parent.id,
            status=Status.processing,
        )
        temp_db.save(child)
        finalize_run_documents(temp_db, {parent.id}, "failed")
        assert temp_db.get(Document, parent.id).status == Status.pending
        assert temp_db.get(Document, child.id).status == Status.pending

    def test_failed_does_not_promote_pending_parent(self, temp_db):
        # The success-only pending→completed parent promotion (#2219) must NOT
        # fire on failure — a pending doc stays pending, it does not complete.
        doc = Document(name="parent.pdf", path="/tmp/parent.pdf", status=Status.pending)
        temp_db.save(doc)
        finalize_run_documents(temp_db, {doc.id}, "failed")
        assert temp_db.get(Document, doc.id).status == Status.pending

    def test_completed_matches_legacy_complete_run_documents(self, temp_db):
        doc = _processing_doc(temp_db)
        updated = complete_run_documents(temp_db, {doc.id})
        assert updated == 1
        assert temp_db.get(Document, doc.id).status == Status.completed

    def test_unknown_final_status_raises(self, temp_db):
        with pytest.raises(ValueError, match="unknown final_status"):
            finalize_run_documents(temp_db, {"x"}, "paused")

    def test_untouched_completed_docs_keep_status_on_failure(self, temp_db):
        doc = Document(name="done.pdf", path="/tmp/done.pdf", status=Status.completed)
        temp_db.save(doc)
        finalize_run_documents(temp_db, {doc.id}, "cancelled")
        assert temp_db.get(Document, doc.id).status == Status.completed


# ---------------------------------------------------------------------------
# segment.overlay.refreshes-when-segmentation-finishes: a run's saved
# artifacts must broadcast on the change stream, naming the artifact and its
# document, even when settling the run's documents produces no status
# transition. (#4890.)
# ---------------------------------------------------------------------------


class TestArtifactChangeEmission:
    def test_segmentation_run_emits_an_event_naming_the_artifact_and_document(
        self, temp_db, monkeypatch
    ):
        from fichero_server.api import change_stream
        from fichero_server.models import Artifact

        doc = _processing_doc(temp_db)
        art = Artifact(document_id=doc.id, artifact_type="regions", content="")
        temp_db.save(art)

        captured = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda library_path, event: captured.append(event),
        )

        complete_run_documents(temp_db, {doc.id}, artifact_ids={art.id})

        artifact_events = [e for e in captured if e.type == "artifact.updated"]
        assert len(artifact_events) == 1
        assert artifact_events[0].artifact_ids == [art.id]
        assert artifact_events[0].document_ids == [doc.id]

    def test_a_run_that_changes_no_document_status_still_emits(
        self, temp_db, monkeypatch
    ):
        """The exact scenario named in the ruling: re-running segmentation on
        an already-`completed` document settles no status transition, so the
        pre-existing `document.updated` broadcast stays silent -- the new
        artifact-carrying emission must fire anyway."""
        from fichero_server.api import change_stream
        from fichero_server.models import Artifact

        doc = Document(name="done.pdf", path="/tmp/done.pdf", status=Status.completed)
        temp_db.save(doc)
        art = Artifact(document_id=doc.id, artifact_type="regions", content="")
        temp_db.save(art)

        captured = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda library_path, event: captured.append(event),
        )

        updated = complete_run_documents(temp_db, {doc.id}, artifact_ids={art.id})

        assert updated == 0  # no status transition -- the old path's own gate
        assert [e for e in captured if e.type == "document.updated"] == []
        artifact_events = [e for e in captured if e.type == "artifact.updated"]
        assert len(artifact_events) == 1
        assert artifact_events[0].artifact_ids == [art.id]

    def test_no_event_is_emitted_twice_for_one_artifact(self, temp_db, monkeypatch):
        from fichero_server.api import change_stream
        from fichero_server.models import Artifact

        doc = _processing_doc(temp_db)
        art = Artifact(document_id=doc.id, artifact_type="regions", content="")
        temp_db.save(art)

        captured = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda library_path, event: captured.append(event),
        )

        complete_run_documents(temp_db, {doc.id}, artifact_ids={art.id})

        artifact_events = [e for e in captured if e.type == "artifact.updated"]
        assert len(artifact_events) == 1, "one event for the RUN, not one per artifact"
        assert artifact_events[0].artifact_ids.count(art.id) == 1

    def test_no_artifacts_means_no_artifact_event(self, temp_db, monkeypatch):
        from fichero_server.api import change_stream

        doc = _processing_doc(temp_db)
        captured = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda library_path, event: captured.append(event),
        )

        complete_run_documents(temp_db, {doc.id})

        assert [e for e in captured if e.type == "artifact.updated"] == []


class TestCollectCreatedArtifactIds:
    def test_reads_a_node_outputs_own_artifacts_key(self):
        from fichero_server.workflows.completion import collect_created_artifact_ids

        final_state = {"outputs": {"detect_regions_node": {"artifacts": ["a1", "a2"]}}}
        assert collect_created_artifact_ids(final_state) == {"a1", "a2"}

    def test_reads_the_top_level_fallback(self):
        """The graph's state schema can merge a node's return dict onto the
        top level (the same shape `process_vision` itself returns, #4890,
        `vision_base.py:5301`)."""
        from fichero_server.workflows.completion import collect_created_artifact_ids

        final_state = {"artifacts": ["a3"]}
        assert collect_created_artifact_ids(final_state) == {"a3"}

    def test_non_dict_state_is_empty_not_an_error(self):
        from fichero_server.workflows.completion import collect_created_artifact_ids

        assert collect_created_artifact_ids(None) == set()
        assert collect_created_artifact_ids([1, 2, 3]) == set()


# ---------------------------------------------------------------------------
# Runner terminal paths: cancel and failure must call the finalize boundary.
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


def _wire_runner(monkeypatch, run_app, checkpointer, temp_db):
    from fichero_server.execution import runner

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
        runner, "create_compiled_app", lambda *_a, **_k: (run_app, checkpointer)
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.get_database",
        lambda _library_path: temp_db,
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.close_current_thread", lambda: None
    )
    return runner


def _checkpointer_with_doc(doc_id):
    class _Ckpt:
        async def aget_tuple(self, _config):
            return SimpleNamespace(
                checkpoint={
                    "id": "ckpt-1",
                    "channel_values": {
                        "outputs": {
                            "src": {"documents": [{"id": doc_id}]}
                        }
                    },
                }
            )

    return _Ckpt()


@pytest.mark.asyncio
async def test_cancelled_run_reverts_documents(monkeypatch, temp_db):
    """Cancel mid-run: touched docs return to a non-spinner state."""
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.models import Workflow

    doc = _processing_doc(temp_db)

    class _App:
        async def astream_events(self, *_a, **_k):
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            yield {"event": "on_chain_end", "name": "node-1", "data": {"output": {}}}

    runner = _wire_runner(
        monkeypatch, _App(), _checkpointer_with_doc(doc.id), temp_db
    )
    thread_id = "thread-cancel-final"
    events = runner.WorkflowEventHub()
    state = {"events": events, "cancel_requested": True}
    runner._set_workflow_state(thread_id, state)

    workflow = Workflow(
        id="wf-c",
        name="Cancelme",
        format="nodes",
        nodes=[{"id": "node-1", "tool": "transcribe", "label": "node-1"}],
        edges=[],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-c", inputs={}),
        temp_db,
    )

    assert state["status"] == "cancelled"
    after = temp_db.get(Document, doc.id)
    assert after.status == Status.pending
    assert after.workflow_runs[-1]["result"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_failed_run_reverts_documents(monkeypatch, temp_db):
    """Failed run: touched docs return to a non-spinner state."""
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.models import Workflow

    doc = _processing_doc(temp_db)

    class _App:
        async def astream_events(self, *_a, **_k):
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            raise RuntimeError("provider exploded")

    runner = _wire_runner(
        monkeypatch, _App(), _checkpointer_with_doc(doc.id), temp_db
    )
    thread_id = "thread-fail-final"
    events = runner.WorkflowEventHub()
    state = {"events": events}
    runner._set_workflow_state(thread_id, state)

    workflow = Workflow(
        id="wf-f",
        name="Failme",
        format="nodes",
        nodes=[{"id": "node-1", "tool": "transcribe", "label": "node-1"}],
        edges=[],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-f", inputs={}),
        temp_db,
    )

    assert state["status"] == "failed"
    after = temp_db.get(Document, doc.id)
    assert after.status == Status.pending
    assert after.workflow_runs[-1]["result"]["status"] == "failed"
