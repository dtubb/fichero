"""`activity.read.get-embeds-its-own-query` and `activity.read.claims-backfill-is-a-lane-job` (review 361 ruling): a GET embeds its
own query text, within a bound, and never anything else; the claims without a vector are a lane job, queued once."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.kg.claim_search import search_claims_semantic_impl
from fichero_server.api.routes.kg.entity_curation import search_entities_semantic_impl
from fichero_server.core import no_model_in_get
from fichero_server.db.embeddings import KG_CLAIM_EMBEDDINGS_TABLE, DatabaseEmbeddingMixin


class _Row(SimpleNamespace):
    def model_dump(self):
        return dict(vars(self))


class _FakeDb(DatabaseEmbeddingMixin):
    """The real `_embed_text` (and so the real GET bound); the embedder itself, the vectors and the rows are stand-ins."""

    def __init__(self, delay: float = 0.0, claims_total: int = 1, indexed: int = 1) -> None:
        self.delay, self.claims_total, self.indexed = delay, claims_total, indexed
        self.embedded: list[tuple[str, str]] = []

    def _embed_text_now(self, text, role):
        time.sleep(self.delay)
        self.embedded.append((text, role))
        return [1.0, 0.0]

    def _lance_tables(self):
        return [KG_CLAIM_EMBEDDINGS_TABLE]

    def ensure_canonical_entity_embedding_table(self):
        return "kg_entity_embeddings"

    def search_vectors(self, table, vector, limit=20):
        return [{"id": "x1", "_score": 0.9}]

    def _vector_table_stats(self, table_name):
        return {"indexed_count": self.indexed, "table_exists": True}

    def count(self, model, **filters):
        return self.claims_total

    def all(self, model):
        return [_Row(id="x1", claim_type="fact", curation_state="proposed", entity_type="person")]


@pytest.fixture
def no_eviction(monkeypatch):
    """Anything that loads, runs or unloads a heavy model is a spy: the loaded model must be left alone (review 361 c)."""
    from fichero_server.db import embeddings
    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime

    touched: list[str] = []
    for owner, name in ((kraken_runtime, "_kraken_call"), (jobs, "run_on_lane"), (jobs, "run_on_lane_blocking"),
                        (embeddings, "release_idle_embedders")):
        monkeypatch.setattr(owner, name, lambda *a, _n=name, **k: touched.append(_n))
    return touched


def test_a_get_answers_claims_and_entities_with_a_query_embedding(no_eviction):
    db = _FakeDb()
    with no_model_in_get.marked_get("/api/kg/claim-search"):
        claims = search_claims_semantic_impl(db=db, q="who sold the mill")
        entities = search_entities_semantic_impl(db=db, q="who sold the mill")
    assert claims.count == 1 and entities.count == 1
    assert db.embedded == [("who sold the mill", "query")] * 2, "the query, once per search, and nothing else"


def test_a_passage_embed_stays_refused_in_a_get():
    with no_model_in_get.marked_get("/api/kg/claim-search"):
        with pytest.raises(no_model_in_get.ModelWorkInGet):
            _FakeDb()._embed_text("a claim", role="passage")
        with pytest.raises(no_model_in_get.ModelWorkInGet):
            _FakeDb()._embed_texts(["a claim"])


def test_with_the_embedder_busy_past_the_bound_the_get_answers_in_words_within_it(monkeypatch):
    monkeypatch.setattr(no_model_in_get, "QUERY_EMBED_SECONDS", 0.1)
    db = _FakeDb(delay=0.6)
    started = time.monotonic()
    with no_model_in_get.marked_get("/api/kg/entities/semantic"):
        for search in (search_claims_semantic_impl, search_entities_semantic_impl):
            with pytest.raises(HTTPException) as refused:
                search(db=db, q="who sold the mill")
            assert refused.value.status_code == 503 and "busy" in refused.value.detail
    assert time.monotonic() - started < 0.5, "it answered at the bound, it did not wait for the embedder"
    time.sleep(0.7)  # let the late embeds finish so the next test finds the pool free


def test_the_loaded_heavy_model_is_untouched_by_a_get_that_embeds(no_eviction):
    with no_model_in_get.marked_get("/api/kg/claim-search"):
        search_claims_semantic_impl(db=_FakeDb(), q="q")
        search_entities_semantic_impl(db=_FakeDb(), q="q")
    assert no_eviction == [], "no Kraken call, lane job or unload was made for a query embedding"


def test_a_get_with_unembedded_claims_queues_the_backfill_once(db, monkeypatch):
    from fichero_server.execution import jobs
    from fichero_server.importers.derivatives import EMBED_CLAIMS_KIND

    jobs.load_kinds()
    gate = threading.Event()
    monkeypatch.setitem(jobs.KINDS, EMBED_CLAIMS_KIND, jobs.Kind(
        run=lambda _db, _subject: gate.wait(30), model="embedder", lane="embed", name="Embed claims for search"))
    fake = _FakeDb(claims_total=5, indexed=2)
    monkeypatch.setattr(db, "_lance_tables", fake._lance_tables)
    monkeypatch.setattr(db, "_embed_text", lambda text, role="query": [1.0, 0.0])
    monkeypatch.setattr(db, "search_vectors", fake.search_vectors)
    monkeypatch.setattr(db, "_vector_table_stats", fake._vector_table_stats)
    monkeypatch.setattr(db, "count", fake.count)
    monkeypatch.setattr(db, "all", fake.all)
    try:
        with no_model_in_get.marked_get("/api/kg/claim-search"):
            answers = [search_claims_semantic_impl(db=db, q="q") for _ in range(3)]
        assert [a.not_embedded for a in answers] == [3, 3, 3], "it says how many claims are not embedded yet"
        rows = db.execute_fetchall("SELECT id FROM jobs WHERE kind = ?", [EMBED_CLAIMS_KIND])
        assert len(rows) == 1, "one backfill job, not one per GET"
    finally:
        gate.set()


def test_a_get_with_every_claim_embedded_says_nothing_and_queues_nothing(db):
    from fichero_server.importers.derivatives import EMBED_CLAIMS_KIND

    fake = _FakeDb(claims_total=2, indexed=2)
    for name in ("_lance_tables", "search_vectors", "_vector_table_stats", "count", "all"):
        setattr(db, name, getattr(fake, name))
    db._embed_text = lambda text, role="query": [1.0, 0.0]
    with no_model_in_get.marked_get("/api/kg/claim-search"):
        answer = search_claims_semantic_impl(db=db, q="q")
    assert answer.not_embedded is None
    assert db.execute_fetchall("SELECT id FROM jobs WHERE kind = ?", [EMBED_CLAIMS_KIND]) == []


def test_auto_embed_with_no_loop_inside_a_get_queues_the_backfill_instead_of_losing_the_vectors(monkeypatch):
    """Review 366: the sync fallback runs inline in the GET's marked thread, where the passage embed is refused."""
    import contextvars

    from fichero_server.importers import derivatives

    queued: list[object] = []
    monkeypatch.setattr(derivatives, "queue_claims_backfill", lambda database: queued.append(database))

    class Db(DatabaseEmbeddingMixin):
        def _embed_worker(self):
            raise AssertionError("the GET's thread must not embed")

    db, outcome = Db(), []

    def in_a_thread():  # as asyncio.to_thread: a thread with the GET's context and no running loop
        db._schedule_embedding_task([_Row(id="c1")], label="claim")
        outcome.append("returned")

    with no_model_in_get.marked_get("/api/thing"):
        context = contextvars.copy_context()
        thread = threading.Thread(target=context.run, args=(in_a_thread,))
        thread.start()
        thread.join(10)
    assert outcome == ["returned"] and queued == [db]
