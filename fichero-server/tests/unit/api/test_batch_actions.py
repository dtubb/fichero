"""Unit tests for the BATCH audited-action layer (EPIC #1848 / sweep #2014).

Mirrors ``test_action_registry.py``: every batch mutation is driven through
``registry.invoke`` and we assert (a) the persisted effect, (b) an ActionAudit
row, (c) undo (for undoable ops), (d) param validation + edge/failure cases a
naive impl would get wrong, and (e) the change-stream emit fires with the right
type + ids (emit_change monkeypatched at the SOURCE).

Architecture note: ``BatchManager`` is async + backed by its own DuckDB (the
*app* db in prod). These tests point a fresh BatchManager at a temp duckdb and
swap it in as the module singleton, so the action's ``get_batch_manager()`` and
the test share one store. The ActionAudit still lands in the library ``db``
fixture (the registry's choke point). The SSE streaming ops (execute/resume/
retry) are wrapped as drain-to-completion actions; their generators are stubbed
so we assert the audited wrapper without running a live workflow.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

# Importing the route module registers the batch.* actions via @action.
import fichero_server.api.routes.workflow.batch as batch_routes  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.execution.batch import (
    BatchEvent,
    BatchExecution,
    BatchItem,
    BatchItemStatus,
    BatchManager,
    BatchStatus,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """A BatchManager on a temp duckdb, installed as the module singleton."""
    db_path = str(tmp_path / "batch_actions_test.duckdb")
    mgr = BatchManager(db_path)
    monkeypatch.setattr(batch_routes, "_batch_manager", mgr)
    return mgr


@pytest.fixture
def ctx():
    return ActionContext(actor="ui", library_path="/lib/test.fichero")


@pytest.fixture
def emit_spy(monkeypatch):
    """Spy on emit_change as the registry resolves it (at the source module)."""
    calls = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _make_batch(workflow_id="wf-1", n_items=2):
    return {
        "workflow_id": workflow_id,
        "items": [{"input_text": f"item {i}"} for i in range(n_items)],
    }


# ---------------------------------------------------------------------------
# Registry listing
# ---------------------------------------------------------------------------


class TestBatchActionsRegistered:
    def test_all_batch_actions_present(self):
        names = set(registry.names())
        for verb in (
            "batch.create",
            "batch.delete",
            "batch.restore",
            "batch.execute",
            "batch.pause",
            "batch.resume",
            "batch.cancel",
            "batch.retry",
        ):
            assert verb in names, f"{verb} not registered"

    def test_undoable_flags(self):
        assert registry.get("batch.create").undoable is True
        assert registry.get("batch.delete").undoable is True
        # State transitions / terminal ops are not undoable.
        for verb in ("batch.pause", "batch.cancel", "batch.execute",
                     "batch.resume", "batch.retry", "batch.restore"):
            assert registry.get(verb).undoable is False


# ---------------------------------------------------------------------------
# batch.create
# ---------------------------------------------------------------------------


class TestBatchCreate:
    def test_create_effect_audit_and_emit(self, db, manager, ctx, emit_spy):
        result = registry.invoke(db, "batch.create", _make_batch(n_items=3), ctx)

        # (a) effect: the batch is persisted in the manager store
        batch_id = result.result["batch_id"]
        persisted = _run(manager.get_batch(batch_id))
        assert persisted is not None
        assert persisted.total_items == 3
        assert persisted.workflow_id == "wf-1"

        # (b) ActionAudit row
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "batch.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [batch_id]
        assert audit.before is None
        assert audit.after and audit.after["batch_id"] == batch_id

        # (e) emit fired with the typed event
        assert len(emit_spy) == 1
        _args, kwargs = emit_spy[0]
        assert kwargs["type"] == "batch.created"
        assert kwargs["actor"] == "ui"

    def test_create_rejects_empty_items(self, db, manager, ctx):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            registry.invoke(db, "batch.create", {"workflow_id": "wf-1", "items": []}, ctx)

    def test_create_rejects_missing_workflow_id(self, db, manager, ctx):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            registry.invoke(db, "batch.create", {"items": [{"x": 1}]}, ctx)

    def test_create_then_undo_deletes(self, db, manager, ctx):
        result = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = result.result["batch_id"]
        assert _run(manager.get_batch(batch_id)) is not None

        # Undo: derive the inverse from the audit and invoke it (how the
        # generic /audit/{id}/undo endpoint drives undo).
        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get(audit.action_name)
        inverse = reg.invert(audit.before, audit.after, ctx)
        assert inverse == ("batch.delete", {"batch_id": batch_id})
        registry.invoke(db, inverse[0], inverse[1], ctx)

        assert _run(manager.get_batch(batch_id)) is None


# ---------------------------------------------------------------------------
# batch.delete  (+ batch.restore as its inverse)
# ---------------------------------------------------------------------------


class TestBatchDelete:
    def test_delete_effect_and_audit_snapshot(self, db, manager, ctx, emit_spy):
        created = registry.invoke(db, "batch.create", _make_batch(n_items=2), ctx)
        batch_id = created.result["batch_id"]
        emit_spy.clear()

        result = registry.invoke(db, "batch.delete", {"batch_id": batch_id}, ctx)
        assert result.result["status"] == "deleted"
        assert _run(manager.get_batch(batch_id)) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "batch.delete"
        # before-snapshot carries the full batch (the undo payload)
        assert audit.before and audit.before["batch_id"] == batch_id
        assert len(audit.before["items"]) == 2
        assert audit.after is None

        assert emit_spy and emit_spy[-1][1]["type"] == "batch.deleted"

    def test_delete_missing_raises_404(self, db, manager, ctx):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "batch.delete", {"batch_id": "no-such"}, ctx)
        assert exc.value.status_code == 404

    def test_delete_running_rejected(self, db, manager, ctx):
        from fastapi import HTTPException

        created = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = created.result["batch_id"]
        # Force RUNNING and persist.
        running = _run(manager.get_batch(batch_id))
        running.status = BatchStatus.RUNNING
        _run(manager._save_batch(running))

        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "batch.delete", {"batch_id": batch_id}, ctx)
        assert exc.value.status_code == 400
        # Not deleted.
        assert _run(manager.get_batch(batch_id)) is not None

    def test_delete_then_undo_restores(self, db, manager, ctx):
        created = registry.invoke(db, "batch.create", _make_batch(n_items=2), ctx)
        batch_id = created.result["batch_id"]

        deleted = registry.invoke(db, "batch.delete", {"batch_id": batch_id}, ctx)
        assert _run(manager.get_batch(batch_id)) is None

        audit = db.get(ActionAudit, deleted.audit_id)
        reg = registry.get(audit.action_name)
        inv_name, inv_params = reg.invert(audit.before, audit.after, ctx)
        assert inv_name == "batch.restore"
        registry.invoke(db, inv_name, inv_params, ctx)

        # restored with the same id + item count
        restored = _run(manager.get_batch(batch_id))
        assert restored is not None
        assert restored.total_items == 2
        assert restored.workflow_id == "wf-1"


# ---------------------------------------------------------------------------
# batch.pause
# ---------------------------------------------------------------------------


class TestBatchPause:
    def test_pause_running_batch(self, db, manager, ctx, emit_spy):
        created = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = created.result["batch_id"]
        running = _run(manager.get_batch(batch_id))
        running.status = BatchStatus.RUNNING
        _run(manager._save_batch(running))
        emit_spy.clear()

        result = registry.invoke(db, "batch.pause", {"batch_id": batch_id}, ctx)
        assert result.result["status"] == BatchStatus.PAUSED.value
        assert _run(manager.get_batch(batch_id)).status == BatchStatus.PAUSED

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "batch.pause"
        assert audit.after["status"] == BatchStatus.PAUSED.value
        assert emit_spy and emit_spy[-1][1]["type"] == "batch.paused"

    def test_pause_non_running_raises(self, db, manager, ctx):
        created = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = created.result["batch_id"]  # status PENDING
        with pytest.raises(ValueError):
            registry.invoke(db, "batch.pause", {"batch_id": batch_id}, ctx)


# ---------------------------------------------------------------------------
# batch.cancel
# ---------------------------------------------------------------------------


class TestBatchCancel:
    def test_cancel_pending_batch_marks_items_cancelled(self, db, manager, ctx, emit_spy):
        created = registry.invoke(db, "batch.create", _make_batch(n_items=2), ctx)
        batch_id = created.result["batch_id"]
        emit_spy.clear()

        result = registry.invoke(db, "batch.cancel", {"batch_id": batch_id}, ctx)
        assert result.result["status"] == BatchStatus.CANCELLED.value

        cancelled = _run(manager.get_batch(batch_id))
        assert cancelled.status == BatchStatus.CANCELLED
        assert all(i.status == BatchItemStatus.CANCELLED for i in cancelled.items)

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "batch.cancel"
        assert audit.before["status"] == BatchStatus.PENDING.value
        assert audit.after["status"] == BatchStatus.CANCELLED.value
        assert emit_spy and emit_spy[-1][1]["type"] == "batch.cancelled"

    def test_cancel_terminal_batch_rejected(self, db, manager, ctx):
        created = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = created.result["batch_id"]
        # Force a terminal COMPLETED state.
        done = _run(manager.get_batch(batch_id))
        done.status = BatchStatus.COMPLETED
        _run(manager._save_batch(done))

        with pytest.raises(ValueError):
            registry.invoke(db, "batch.cancel", {"batch_id": batch_id}, ctx)


# ---------------------------------------------------------------------------
# batch.execute / batch.resume  (drain-to-completion; generator stubbed)
# ---------------------------------------------------------------------------


def _stub_stream_to(manager, monkeypatch, attr, final_status):
    """Replace a manager streaming generator with a deterministic stub that
    flips the persisted batch to ``final_status`` and yields one event."""

    async def _stub(batch_id, store):
        b = await manager.get_batch(batch_id)
        b.status = final_status
        b.completed_at = datetime.now()
        await manager._save_batch(b)
        yield BatchEvent(batch_id=batch_id, event_type="batch_completed")

    monkeypatch.setattr(manager, attr, _stub)


class TestBatchExecute:
    def test_execute_drains_and_audits_final_state(
        self, db, manager, ctx, emit_spy, monkeypatch
    ):
        created = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = created.result["batch_id"]
        _stub_stream_to(manager, monkeypatch, "execute_batch", BatchStatus.COMPLETED)
        monkeypatch.setattr(batch_routes, "get_workflow_store", lambda: object())
        emit_spy.clear()

        result = registry.invoke(db, "batch.execute", {"batch_id": batch_id}, ctx)
        assert result.result["status"] == BatchStatus.COMPLETED.value
        assert _run(manager.get_batch(batch_id)).status == BatchStatus.COMPLETED

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "batch.execute"
        assert audit.before["status"] == BatchStatus.PENDING.value
        assert audit.after["status"] == BatchStatus.COMPLETED.value
        assert emit_spy and emit_spy[-1][1]["type"] == "batch.executed"

    def test_execute_missing_batch_raises(self, db, manager, ctx, monkeypatch):
        monkeypatch.setattr(batch_routes, "get_workflow_store", lambda: object())
        with pytest.raises(ValueError):
            registry.invoke(db, "batch.execute", {"batch_id": "no-such"}, ctx)


class TestBatchResume:
    def test_resume_drains_from_paused(self, db, manager, ctx, monkeypatch):
        created = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = created.result["batch_id"]
        paused = _run(manager.get_batch(batch_id))
        paused.status = BatchStatus.PAUSED
        _run(manager._save_batch(paused))

        _stub_stream_to(manager, monkeypatch, "resume_batch", BatchStatus.COMPLETED)
        monkeypatch.setattr(batch_routes, "get_workflow_store", lambda: object())

        result = registry.invoke(db, "batch.resume", {"batch_id": batch_id}, ctx)
        assert result.result["status"] == BatchStatus.COMPLETED.value
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "batch.resume"
        assert audit.before["status"] == BatchStatus.PAUSED.value


# ---------------------------------------------------------------------------
# batch.retry  (+ the extracted reset_failed_items discrete transition)
# ---------------------------------------------------------------------------


class TestResetFailedItems:
    """Real-effect test of the discrete reset the retry action wraps."""

    def _failed_batch(self, manager):
        batch = BatchExecution(
            batch_id="failed-batch",
            workflow_id="wf-1",
            status=BatchStatus.FAILED,
            items=[
                BatchItem(thread_id="t0", item_index=0, inputs={},
                          status=BatchItemStatus.FAILED, error="boom"),
                BatchItem(thread_id="t1", item_index=1, inputs={},
                          status=BatchItemStatus.COMPLETED),
            ],
            created_at=datetime.now(),
        )
        manager._batches[batch.batch_id] = batch
        _run(manager._save_batch(batch))
        return batch

    def test_reset_returns_failed_items_to_pending(self, manager):
        self._failed_batch(manager)
        reset = _run(manager.reset_failed_items("failed-batch"))
        assert reset.status == BatchStatus.PENDING
        statuses = {i.item_index: i.status for i in reset.items}
        assert statuses[0] == BatchItemStatus.PENDING  # was FAILED
        assert statuses[0] != BatchItemStatus.FAILED
        assert reset.items[0].error is None
        # Already-completed item is left untouched.
        assert statuses[1] == BatchItemStatus.COMPLETED

    def test_reset_non_failed_raises(self, manager):
        created = registry.invoke  # noqa: F841
        batch = BatchExecution(
            batch_id="pending-batch",
            workflow_id="wf-1",
            status=BatchStatus.PENDING,
            items=[],
            created_at=datetime.now(),
        )
        manager._batches[batch.batch_id] = batch
        _run(manager._save_batch(batch))
        with pytest.raises(ValueError):
            _run(manager.reset_failed_items("pending-batch"))


class TestBatchRetry:
    def test_retry_resets_then_drains(self, db, manager, ctx, monkeypatch):
        batch = BatchExecution(
            batch_id="retry-batch",
            workflow_id="wf-1",
            status=BatchStatus.FAILED,
            items=[
                BatchItem(thread_id="t0", item_index=0, inputs={},
                          status=BatchItemStatus.FAILED, error="boom"),
            ],
            created_at=datetime.now(),
        )
        manager._batches[batch.batch_id] = batch
        _run(manager._save_batch(batch))

        # Stub only the execute_batch tail; retry_failed_items still runs the
        # REAL reset (extracted) then delegates to execute_batch.
        _stub_stream_to(manager, monkeypatch, "execute_batch", BatchStatus.COMPLETED)
        monkeypatch.setattr(batch_routes, "get_workflow_store", lambda: object())

        result = registry.invoke(db, "batch.retry", {"batch_id": "retry-batch"}, ctx)
        assert result.result["status"] == BatchStatus.COMPLETED.value

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "batch.retry"
        assert audit.before["status"] == BatchStatus.FAILED.value

    def test_retry_non_failed_raises(self, db, manager, ctx, monkeypatch):
        monkeypatch.setattr(batch_routes, "get_workflow_store", lambda: object())
        created = registry.invoke(db, "batch.create", _make_batch(), ctx)
        batch_id = created.result["batch_id"]  # PENDING
        with pytest.raises(ValueError):
            registry.invoke(db, "batch.retry", {"batch_id": batch_id}, ctx)
