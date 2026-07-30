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
