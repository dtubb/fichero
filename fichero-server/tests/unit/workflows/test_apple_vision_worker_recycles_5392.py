"""#5392 (`compute.apple-vision.worker-recycles-itself`): Apple Vision runs in a child process that is killed, not abandoned.

A call stuck in Apple's recogniser cannot be interrupted. It used to stay a thread (memory held, later reads refused with
'Restart the engine'). Now the parent kills the child that holds it; the page fails in words, the next call starts a new
child, nothing is left stuck. The calls here are module-level functions the forked child finds by name."""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time

import pytest

from fichero_server.workflows.tools import apple_vision_worker as worker
from fichero_server.workflows.tools import vision_base as vb

DEADLINE = 0.6


def read_page(path: str, language: str = "en") -> str:
    """Stands for apple_vision_ocr: a page named stuck* never returns."""
    if path.startswith("stuck"):
        time.sleep(60)
    if path.startswith("boom"):
        raise ValueError("not an image")
    return f"read {path}"


@pytest.fixture(autouse=True)
def _child_mode(monkeypatch):
    monkeypatch.delenv("FICHERO_APPLE_VISION_IN_PROCESS", raising=False)
    monkeypatch.setattr(vb, "_apple_vision_deadline", lambda: DEADLINE)
    worker.WORKER.close()
    worker.WORKER.starts = worker.WORKER.recycles = 0
    yield
    worker.WORKER.close()


def _read(path: str) -> str:
    return asyncio.run(vb._apple_vision_call(read_page, path, "en"))


def test_a_call_that_never_returns_kills_the_child_and_fails_its_page_in_words():
    began = time.monotonic()
    with pytest.raises(vb.AppleVisionTimeout) as raised:
        _read("stuck1")
    assert time.monotonic() - began < DEADLINE + 1.0
    assert worker.WORKER.recycles == 1
    assert vb._APPLE_VISION_GATE.stuck == 0, "the child was killed, so no call is left inside the recogniser"
    words = str(raised.value)
    assert "worker was stopped" in words and "restart the engine" not in words.lower()


def test_the_next_call_gets_a_new_child_and_reads():
    with pytest.raises(vb.AppleVisionTimeout):
        _read("stuck1")
    assert _read("page2") == "read page2"
    assert worker.WORKER.starts == 2, "a new child after the kill"
    assert _read("page3") == "read page3"
    assert worker.WORKER.starts == 2, "the same child while it works"


def test_many_stuck_pages_never_close_the_gate():
    for n in range(vb.APPLE_VISION_STUCK_CEILING + 2):  # past the ceiling that used to refuse every read
        with pytest.raises(vb.AppleVisionTimeout):
            _read(f"stuck{n}")
    assert _read("page") == "read page"


def test_a_call_that_raises_raises_the_same_error_for_its_page():
    with pytest.raises(ValueError, match="not an image"):
        _read("boom")
    assert _read("page") == "read page", "the child stays up after a call's own error"
    assert worker.WORKER.recycles == 0


def test_a_child_that_dies_fails_its_page_and_the_next_call_starts_again():
    assert _read("page") == "read page"
    worker.WORKER._process.kill()
    worker.WORKER._process.join(5)
    assert _read("again") == "read again"


def test_the_parent_never_imports_vision_itself():
    """Only the child imports the Vision framework. The parent's ObjC runtime IS loaded (the engine's packages import
    Quartz and PyObjC at import, measured 2026-10-25), so the child is forked with OBJC_DISABLE_INITIALIZE_FORK_SAFETY set,
    as the embedder's is, and `FICHERO_APPLE_VISION_START=spawn` is there for a dev engine; real Vision under that fork is
    checked on the M4."""
    code = (
        "import sys\n"
        "import fichero_server.workflows.tools.apple_vision_worker\n"
        "import fichero_server.workflows.tools.vision_base\n"
        "assert 'Vision' not in sys.modules, 'the parent imported the Vision framework'\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-600:]


def test_a_page_failed_by_a_recycled_worker_is_read_once_more_by_itself():
    """Part 2 (#5392): the failure words of a killed or dead worker name a passing cause, so the per-page retry
    (`page_retry`, the never-rerun path: only that page, the done ones untouched) reads it again in the new worker; the real
    timeout and a real second read below show it."""
    from fichero_server.workflows import page_retry

    assert page_retry.is_passing_cause(vb._apple_vision_timeout(300, recycled=True))
    assert page_retry.is_passing_cause(worker.WorkerFailure(
        "Apple Vision's worker stopped while reading this page; it starts again for the next one."))
    with pytest.raises(vb.AppleVisionTimeout) as raised:
        _read("stuck1")
    assert page_retry.is_passing_cause(str(raised.value)), "the words the real timeout gives"
    assert _read("stuck1".replace("stuck", "page")) == "read page1", "and the second read finds a new worker"
