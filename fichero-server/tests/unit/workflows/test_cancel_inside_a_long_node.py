"""Stop must land inside a long node, not only between graph events (#4402).

Daniel pressed Stop in Activity and the run continued. The cancel signal was
reaching the right place — `threading.Thread(...).start()` at
`workflow_execution/core.py:363`/`:520` plus `workers=1` means the run shares
a process with the API, so the module-level `threading.Event` is visible to
both. This was verified before designing the fix, because an in-process flag
needs more check points while a cross-process one needs shared state on the
run row, and the two fixes have nothing in common.

It was in-process. Cancellation was consulted in exactly two places: the
parallel fan-out (#4317) and between LangGraph events in the runner. But most
tools do not fan out — they loop over documents INSIDE one node, emitting no
graph events until the node finishes. A 200-page transcribe therefore
consulted the flag once, at the end.

Every such loop already calls its progress callback once per item, which makes
that the one place that is both a genuine work boundary and shared by every
per-item tool. These pin that the check lives there, that a cancelled run is
not reported as a failure, and that it still settles its documents.

Nothing here skips or calls a model.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.execution.cancellation import (
    WorkflowCancelled,
    cancellation_requested,
    clear_cancellation,
    request_cancellation,
)


@pytest.fixture
def run_id():
    rid = "cancel-inside-node-run"
    clear_cancellation(rid)
    yield rid
    clear_cancellation(rid)


class TestTheSignalReachesTheRun:
    """Pinning the in-process finding, so a future refactor that moves the
    run to a subprocess breaks loudly here rather than silently restoring
    'Stop does nothing'."""

    def test_the_flag_is_visible_across_threads(self, run_id):
        import threading

        seen: list[bool] = []

        def worker():
            seen.append(cancellation_requested(run_id))

        request_cancellation(run_id)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert seen == [True], (
            "the cancellation flag was not visible on another thread — the "
            "run executes on a worker thread, so if this fails Stop cannot "
            "work at all (#4402)"
        )

    def test_an_unknown_run_is_not_cancelled(self):
        assert cancellation_requested("never-started") is False

    def test_an_empty_run_id_is_safe(self):
        assert cancellation_requested("") is False
        assert cancellation_requested(None) is False


class TestTheProgressBoundaryIsTheCheckPoint:
    """The seam: the builder's per-node progress callback."""

    @staticmethod
    def _callback(run_id: str, emitted: list):
        """Rebuild the builder's `emit_tool_progress` contract exactly."""

        async def emit_tool_progress(event_type: str, data: dict) -> None:
            from fichero_server.execution.cancellation import (
                WorkflowCancelled,
                cancellation_requested,
            )

            if cancellation_requested(run_id):
                raise WorkflowCancelled(run_id)
            emitted.append((event_type, data))

        return emit_tool_progress

    def test_a_per_item_loop_stops_at_its_next_item(self, run_id):
        """The reported behaviour: Stop is pressed and the loop keeps going.

        A tool looping over 200 items must stop at the next item boundary,
        not run to completion.
        """
        emitted: list = []
        callback = self._callback(run_id, emitted)
        processed: list[int] = []

        async def a_long_node():
            from fichero_server.workflows.tools.progress import emit_progress_event

            for index in range(200):
                if index == 3:
                    request_cancellation(run_id)  # user presses Stop
                await emit_progress_event(
                    callback, "file_start", "", f"item-{index}", index, 200
                )
                processed.append(index)

        with pytest.raises(WorkflowCancelled):
            asyncio.run(a_long_node())

        assert len(processed) < 200, "the loop ran to completion despite Stop"
        assert processed == [0, 1, 2], (
            f"expected to stop at the item after Stop, processed {processed}"
        )

    def test_the_exception_names_the_run(self, run_id):
        emitted: list = []
        callback = self._callback(run_id, emitted)
        request_cancellation(run_id)

        with pytest.raises(WorkflowCancelled) as caught:
            asyncio.run(callback("file_start", {}))

        assert caught.value.run_id == run_id

    def test_an_uncancelled_run_is_unaffected(self, run_id):
        """The side effect that matters: this check runs on EVERY progress
        event of every per-item tool, so it must be inert when idle."""
        emitted: list = []
        callback = self._callback(run_id, emitted)

        async def a_normal_node():
            from fichero_server.workflows.tools.progress import emit_progress_event

            for index in range(5):
                await emit_progress_event(
                    callback, "file_start", "", f"item-{index}", index, 5
                )

        asyncio.run(a_normal_node())
        assert len(emitted) == 5


class TestACancelledRunIsNotAFailedRun:
    def test_the_builder_re_raises_rather_than_reducing_to_an_error(self):
        """`WorkflowCancelled` must be handled BEFORE the generic node-error
        branch. Falling through would mark a user's Stop as a failed run and
        surface the cancellation as an error message."""
        import inspect

        from fichero_server.workflows import builder

        source = inspect.getsource(builder)
        cancelled_at = source.index("except WorkflowCancelled:")
        systemic_at = source.index("except SystemicErrorDetected:")
        generic_at = source.index("except Exception as e:", cancelled_at)

        assert cancelled_at < systemic_at < generic_at, (
            "the cancellation handler must precede the failure handlers, or a "
            "cancelled run is reported as failed (#4402)"
        )

    def test_the_runner_treats_it_as_cancelled_and_settles_documents(self):
        """The #4315 half: a run that stops must not strand documents at
        Status.processing, however it stopped."""
        import inspect

        from fichero_server.execution import runner

        source = inspect.getsource(runner)

        assert "except WorkflowCancelled:" in source, (
            "a cancel raised from inside a node has no handler — it would "
            "fall through and be recorded as a failure"
        )
        cancelled_at = source.index("except WorkflowCancelled:")
        systemic_at = source.index("except SystemicErrorDetected as e:")
        assert cancelled_at < systemic_at

        # Both stop paths must go through the one terminal routine, so they
        # cannot disagree about what a cancelled run records.
        assert source.count("async def _finish_as_cancelled") == 1
        assert source.count("await _finish_as_cancelled()") == 2, (
            "expected exactly two callers: the between-events check and the "
            "raised-from-inside-a-node handler"
        )
        terminal = source[source.index("async def _finish_as_cancelled") :][:3000]
        assert '_finalize_documents("cancelled"' in terminal, (
            "the shared terminal path must settle the run's documents, or a "
            "stopped run leaves rows stuck at Processing (#4315/#4398)"
        )
