"""#5847: onnxruntime's session init held the engine's GIL for 18 minutes; the model now lives in a child process."""
from __future__ import annotations

import asyncio
import faulthandler
import io
import time

import pytest

from fichero_server.core import loop_lag
from fichero_server.db import embed_process


@pytest.fixture
def forked(monkeypatch):
    monkeypatch.delenv("FICHERO_EMBED_IN_PROCESS", raising=False)


def test_a_fake_model_embeds_through_the_child(forked, monkeypatch):
    monkeypatch.setenv("FICHERO_EMBED_FAKE_INIT_SECONDS", "0")
    embedder = embed_process.RemoteEmbedder("m", "/nowhere", 1)
    try:
        assert embedder.embed(["ab", "abc"]) == [[2.0, 1.0], [3.0, 1.0]]
    finally:
        embedder.close()
    assert not embedder.alive()


def test_health_answers_under_a_second_beside_a_slow_model_init(forked, monkeypatch):
    monkeypatch.setenv("FICHERO_EMBED_FAKE_INIT_SECONDS", "3")

    async def go() -> float:
        loader = asyncio.ensure_future(asyncio.to_thread(embed_process.RemoteEmbedder, "m", "/x", 1))
        await asyncio.sleep(0.3)
        started = time.monotonic()
        await asyncio.sleep(0)  # what /api/health needs: one turn of the loop
        took = time.monotonic() - started
        (await loader).close()
        return took

    assert asyncio.run(go()) < 1.0


def test_an_init_that_runs_over_is_killed_and_fails_in_words(forked, monkeypatch):
    monkeypatch.setenv("FICHERO_EMBED_FAKE_INIT_SECONDS", "30")
    started = time.monotonic()
    with pytest.raises(embed_process.EmbedderUnavailable, match="took more than"):
        embed_process.RemoteEmbedder("m", "/x", 1, init_timeout=0.5)
    assert time.monotonic() - started < 10


def test_the_watchdog_is_armed_at_startup_and_rearmed_by_the_heartbeat(monkeypatch):
    calls: list[tuple[float, bool]] = []
    monkeypatch.setattr(faulthandler, "dump_traceback_later",
                        lambda seconds, repeat=False, file=None, exit=False: calls.append((seconds, repeat)))
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", lambda: None)

    async def go() -> None:
        stop = loop_lag.start(asyncio.get_running_loop(), ping_seconds=0.05, dump_seconds=7, dump_file=io.StringIO())
        assert calls == [(7, True)]  # armed at startup
        await asyncio.sleep(0.3)
        stop.set()

    asyncio.run(go())
    assert len(calls) >= 3 and all(c == (7, True) for c in calls)  # and re-armed by the loop's heartbeat
