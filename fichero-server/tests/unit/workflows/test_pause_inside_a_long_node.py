"""Pause must land inside a long node, and dead runs must settle (#4402).

Two admitted gaps from the reopened issue, both engine-side:

1. Pause (unlike Stop, fixed earlier in #4402) was consulted only between
   LangGraph events — a pause during a 200-page transcribe waited for the
   whole node. The per-item progress callback is the one boundary shared by
   every per-item tool; pause now rides it exactly the way cancel does.

2. A run row recorded as ``running`` whose worker died with a previous engine
   process has no registry entry. Cancel used to decline ("a live worker will
   settle itself") and return a polite 200 — so the row could never be
   stopped, ever, and the UI said nothing. A row that can never settle is
   worse than an honest failure: cancel now settles it, and pause says
   honestly that a dead run cannot pause.

Nothing here skips or calls a model.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fichero_server.execution.cancellation import (
    WorkflowCancelled,
    WorkflowPaused,
    cancellation_requested,
    clear_cancellation,
    clear_pause,
    pause_requested,
    request_cancellation,
    request_pause,
)


@pytest.fixture
def run_id():
    rid = "pause-inside-node-run"
    clear_pause(rid)
    clear_cancellation(rid)
    yield rid
    clear_pause(rid)
    clear_cancellation(rid)


class TestThePausePrimitive:
    def test_set_check_clear(self, run_id):
        assert not pause_requested(run_id)
        request_pause(run_id)
        assert pause_requested(run_id)
        clear_pause(run_id)
        assert not pause_requested(run_id)

    def test_the_flag_is_visible_across_threads(self, run_id):
        """The run executes on a worker thread — if this fails, Pause cannot
        work at all, same as the #4402 cancel finding."""
        import threading

        seen: list[bool] = []
        request_pause(run_id)
        thread = threading.Thread(target=lambda: seen.append(pause_requested(run_id)))
        thread.start()
        thread.join()
        assert seen == [True]

    def test_an_unknown_or_empty_run_is_not_paused(self):
        assert pause_requested("never-started") is False
        assert pause_requested("") is False
        assert pause_requested(None) is False

    def test_pause_and_cancel_are_independent_signals(self, run_id):
        request_pause(run_id)
        assert pause_requested(run_id)
        assert not cancellation_requested(run_id)


class TestTheProgressBoundaryChecksPause:
    """The seam: the builder's per-node progress callback (#4402)."""

    @staticmethod
    def _callback(run_id: str, emitted: list):
        """Rebuild the builder's `emit_tool_progress` contract exactly —
        cancel checked first (a run both paused and stopped is stopped),
        then pause."""

        async def emit_tool_progress(event_type: str, data: dict) -> None:
            if cancellation_requested(run_id):
                raise WorkflowCancelled(run_id)
            if pause_requested(run_id):
                raise WorkflowPaused(run_id)
            emitted.append((event_type, data))

        return emit_tool_progress

    def test_a_per_item_loop_pauses_at_its_next_item(self, run_id):
        """The reported behaviour: Pause is pressed and the loop keeps going
        to the end of the node. It must stop at the next item boundary."""
        emitted: list = []
        callback = self._callback(run_id, emitted)
        processed: list[int] = []

        async def a_long_node():
            from fichero_server.workflows.tools.progress import emit_progress_event

            for index in range(200):
                if index == 3:
                    request_pause(run_id)  # user presses Pause
                await emit_progress_event(
                    callback, "file_start", "", f"item-{index}", index, 200
                )
                processed.append(index)

        with pytest.raises(WorkflowPaused):
            asyncio.run(a_long_node())

        assert processed == [0, 1, 2], (
            f"expected to pause at the item after Pause, processed {processed}"
        )

    def test_cancel_wins_when_both_are_requested(self, run_id):
        emitted: list = []
        callback = self._callback(run_id, emitted)
        request_pause(run_id)
        request_cancellation(run_id)
        with pytest.raises(WorkflowCancelled):
            asyncio.run(callback("file_start", {}))

    def test_the_exception_names_the_run(self, run_id):
        request_pause(run_id)
        with pytest.raises(WorkflowPaused) as caught:
            asyncio.run(self._callback(run_id, [])("file_start", {}))
        assert caught.value.run_id == run_id

    def test_the_real_builder_checks_pause_at_the_boundary(self):
        """The rebuilt contract above must match the shipped callback: the
        builder's progress boundary consults pause and raises WorkflowPaused,
        and re-raises it ahead of the generic failure handler."""
        import inspect

        from fichero_server.workflows import builder

        source = inspect.getsource(builder)
        assert "raise WorkflowPaused(run_id)" in source, (
            "the per-item progress boundary does not check pause — a pause "
            "during a long node waits for the whole node again (#4402)"
        )
        paused_at = source.index("except WorkflowPaused:")
        generic_at = source.index("except Exception as e:", paused_at)
        assert paused_at < generic_at, (
            "WorkflowPaused must be handled before the generic node-error "
            "branch, or a user's Pause is reported as a failed run"
        )

    def test_the_runner_settles_a_mid_node_pause_as_paused(self):
        """Both pause paths — between-events and raised-from-inside-a-node —
        must go through the one terminal routine, mirroring
        `_finish_as_cancelled`, so they cannot disagree."""
        import inspect

        from fichero_server.execution import runner

        source = inspect.getsource(runner)
        assert "except WorkflowPaused:" in source, (
            "a pause raised from inside a node has no handler — it would be "
            "recorded as a failure"
        )
        assert source.count("async def _finish_as_paused") == 1
        assert source.count("await _finish_as_paused()") == 2, (
            "expected exactly two callers: the between-events check and the "
            "raised-from-inside-a-node handler"
        )
        # A paused run is NOT terminal — it must not finalize documents.
        terminal = source[source.index("async def _finish_as_paused") :][:2400]
        assert "_finalize_documents" not in terminal, (
            "a paused run settled its documents as if it had ended — it must "
            "stay resumable"
        )
        assert "clear_pause(thread_id)" in terminal, (
            "the pause signal must be consumed on settle, or the next resume "
            "instantly re-pauses"
        )


def _tracker_with_run(status: str | None):
    """An activity tracker whose store returns a run row with `status`."""
    tracker = MagicMock()
    run = (
        SimpleNamespace(
            status=status,
            workflow_id="wf-1",
            workflow_name="Transcribe",
        )
        if status is not None
        else None
    )
    tracker.store.get_workflow_run = AsyncMock(return_value=run)
    tracker.store.update_workflow_run = AsyncMock()
    return tracker


class TestDeadRunningRowsSettle:
    """#4402 mechanism 1: the engine restarted, a `running` row survived with
    no registry entry, and Stop/Pause returned polite no-ops forever."""

    @pytest.mark.asyncio
    async def test_cancel_settles_a_running_row_with_no_worker(self, tmp_path):
        from fichero_server.api.routes.workflow_execution import threads

        tracker = _tracker_with_run("running")
        db = MagicMock()
        # A real path: the settle path's best-effort document finalize opens a
        # checkpointer at db.path, and a MagicMock path literally creates a
        # `MagicMock/` directory in the CWD.
        db.path = tmp_path / "fichero.duckdb"
        with patch.object(threads, "get_activity_tracker", return_value=tracker), \
             patch(
                 "fichero_server.execution.runner._get_workflow_state",
                 return_value=None,
             ):
            result = await threads.cancel_workflow("dead-thread", db=db)

        assert result.status == "cancelled", (
            "a running row with no live worker got a polite "
            f"'{result.status}' — the row can then never settle (#4402)"
        )
        assert "no live worker" in result.message
        tracker.store.update_workflow_run.assert_awaited()
        settle = tracker.store.update_workflow_run.await_args.kwargs
        assert settle["thread_id"] == "dead-thread"
        assert settle["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_of_a_terminal_row_is_still_already_terminal(self):
        from fichero_server.api.routes.workflow_execution import threads

        tracker = _tracker_with_run("completed")
        with patch.object(threads, "get_activity_tracker", return_value=tracker), \
             patch(
                 "fichero_server.execution.runner._get_workflow_state",
                 return_value=None,
             ):
            result = await threads.cancel_workflow("done-thread", db=MagicMock())

        assert result.status == "already_terminal"
        tracker.store.update_workflow_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pause_of_a_dead_running_row_says_so(self):
        """Pause cannot land on a dead run — the response must say why, not
        pretend the request might work."""
        from fichero_server.api.routes.workflow_execution import threads

        tracker = _tracker_with_run("running")
        with patch.object(threads, "get_activity_tracker", return_value=tracker), \
             patch(
                 "fichero_server.execution.runner._get_workflow_state",
                 return_value=None,
             ):
            result = await threads.pause_workflow("dead-thread", db=MagicMock())

        assert result.status == "not_running"
        assert "no live worker" in result.message
        assert "cannot be paused" in result.message

    @pytest.mark.asyncio
    async def test_pause_of_a_terminal_row_is_already_terminal(self):
        from fichero_server.api.routes.workflow_execution import threads

        tracker = _tracker_with_run("completed")
        with patch.object(threads, "get_activity_tracker", return_value=tracker), \
             patch(
                 "fichero_server.execution.runner._get_workflow_state",
                 return_value=None,
             ):
            result = await threads.pause_workflow("done-thread", db=MagicMock())

        assert result.status == "already_terminal"

    @pytest.mark.asyncio
    async def test_pause_of_a_live_run_sets_both_signals(self):
        """The endpoint must set the shared event too — the flag alone never
        reaches the per-item boundary inside a long node."""
        from fichero_server.api.routes.workflow_execution import threads

        state = {"status": "running"}
        clear_pause("live-thread")
        try:
            with patch(
                "fichero_server.execution.runner._get_workflow_state",
                return_value=state,
            ):
                result = await threads.pause_workflow("live-thread", db=MagicMock())

            assert result.status == "pause_requested"
            assert state["pause_requested"] is True
            assert pause_requested("live-thread"), (
                "the shared pause event was not set — a pause during a long "
                "node still waits for the whole node (#4402)"
            )
        finally:
            clear_pause("live-thread")
