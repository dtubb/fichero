"""Stop and Pause take effect between files in economy HTR (#5375, `activity.run.stop-reaches-economy-htr`): the
step used to read every file in one blocking loop, so Stop waited for the whole step."""
import asyncio
import threading

import pytest

from fichero_server.execution import cancellation
from fichero_server.execution.cancellation import WorkflowCancelled, WorkflowPaused
from fichero_server.workflows.tools import economy_htr as module


def _run(files, run_id, seen, loop_ids, then=None):
    def fake(path, **_):
        seen.append(path)
        loop_ids.append(threading.get_ident())
        if then:
            then(path)
        return {"source": path, "text": "t", "lines": [], "backend": "apple", "error": None}

    module.economy_htr_file = fake
    return asyncio.run(module.economy_htr({"files": files, "backend": "apple"}, {"task_id": run_id}, None))


@pytest.fixture(autouse=True)
def _restore():
    real = module.economy_htr_file
    yield
    module.economy_htr_file = real


def test_stop_between_files_ends_the_step_with_the_rest_unread():
    seen = []
    with pytest.raises(WorkflowCancelled):
        _run(["a", "b", "c"], "run-stop-5375", seen, [],
             then=lambda p: cancellation.request_cancellation("run-stop-5375"))
    assert seen == ["a"]
    cancellation.clear_cancellation("run-stop-5375")


def test_pause_between_files_ends_the_step_as_paused():
    seen = []
    with pytest.raises(WorkflowPaused):
        _run(["a", "b"], "run-pause-5375", seen, [], then=lambda p: cancellation.request_pause("run-pause-5375"))
    assert seen == ["a"]
    cancellation.clear_pause("run-pause-5375")


def test_without_a_request_every_file_is_read_off_the_event_loop():
    seen, threads = [], []
    out = _run(["a", "b"], "run-quiet-5375", seen, threads)
    assert seen == ["a", "b"] and out["texts"] == ["t", "t"]
    assert threading.get_ident() not in threads
