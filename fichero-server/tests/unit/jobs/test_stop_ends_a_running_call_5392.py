"""`activity.run.stop-reaches-in-flight-calls` (#5392, #5375): a Stop ends a model call that is already RUNNING in its slot, books a
stopped cloud call's cost, frees the slot, and leaves no task behind. Real lane and rows; the call is a long sleep."""
from __future__ import annotations

import asyncio
import inspect
import json
import time

import pytest

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowCancelled, clear_cancellation, request_cancellation


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    yield
    clear_cancellation("run-sc")


def _row(db, subject):
    return db.execute_fetchone("SELECT state, reason, detail FROM jobs WHERE subject = ?", [subject])


async def _stopped_call(test_package, subject, model, lane, *, stop_after=0.4, note_usage=False):
    started = time.monotonic()
    loop = asyncio.get_running_loop()
    loop.call_later(stop_after, request_cancellation, "run-sc")
    with pytest.raises(WorkflowCancelled):
        async with jobs.lane_slot(str(test_package), "ask-a-model", subject, model=model, run_id="run-sc", lane=lane):
            if note_usage:
                jobs.note_usage({"provider": "openai", "model": "gpt-x", "kind": "chat", "input_tokens": 50,
                                 "output_tokens": 5, "total_tokens": 55, "estimated": False})
            await asyncio.sleep(30)
    return time.monotonic() - started


def test_a_stop_ends_a_running_local_call_at_once_and_the_row_reads_cancelled(db, test_package):
    took = asyncio.run(_stopped_call(test_package, "local page", "omlx:reader", "local-ml"))
    assert took < 5, f"the Stop waited for the call ({took:.1f} s)"
    state, reason, _ = _row(db, "local page")
    for _ in range(60):  # the slot's row settles on its lane thread just after the call ends
        state, reason, _ = _row(db, "local page")
        if state == "cancelled":
            break
        time.sleep(0.1)
    assert (state, reason) == ("cancelled", "Stopped by you")


def test_the_slot_is_released_so_the_next_page_starts(db, test_package):
    async def go():
        await _stopped_call(test_package, "first page", "omlx:reader", "local-ml")
        clear_cancellation("run-sc")
        ran = []
        async with jobs.lane_slot(str(test_package), "ask-a-model", "next page", model="omlx:reader", run_id="run-next", lane="local-ml"):
            ran.append(True)
        return ran

    assert asyncio.run(asyncio.wait_for(go(), 30)) == [True]


def test_a_stopped_cloud_call_with_no_usage_is_booked_as_an_estimate(db, test_package):
    asyncio.run(_stopped_call(test_package, "cloud page", "openai:gpt-x", "network"))
    detail = json.loads(_row(db, "cloud page")[2])
    (entry,) = detail["usage"]
    assert entry["kind"] == "stopped" and entry["estimated"] is True and entry["provider"] == "openai" and entry["model"] == "gpt-x"
    assert entry["input_tokens"] == jobs.STOPPED_CALL_INPUT_TOKENS


def test_a_stopped_cloud_call_that_already_had_usage_keeps_that_figure(db, test_package):
    asyncio.run(_stopped_call(test_package, "billed page", "openai:gpt-x", "network", note_usage=True))
    detail = json.loads(_row(db, "billed page")[2])
    assert [u["kind"] for u in detail["usage"]] == ["chat"], "no estimate on top of a measured figure"


def test_a_local_call_books_no_cost(db, test_package):
    asyncio.run(_stopped_call(test_package, "free page", "omlx:reader", "local-ml"))
    assert "usage" not in json.loads(_row(db, "free page")[2] or "{}")


def test_the_guard_ends_with_the_call_and_leaves_no_task(db, test_package):
    async def go():
        before = set(asyncio.all_tasks())
        async with jobs.lane_slot(str(test_package), "ask-a-model", "quick page", model="omlx:reader", run_id="run-sc", lane="local-ml"):
            pass
        await _stopped_call(test_package, "stopped page", "omlx:reader", "local-ml")
        await asyncio.sleep(0.2)
        return [t for t in asyncio.all_tasks() if t not in before and t is not asyncio.current_task() and not t.done()]

    assert asyncio.run(go()) == [], "a task outlived its slot"


def test_a_call_that_finishes_before_the_stop_is_untouched(db, test_package):
    async def go():
        async with jobs.lane_slot(str(test_package), "ask-a-model", "fast page", model="omlx:reader", run_id="run-sc", lane="local-ml"):
            await asyncio.sleep(0.05)
        request_cancellation("run-sc")  # too late: nothing to end
        await asyncio.sleep(0.6)

    asyncio.run(go())  # no exception
    for _ in range(60):
        if _row(db, "fast page")[0] == "done":
            break
        time.sleep(0.1)
    assert _row(db, "fast page")[0] == "done"


def test_the_guard_reads_only_the_in_memory_signal():
    """It runs ON the event loop (#5843): the stop is read from `cancellation_requested` (a dict and an Event), never the database."""
    source = inspect.getsource(jobs._end_call_on_stop) + inspect.getsource(jobs._stop_requested)
    assert "execute" not in source and "cancellation_requested" in source


def test_a_callee_that_swallows_the_cancel_still_ends_in_a_stop(db, test_package):
    """A call that catches CancelledError and returns normally must not turn the Stop into a finished page."""
    async def go():
        asyncio.get_running_loop().call_later(0.4, request_cancellation, "run-sc")
        with pytest.raises(WorkflowCancelled):
            async with jobs.lane_slot(str(test_package), "ask-a-model", "swallow page", model="omlx:reader", run_id="run-sc", lane="local-ml"):
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    pass  # swallowed, as a careless callee does

    asyncio.run(asyncio.wait_for(go(), 30))
    for _ in range(60):
        if _row(db, "swallow page")[0] == "cancelled":
            break
        time.sleep(0.1)
    assert _row(db, "swallow page")[:2] == ("cancelled", "Stopped by you")


def test_the_floor_is_labelled_as_an_estimate_in_the_rows_words(db, test_package):
    asyncio.run(_stopped_call(test_package, "words page", "openai:gpt-x", "network"))
    log = json.loads(_row(db, "words page")[2])["log"]
    assert any("ESTIMATE" in entry["message"] and str(jobs.STOPPED_CALL_INPUT_TOKENS) in entry["message"] for entry in log), log
