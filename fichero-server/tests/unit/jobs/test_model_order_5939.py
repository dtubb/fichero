"""`activity.lane.model-order` (#5939): with no model loaded, the lane takes Kraken's block first, then the local
language model, then spaCy, then the embedder; the loaded model still goes first of all."""
from __future__ import annotations

import duckdb

from fichero_server.execution import jobs
from tests.unit.jobs.test_job_queue import _kind, _wait_for  # noqa: F401  (the real-lane helpers)

MODELS = ["embedder", "spacy", "omlx:qwen", "kraken:blla"]


def test_the_rank_follows_the_order():
    assert sorted(MODELS, key=jobs._model_rank) == ["kraken:blla", "omlx:qwen", "spacy", "embedder"]
    assert jobs._model_rank(None) == jobs._model_rank("omlx:x")  # work with no model sits with the language model


def test_a_librarys_own_pick_uses_the_same_order():
    con = duckdb.connect()
    con.execute("CREATE TABLE jobs (model VARCHAR)")
    con.executemany("INSERT INTO jobs VALUES (?)", [(m,) for m in MODELS])
    rows = [r[0] for r in con.execute(f"SELECT model FROM jobs ORDER BY {jobs._model_rank_sql()}").fetchall()]
    assert rows == sorted(MODELS, key=jobs._model_rank)


def test_the_lane_starts_with_kraken_when_all_four_wait(db, monkeypatch):
    ran: list[str] = []
    for kind, model in (("t-embed", "embedder"), ("t-spacy", "spacy"), ("t-mlx", "omlx:qwen"), ("t-kraken", "kraken:blla")):
        _kind(monkeypatch, kind, model, ran)
    jobs.set_paused(True)
    for kind in ("t-embed", "t-spacy", "t-mlx", "t-kraken"):  # queued in the WRONG order
        jobs.enqueue(db, kind, kind)
    jobs.set_paused(False)
    assert _wait_for(lambda: len(ran) >= 1)
    assert ran[0] == "t-kraken"
