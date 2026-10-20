"""`runtime.embed.once-per-text-version` (#5954): a page is embedded once per version of its text, however many doors ask
(import, after a read, the recipe's search step), and the recipe's step embeds in batches. The embedder is a recording stub."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from fichero_server.db.embeddings import EMBEDDING_MODEL_ID_FIELD, EMBEDDINGS_TABLE, DatabaseEmbeddingMixin
from fichero_server.models import Document


class _Table:
    def __init__(self, rows):
        self.rows, self._where = rows, None

    def search(self):
        return self

    def where(self, clause):
        self._where = clause
        return self

    def limit(self, n):
        return self

    def to_list(self):
        doc = self._where.split("'")[1]
        return [r for r in self.rows if r["document_id"] == doc]


class _Lance:
    def __init__(self, store):
        self.store = store

    def open_table(self, name):
        assert name == EMBEDDINGS_TABLE
        return _Table(self.store)


class _Lib(DatabaseEmbeddingMixin):
    """The mixin with a recording embedder and an in-memory vector table."""

    MODEL = "model-A"

    def __init__(self):
        self.store: list[dict] = []
        self.lance = _Lance(self.store)
        self.texts_embedded: list[str] = []
        self.calls = 0

    def _lance_tables(self):
        return [EMBEDDINGS_TABLE]

    def _get_embedding_model_id(self):
        return self.MODEL

    def _vector_model_metadata(self):
        return {EMBEDDING_MODEL_ID_FIELD: self.MODEL}

    def _use_int8_embeddings(self):
        return False

    def _embed_texts(self, texts, **_):
        self.calls += 1
        self.texts_embedded.extend(texts)
        return [[0.0] for _ in texts]

    def _delete_embedding_rows(self, field, value):
        self.store[:] = [r for r in self.store if r[field] != value]

    def save_vectors(self, table, records):
        self.store.extend(records)

    def save_passage_embeddings(self, doc, text=None):
        units = self.passage_units_for_document(doc, text=text)
        self._delete_embedding_rows("document_id", doc.id)
        vectors = self._embed_texts([u.text for u in units])
        self.store.extend({"id": u.id, "document_id": doc.id, "text": u.text, "vector": v, EMBEDDING_MODEL_ID_FIELD: self.MODEL}
                          for u, v in zip(units, vectors))
        return len(units)

    def embed(self, doc, *, mode="passage"):
        from fichero_server.db import EmbedOutcome

        text = self._embedding_text_for_document(doc)
        if not text:
            return EmbedOutcome(embedded=False, reason="no_embeddable_text", document_id=doc.id)
        return EmbedOutcome(embedded=self.save_passage_embeddings(doc, text=text) > 0, document_id=doc.id)


def _page(name, text):
    return Document(name=name, page_content=text)


LONG = "palabra " * 40


def test_a_page_is_embedded_once_however_many_doors_ask():
    lib, page = _Lib(), _page("p1", LONG)
    assert lib.embed_unless_current(page).embedded and lib.calls == 1  # after the read
    again = lib.embed_unless_current(page)  # the recipe's search step
    assert again.embedded and again.reason == "unchanged" and lib.calls == 1
    assert lib.embed_unless_current(page).reason == "unchanged" and lib.calls == 1


def test_a_changed_text_is_embedded_again_and_the_old_passages_are_gone():
    lib, page = _Lib(), _page("p1", LONG)
    lib.embed_unless_current(page)
    page.page_content = LONG + " nueva frase que cambia el texto de la página"
    assert lib.embed_unless_current(page).reason != "unchanged" and lib.calls == 2
    assert {r["text"] for r in lib.store} == {u.text for u in lib.passage_units_for_document(page, text=page.page_content)}


def test_another_model_embeds_the_page_again():
    lib, page = _Lib(), _page("p1", LONG)
    lib.embed_unless_current(page)
    lib.MODEL = "model-B"
    assert not lib.embedding_is_current(page)
    lib.embed_unless_current(page)
    assert lib.calls == 2


def test_a_page_with_no_vectors_or_no_text_is_not_current():
    lib = _Lib()
    assert not lib.embedding_is_current(_page("p", LONG))
    assert not lib.embedding_is_current(_page("p", ""))


def test_a_batch_leaves_the_current_pages_alone_and_embeds_the_rest_in_one_pass():
    lib = _Lib()
    done, fresh = _page("a", LONG), [_page(f"n{i}", f"texto distinto {i} " * 30) for i in range(5)]
    lib.embed_unless_current(done)
    lib.calls = 0
    current, embedded, wanted = lib.embed_many_unless_current([done, *fresh])
    assert (current, embedded, wanted) == (1, 5, 6)
    assert lib.calls == 1, "five pages, one forward pass"


def test_a_page_with_nothing_to_embed_is_not_counted_as_wanted():
    lib = _Lib()
    assert lib.embed_many_unless_current([_page("empty", ""), _page("p", LONG)]) == (0, 1, 1)


def test_the_recipes_pages_are_queued_in_batches_of_64(tmp_path):
    from fichero_server.actions import page_text_cache as cache

    queued = []

    class Jobs:
        @staticmethod
        def enqueue(db, kind, subject, *, started_by, detail=None):
            queued.append((kind, subject, json.loads(detail)["documents"]))
            return f"job{len(queued)}"

    import fichero_server.execution as execution

    original = execution.jobs
    execution.jobs = Jobs
    try:
        ids = [f"d{i}" for i in range(130)]
        cache.queue_reembed_batches(MagicMock(), ids, started_by="recipe")
    finally:
        execution.jobs = original
    assert [len(q[2]) for q in queued] == [64, 64, 2] and sum((q[2] for q in queued), []) == ids
    assert all(q[0] == cache.REEMBED_KIND and q[1].startswith(cache.BATCH_PREFIX) for q in queued)
