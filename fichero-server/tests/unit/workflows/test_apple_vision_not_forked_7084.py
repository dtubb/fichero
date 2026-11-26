"""#7084: Apple Vision never runs in a child forked without exec (it crashed with SIGSEGV on the child side of fork on an M1).

By default the calls run on the engine's own threads behind the gate and its deadline. Only FICHERO_APPLE_VISION_START=spawn
starts a child, and that child is exec'd (multiprocessing spawn). A child that crashes fails its page at once with the signal
named, and the per-page retry does not read that page again into the same crash."""
from __future__ import annotations

import asyncio
import os
import signal

import pytest

from fichero_server.workflows import page_retry
from fichero_server.workflows.tools import apple_vision_worker as worker
from fichero_server.workflows.tools import vision_base as vb


def segfault(path: str, language: str = "en") -> str:
    """Stands for apple_vision_ocr in a child that crashes."""
    os.kill(os.getpid(), signal.SIGSEGV)
    return "unreachable"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("FICHERO_APPLE_VISION_IN_PROCESS", raising=False)
    monkeypatch.delenv("FICHERO_APPLE_VISION_START", raising=False)
    worker.WORKER.close()
    yield
    worker.WORKER.close()


def test_by_default_the_calls_run_in_the_engine_not_in_a_forked_child():
    assert worker.in_process()
    assert asyncio.run(vb._apple_vision_call(os.getpid)) == os.getpid()
    assert worker.WORKER.starts == 0


def test_a_fork_start_is_refused_not_quietly_replaced(monkeypatch):
    monkeypatch.setenv("FICHERO_APPLE_VISION_START", "fork")
    with pytest.raises(RuntimeError, match="fork"):
        worker.in_process()


def test_spawn_starts_an_exec_child(monkeypatch):
    monkeypatch.setenv("FICHERO_APPLE_VISION_START", "spawn")
    assert not worker.in_process()
    assert not hasattr(worker, "fork_from_seed")


def test_a_crashing_child_fails_fast_naming_the_signal_and_is_not_retried(monkeypatch):
    monkeypatch.setenv("FICHERO_APPLE_VISION_START", "spawn")
    with pytest.raises(vb.AppleVisionTimeout) as raised:
        asyncio.run(vb._apple_vision_call(segfault, "p1", "en"))
    assert "Apple Vision's worker crashed (SIGSEGV)" in str(raised.value)
    assert not page_retry.is_passing_cause(str(raised.value)), "the same page would crash the same way"


def test_a_default_call_forks_nothing(monkeypatch):
    """Pins the fix itself: with every way to fork made to raise, a default call through the public path still returns."""
    import multiprocessing

    from fichero_server.db import embed_process

    def no_fork(*args, **kwargs):
        raise AssertionError("Apple Vision forked a child (#7084)")

    real_get_context = multiprocessing.get_context

    def no_fork_context(method=None):
        if method == "fork":
            no_fork()
        return real_get_context(method)

    before = worker.WORKER.starts
    monkeypatch.setattr(os, "fork", no_fork)
    monkeypatch.setattr(embed_process, "fork_from_seed", no_fork, raising=False)
    monkeypatch.setattr(multiprocessing, "get_context", no_fork_context)
    assert asyncio.run(vb._apple_vision_call(os.getpid)) == os.getpid()
    assert worker.WORKER.starts == before
