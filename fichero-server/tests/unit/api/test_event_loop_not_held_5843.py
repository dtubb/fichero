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
    async def go() -> float:  # a 0.2 s sleep beside the call: the turn after it would miss a block at the start (#6178)
        work = asyncio.ensure_future(blocking_call())
        started = time.monotonic()
        await asyncio.sleep(0.2)
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


def test_the_activity_poll_reads_the_job_table_off_the_loop(monkeypatch):
    from fichero_server.api.routes.system import activity

    def slow_snapshot(_db):
        time.sleep(1.5)  # waiting on the transaction gate behind a write
        return []

    monkeypatch.setattr(jobs, "snapshot", slow_snapshot)
    monkeypatch.setattr(jobs, "waiting_reason_of", lambda *_a, **_k: None)
    monkeypatch.setattr("fichero_server.importers.derivatives.background_jobs_snapshot", lambda _lib: [])
    db = SimpleNamespace(path="/lib/x.duckdb")
    monkeypatch.setattr(activity, "get_activity_tracker", lambda _p: (_ for _ in ()).throw(RuntimeError("skip")))
    assert _loop_turn_during(lambda: activity.list_background_jobs(db)) < 1.0


def test_the_job_tree_reads_off_the_loop(monkeypatch):
    from fichero_server.api.routes.system import activity

    def slow_tree(_db, _id):
        time.sleep(1.5)
        return None  # 404 after the wait; the loop was free meanwhile

    monkeypatch.setattr(jobs, "queue_of", lambda _id: False)
    monkeypatch.setattr(jobs, "tree", slow_tree)

    async def call():
        try:
            await activity.get_job_tree("j", None, SimpleNamespace())
        except Exception:  # noqa: BLE001 -- the HTTPException 404
            pass

    assert _loop_turn_during(call) < 1.0


def test_a_cold_apple_vision_answer_on_the_loop_says_it_is_warming_up(monkeypatch):
    from fichero_server.recipes import bakeoff

    monkeypatch.setattr(vision_base, "supported_locales_are_known", lambda: False)
    monkeypatch.setattr(evaluation, "on_this_mac", lambda *_a, **_k: False)
    card = SimpleNamespace(runs_here=True, open_licence=True)

    async def ask():
        return bakeoff._not_scored_because(card, "vision", evaluation.APPLE_VISION, "apple")

    assert "starting up" in asyncio.run(ask())
