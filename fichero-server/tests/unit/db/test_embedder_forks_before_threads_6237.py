"""#6237, `activity.lane.embedder-forks-before-threads`: the search embedder's process is forked from a seed the engine
forks once at start, before any other thread exists, and never from the running engine. WHY: forked from the engine at
first use, the child inherited uvicorn's selector and LanceDB's loop thread; LanceDB's loop died in it with "Bad file
descriptor" (the M4 106-page run). The shipped engine cannot spawn (its `sys.executable` is the sandboxed stub).
"""
from __future__ import annotations

import os
import threading

import pytest

from fichero_server.db import embed_process


@pytest.fixture
def seed(monkeypatch):
    monkeypatch.delenv("FICHERO_EMBED_IN_PROCESS", raising=False)
    monkeypatch.setattr(embed_process, "_cached", lambda *_a: True)  # the fake model is "in the cache"
    monkeypatch.setenv("FICHERO_EMBED_FAKE_INIT_SECONDS", "0")
    embed_process.start_seed()
    yield embed_process._SEED
    embed_process.stop_seed()


def test_the_worker_is_the_seeds_child_not_the_engines(seed):
    embedder = embed_process.RemoteEmbedder("m", "/nowhere", 1)
    try:
        assert embedder.embed(["ab", "abc"]) == [[2.0, 1.0], [3.0, 1.0]]
        assert embedder.parent_pid() == seed.pid != os.getpid(), "the worker was forked by the engine"
        assert embedder.alive()
    finally:
        embedder.close()
    assert not embedder.alive()


def test_a_worker_that_crashes_is_asked_of_the_seed_again(seed, tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_EMBED_FAKE_CRASH", str(tmp_path / "crashed"))
    embedder = embed_process.RemoteEmbedder("m", "/nowhere", 1)
    try:
        assert embedder.embed(["crash"]) == [[5.0, 1.0]], "the batch is answered by a second worker"
        assert embedder.parent_pid() == seed.pid
    finally:
        embedder.close()


def test_the_engine_makes_the_seed_before_it_starts_any_thread(monkeypatch):
    from fichero_server import __main__ as engine

    order: list[str] = []
    real = threading.Thread

    def seed_here() -> None:
        order.append("seed")
        raise SystemExit(0)  # main() is needed only as far as the seed

    def a_thread(*args, **kwargs):
        order.append(f"thread {kwargs.get('name')}")
        return real(*args, **kwargs)

    monkeypatch.setattr(embed_process, "start_seed", seed_here)
    monkeypatch.setattr(threading, "Thread", a_thread)
    with pytest.raises(SystemExit):
        engine._main([])
    assert order == ["seed"], f"the engine started a thread before the seed: {order}"


def test_apple_visions_worker_is_the_seeds_child_too(seed, monkeypatch):
    """Apple Vision's worker (#5392) is forked the same way: from the seed, never from the running engine."""
    from fichero_server.workflows.tools import apple_vision_worker as vision

    monkeypatch.delenv("FICHERO_APPLE_VISION_IN_PROCESS", raising=False)
    monkeypatch.delenv("FICHERO_APPLE_VISION_START", raising=False)
    vision.WORKER.close()
    try:
        assert vision.WORKER.call(("os", "getppid"), (), 10) == seed.pid != os.getpid()
    finally:
        vision.WORKER.close()


def test_a_stuck_vision_call_still_kills_its_seeded_worker_and_the_next_one_reads(seed, monkeypatch):
    from fichero_server.workflows.tools import apple_vision_worker as vision

    monkeypatch.delenv("FICHERO_APPLE_VISION_IN_PROCESS", raising=False)
    monkeypatch.delenv("FICHERO_APPLE_VISION_START", raising=False)
    vision.WORKER.close()
    try:
        with pytest.raises(vision.WorkerTimeout):
            vision.WORKER.call(("time", "sleep"), (5,), 0.5)
        assert vision.WORKER.call(("os", "getppid"), (), 10) == seed.pid, "the new worker is the seed's child"
    finally:
        vision.WORKER.close()


def test_a_bad_request_does_not_end_the_seed(seed):
    """One request the seed cannot run (here, args it cannot read) is answered with no worker; the next one is served."""
    ours, theirs = embed_process.socket.socketpair()
    try:
        bad = b"not json"
        embed_process.socket.send_fds(seed.control, [len(bad).to_bytes(8, "big") + bad], [theirs.fileno()])
        assert int.from_bytes(embed_process._recv_exactly(seed.control, 8), "big") == 0
    finally:
        ours.close()
        theirs.close()
    embedder = embed_process.RemoteEmbedder("m", "/nowhere", 1)
    try:
        assert embedder.embed(["ab"]) == [[2.0, 1.0]]
        assert embedder.parent_pid() == seed.pid, "the seed still forks after a bad request"
    finally:
        embedder.close()


def test_a_killed_seed_falls_back_to_a_direct_fork(seed):
    os.kill(seed.pid, embed_process.signal.SIGKILL)
    embed_process._wait_gone(seed.pid, 5)
    embedder = embed_process.RemoteEmbedder("m", "/nowhere", 1)
    try:
        assert embedder.embed(["ab"]) == [[2.0, 1.0]], "the embedder still starts when the seed is gone"
        assert embedder.parent_pid() == os.getpid()
    finally:
        embedder.close()
    assert embed_process._SEED is None, "a gone seed is forgotten, not asked again"
