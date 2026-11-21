"""`recipes-run.order.embed-waits-for-kraken-never-fails` (#6808): a page's embed that meets Kraken reading waits and runs
afterwards; it never ends failed. Kraken refuses the embedder with `MemoryShortError` (owner rule 2026-11-19), and the
`make-a-vector` job let it through as a `RuntimeError`, which the lane counts as a failure ("Something went wrong in
Fichero" on 6 of 22 jobs). The job now raises the `MemoryShortError`, which the lane turns into waiting."""
import pytest

from fichero_server.actions import page_text_cache
from fichero_server.db import embed_process, embeddings
from fichero_server.execution import jobs
from fichero_server.execution.throttle import MemoryShortError
from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document, FileType


@pytest.fixture
def kraken_reading(monkeypatch):
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_LAST_USE", {})
    monkeypatch.setattr(embeddings, "_LOAD_FAILURES", {})
    monkeypatch.setattr(embed_process, "in_process", lambda: True)
    monkeypatch.setattr(embed_process, "load_text_embedding", lambda *a: pytest.fail("loaded beside Kraken"))
    monkeypatch.setattr(kraken_runtime, "_RESIDENT", {"segment": ("blla", object())})
    monkeypatch.setattr(kraken_runtime, "_a_run_has_pages_in_flight", lambda: True)


def _pages(db, n):
    docs = [Document(name=f"p{i}.jpg", doc_type=DocType.file, file_type=FileType.image,
                     page_content=f"The minutes of the town council, page {i}, as Kraken read them.") for i in range(n)]
    for doc in docs:
        db.save(doc)
    return docs


def test_one_pages_embed_waits_for_kraken(db, kraken_reading):
    [page] = _pages(db, 1)
    with pytest.raises(MemoryShortError):
        page_text_cache._reembed(db, page.id)


def test_a_recipes_batch_embed_waits_for_kraken(db, kraken_reading):
    pages = _pages(db, 3)
    [batch] = page_text_cache.queue_reembed_batches(db, [d.id for d in pages], started_by="owner")
    with pytest.raises(MemoryShortError):
        page_text_cache._reembed(db, jobs.read_job(db, batch)["subject"])
