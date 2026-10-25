"""#6122 (`search.embedding.change-is-a-re-embed-run`): changing a project's embedding model is a run that embeds every page
again in a shadow and swaps it in whole. Search reads the old vectors until the swap; a page is never embedded twice; the plan
(pages, time, cost) is said first. The embedder is a recording stub: the model itself is not loaded."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.db import embeddings
from fichero_server.db.embeddings import DatabaseEmbeddingMixin
from fichero_server.models import Document

E5 = "intfloat/multilingual-e5-large"


@pytest.fixture
def embedded(db, monkeypatch):
    """A library with three pages embedded in bge-m3 (the default), and a stub embedder that records every text."""
    monkeypatch.delenv(embeddings.EMBED_MODEL_ENV, raising=False)
    seen: list[tuple[str, str]] = []  # (model id the call ran in, text)

    def embed_texts(self, texts, *, role="passage"):
        seen.extend((self._get_embedding_model_id(), t) for t in texts)
        return [[float(len(t) % 7), 1.0, 0.0, 0.5] for t in texts]

    monkeypatch.setattr(DatabaseEmbeddingMixin, "_embed_texts", embed_texts)
    monkeypatch.setattr(DatabaseEmbeddingMixin, "_ensure_embedder", lambda self: None)
    for i in range(3):
        db.save(Document(name=f"p{i}", page_content=" ".join(f"Line {j} of page {i} is about the harbour." for j in range(60))))
    db.reindex_all()
    seen.clear()
    return db, seen


def _model_ids(db):
    return {i for ids in db.embedding_table_model_ids().values() for i in ids}


def test_the_plan_says_pages_time_and_cost_before_anything_runs(embedded):
    db, seen = embedded
    plan = db.embedding_change_plan(E5)
    assert plan["from_model"] == "BAAI/bge-m3" and plan["to_model"] == E5 and plan["same"] is False
    assert plan["pages"] == 3 and plan["passages"] >= 3 and plan["seconds_estimate"] >= 1
    assert plan["cost_usd"] == 0.0 and plan["runs_on"] == "this-mac" and plan["keeps_old_vectors_until_done"] is True
    assert seen == [], "a plan embeds nothing"
    with pytest.raises(ValueError):
        db.embedding_change_plan("no/such-model")


def test_the_run_builds_in_a_shadow_keeps_search_on_the_old_vectors_then_swaps_whole(embedded):
    db, seen = embedded
    old_ids = _model_ids(db)
    assert len(old_ids) == 1
    during: list[tuple[set, str]] = []
    real = DatabaseEmbeddingMixin._embed_texts

    def spying(self, texts, *, role="passage"):
        during.append((_model_ids(db), db._get_embedding_space().source_model_name))  # what search would see right now
        return real(self, texts, role=role)

    DatabaseEmbeddingMixin._embed_texts = spying
    try:
        done: list[tuple[int, int]] = []
        result = db.migrate_embedding_space(confirm=True, to_model=E5, on_progress=lambda d, t: done.append((d, t)))
    finally:
        DatabaseEmbeddingMixin._embed_texts = real
    assert during and all(ids == old_ids and space == "BAAI/bge-m3" for ids, space in during), \
        "while the run builds, search still reads the old vectors in the old space"
    assert done and done[-1][0] == done[-1][1] == 3  # the pages, counted as they are looked at
    package = Path(str(db.path)).parent
    assert json.loads((package / "embedding.json").read_text())["model"] == E5
    assert db._get_embedding_space().source_model_name == E5
    assert _model_ids(db) == {embeddings.PINNED_EMBEDDING_SPACE.model_id} and not (old_ids & _model_ids(db))
    assert not (package / "vectors-next").exists() and not (package / "vectors-old").exists()
    assert result["documents_indexed"] == 3
    new_model = embeddings.PINNED_EMBEDDING_SPACE.model_id
    assert {m for m, _t in seen} == {new_model}, "every text was embedded in the new space, none in the old"
    assert len(seen) == len({t for _m, t in seen}) >= 3, "each passage once: the catch-up after the swap embeds nothing again"


def test_a_stopped_run_is_carried_on_and_embeds_no_page_twice(embedded, monkeypatch):
    db, seen = embedded
    calls = {"n": 0}
    real = DatabaseEmbeddingMixin.embed_many_unless_current

    def stops_after_one_batch(self, docs):
        calls["n"] += 1
        if calls["n"] == 2 and getattr(self, "_embedding_space_override", None) is not None:
            raise RuntimeError("the Mac went to sleep")
        return real(self, docs)

    monkeypatch.setattr(DatabaseEmbeddingMixin, "embed_many_unless_current", stops_after_one_batch)
    monkeypatch.setattr(embeddings.DatabaseEmbeddingMixin, "_embed_pages_unless_current",
                        _one_page_per_batch(DatabaseEmbeddingMixin._embed_pages_unless_current))
    with pytest.raises(RuntimeError, match="went to sleep"):
        db.migrate_embedding_space(confirm=True, to_model=E5)
    assert _model_ids(db) != {embeddings.PINNED_EMBEDDING_SPACE.model_id}, "the live vectors are untouched by a stopped run"
    assert db._get_embedding_space().source_model_name == "BAAI/bge-m3"
    done_first = len(seen)
    assert done_first >= 1
    monkeypatch.setattr(DatabaseEmbeddingMixin, "embed_many_unless_current", real)
    db.migrate_embedding_space(confirm=True, to_model=E5)
    assert len(seen) == len({t for _m, t in seen}), "the run that carried on embedded none of the passages again"
    assert _model_ids(db) == {embeddings.PINNED_EMBEDDING_SPACE.model_id}


def _one_page_per_batch(real):
    def run(self, on_progress, batch_size=32):
        return real(self, on_progress, batch_size=1)
    return run


def test_the_other_open_connections_see_the_new_model_without_being_told(embedded):
    db, _seen = embedded
    other = type("Other", (DatabaseEmbeddingMixin,), {})()
    other.path = db.path
    assert other._get_embedding_space().source_model_name == "BAAI/bge-m3"
    db.migrate_embedding_space(confirm=True, to_model=E5)
    assert other._get_embedding_space().source_model_name == E5, "keyed on embedding.json, not on one instance"


def test_the_same_model_is_the_in_place_rebuild_not_a_second_path(embedded, monkeypatch):
    db, _seen = embedded
    called = []
    monkeypatch.setattr(DatabaseEmbeddingMixin, "_migrate_to_other_space", lambda *a, **k: called.append(1))
    db.migrate_embedding_space(confirm=True, to_model="BAAI/bge-m3")
    assert called == []


def test_the_routes_show_the_plan_then_queue_the_one_reindex_job(client, db, monkeypatch):
    monkeypatch.delenv(embeddings.EMBED_MODEL_ENV, raising=False)
    db.save(Document(name="p", page_content="A page about a harbour. " * 20))
    plan = client.get("/api/search/embedding/change-plan", params={"model": E5})
    assert plan.status_code == 200, plan.text
    assert plan.json()["to_model"] == E5 and plan.json()["pages"] >= 1 and plan.json()["cost_usd"] == 0.0
    assert client.get("/api/search/embedding/change-plan", params={"model": "no/such"}).status_code == 422
    unconfirmed = client.post("/api/search/embedding/change", json={"model": E5})
    assert unconfirmed.status_code == 422 and "plan" in unconfirmed.json()["detail"]
    same = client.post("/api/search/embedding/change", json={"model": "BAAI/bge-m3", "confirm": True})
    assert same.status_code == 409
    started = client.post("/api/search/embedding/change", json={"model": E5, "confirm": True})
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "started" and started.json()["job_id"]
    from fichero_server.actions.registry import registry

    assert "search.change_embedding_model" in registry.names(), "the route queues the job through the audited action"


def test_the_reindex_job_with_a_target_model_runs_the_migration_and_a_failure_keeps_the_old_vectors(db, monkeypatch):
    import asyncio
    from fichero_server.workflows.task_types import BackgroundTask, TaskConfig, TaskStatus, TaskType
    from fichero_server.workflows.task_workers import TaskWorkersMixin

    class Worker(TaskWorkersMixin):
        database = db

        async def _save_task_progress(self, task):
            return None

    def task():
        return BackgroundTask(task_id="t1", task_type=TaskType.REINDEX, name="n", status=TaskStatus.RUNNING,
                              config=TaskConfig(task_type=TaskType.REINDEX, options={"to_model": E5}))

    calls = []
    monkeypatch.setattr(type(db), "migrate_embedding_space",
                        lambda self, **kw: calls.append(kw) or {"documents_indexed": 2, "before": {}, "after": {}})
    ok = asyncio.run(Worker()._do_reindex(task()))
    assert ok.success and calls[0]["to_model"] == E5 and calls[0]["confirm"] is True

    def boom(self, **kw):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(type(db), "migrate_embedding_space", boom)
    failed_task = task()
    failed = asyncio.run(Worker()._do_reindex(failed_task))
    assert not failed.success and "model download failed" in failed.message and failed_task.status == TaskStatus.FAILED
