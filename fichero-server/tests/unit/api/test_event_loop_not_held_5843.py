"""#5843: three sync paths held the event loop for up to 255 s; each now runs off it."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from fichero_server.execution import jobs
from fichero_server.training import evaluation
from fichero_server.workflows.tools import vision_base


def test_the_jobs_schema_is_created_once_per_connection_not_per_poll():
    statements: list[str] = []
    conn = object()
    db = SimpleNamespace(conn=conn, path="x.duckdb", execute=lambda sql, *a: statements.append(sql))
    jobs._ensure(db)
    first = len(statements)
    for _ in range(5):
        jobs._ensure(db)
    assert len(statements) == first  # five polls later: no more DDL
    db.conn = object()  # a reconnect starts again
    jobs._ensure(db)
    assert len(statements) > first


def _loop_turn_during(blocking_call) -> float:
    async def go() -> float:
        work = asyncio.ensure_future(blocking_call())
        await asyncio.sleep(0.2)
        started = time.monotonic()
        await asyncio.sleep(0)
        took = time.monotonic() - started
        await work
        return took

    return asyncio.run(go())


def test_get_stats_runs_off_the_loop(monkeypatch):
    from fichero_server.api import main

    def slow_stats():
        time.sleep(1.5)  # lancedb opening
        return {}

    db = SimpleNamespace(all=lambda _model: [], count=lambda _model: 0, embedding_stats=slow_stats)
    monkeypatch.setattr(main, "EmbeddingStatsResponse", lambda **_kw: None)
    monkeypatch.setattr(main, "LibraryStatsResponse", lambda **_kw: None)
    assert _loop_turn_during(lambda: main.get_stats(db)) < 1.0


def test_vision_locales_are_never_loaded_on_the_loop(monkeypatch):
    calls: list[int] = []

    def slow_locales():
        calls.append(1)
        time.sleep(1.5)  # the PyObjC Vision bundle load
        return frozenset({"en-US"})

    monkeypatch.setattr(vision_base, "_supported_vision_locales", slow_locales)
    monkeypatch.setattr(vision_base, "supported_locales_are_known", lambda: False)

    async def on_loop():
        return evaluation.apple_vision_here()

    assert _loop_turn_during(on_loop) < 1.0
    assert calls == []  # the loop did not ask; a worker thread still can
    assert evaluation.apple_vision_here() is True and calls == [1]
