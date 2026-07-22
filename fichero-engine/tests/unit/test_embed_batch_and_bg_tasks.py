"""Tests for #2230 and #2229.

#2230: Over-broad except in _embed_document_batch should let non-embedding
       errors (TypeError, KeyError) propagate instead of silently returning
       an empty set (false success).

#2229: _schedule_embedding_task must store task references (prevents GC),
       bound concurrency via semaphore, and clean up refs on completion.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from fichero.db.embeddings import DatabaseEmbeddingMixin


# ---------------------------------------------------------------------------
# Minimal concrete mixin for unit tests
# ---------------------------------------------------------------------------


class _FakeMixin(DatabaseEmbeddingMixin):
    def __init__(self, path="/fake/path.duckdb") -> None:
        self.path = path

    def _embedding_text_for_document(self, doc):
        return doc.page_content

    def passage_units_for_document(self, doc, *, text):
        return []

    def embed(self, doc, *, mode="passage"):
        return False


def _unit(doc_id: str):
    unit = MagicMock()
    unit.text = "some text"
    unit.id = f"u-{doc_id}"
    unit.anchor = MagicMock(
        document_id=doc_id, page_id=None, char_start=0, char_end=5
    )
    return unit


def _doc(doc_id: str):
    doc = MagicMock()
    doc.page_content = "some text"
    doc.id = doc_id
    return doc


# ---------------------------------------------------------------------------
# #2230: narrow except propagates programming-level bugs
# ---------------------------------------------------------------------------


def test_embed_batch_propagates_type_error() -> None:
    """TypeError from wrong schema key must not be swallowed."""
    mixin = _FakeMixin()
    doc = _doc("doc1")

    def bad_embed(texts, *, role="passage"):
        raise TypeError("unexpected schema key")

    with patch.object(mixin, "_embed_texts", bad_embed):
        with patch.object(mixin, "passage_units_for_document", return_value=[_unit("doc1")]):
            with pytest.raises(TypeError):
                mixin._embed_document_batch([doc])


def test_embed_batch_propagates_key_error() -> None:
    """KeyError from unexpected data shape must propagate."""
    mixin = _FakeMixin()
    doc = _doc("doc1")

    def bad_embed(texts, *, role="passage"):
        raise KeyError("missing_key")

    with patch.object(mixin, "_embed_texts", bad_embed):
        with patch.object(mixin, "passage_units_for_document", return_value=[_unit("doc1")]):
            with pytest.raises(KeyError):
                mixin._embed_document_batch([doc])


def test_embed_batch_falls_back_on_runtime_error() -> None:
    """RuntimeError (ONNX model failure) triggers per-doc fallback, not a hard crash."""
    mixin = _FakeMixin()
    doc = _doc("doc1")
    fallback_called: list[str] = []

    def bad_embed(texts, *, role="passage"):
        raise RuntimeError("ONNX inference failed")

    def fake_single_embed(d, *, mode="passage"):
        fallback_called.append(d.id)
        return False

    with patch.object(mixin, "_embed_texts", bad_embed):
        with patch.object(mixin, "passage_units_for_document", return_value=[_unit("doc1")]):
            with patch.object(mixin, "embed", fake_single_embed):
                result = mixin._embed_document_batch([doc])

    assert result == set()
    assert fallback_called == ["doc1"], "Fallback single-embed was not called"


def test_embed_batch_falls_back_on_value_error() -> None:
    """ValueError (model shape mismatch) also triggers per-doc fallback."""
    mixin = _FakeMixin()
    doc = _doc("doc1")
    fallback_called: list[str] = []

    def bad_embed(texts, *, role="passage"):
        raise ValueError("shape mismatch")

    def fake_single_embed(d, *, mode="passage"):
        fallback_called.append(d.id)
        return False

    with patch.object(mixin, "_embed_texts", bad_embed):
        with patch.object(mixin, "passage_units_for_document", return_value=[_unit("doc1")]):
            with patch.object(mixin, "embed", fake_single_embed):
                mixin._embed_document_batch([doc])

    assert fallback_called == ["doc1"]


# ---------------------------------------------------------------------------
# #2229: task tracking and semaphore bounding
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_schedule_embedding_task_tracks_reference() -> None:
    """Background task must be stored in _bg_embedding_tasks while running,
    and removed after completion via the done callback."""
    mixin = _FakeMixin()

    # Patch the Database class that _run imports lazily inside the thread.
    # This avoids touching asyncio.to_thread and tests the real task lifecycle.
    with patch("fichero.db.Database") as MockDB:
        MockDB.return_value.embed_entities.return_value = None
        MockDB.return_value.close.return_value = None

        mixin._schedule_embedding_task(["rec"], label="entity")

        # Task reference exists immediately after create_task()
        assert hasattr(mixin, "_bg_embedding_tasks")
        assert len(mixin._bg_embedding_tasks) == 1

        # Drain the task while the patch is still alive
        tasks = list(mixin._bg_embedding_tasks)
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)  # let done callback fire

    assert len(mixin._bg_embedding_tasks) == 0, "Task ref not cleaned up after completion"
    MockDB.assert_called_once_with(mixin.path)


@pytest.mark.anyio
async def test_schedule_embedding_task_semaphore_limits_concurrency() -> None:
    """At most 2 background embedding tasks may run concurrently."""
    mixin = _FakeMixin()

    peak_active = 0
    active = 0
    lock = threading.Lock()

    def slow_embed(records):
        nonlocal active, peak_active
        with lock:
            active += 1
            if active > peak_active:
                peak_active = active
        time.sleep(0.05)  # simulate work in thread
        with lock:
            active -= 1

    with patch("fichero.db.Database") as MockDB:
        MockDB.return_value.embed_entities.side_effect = slow_embed
        MockDB.return_value.close.return_value = None

        for _ in range(6):
            mixin._schedule_embedding_task(["rec"], label="entity")

        assert len(mixin._bg_embedding_semaphores) == 1

        tasks = list(mixin._bg_embedding_tasks)
        await asyncio.gather(*tasks, return_exceptions=True)

    assert peak_active <= 2, (
        f"Semaphore should cap concurrency at 2; peak was {peak_active}"
    )


def test_schedule_embedding_task_uses_a_semaphore_per_event_loop() -> None:
    mixin = _FakeMixin()

    async def schedule_three() -> list[object]:
        for _ in range(3):
            mixin._schedule_embedding_task(["rec"], label="entity")
        return await asyncio.gather(*list(mixin._bg_embedding_tasks), return_exceptions=True)

    with patch("fichero.db.Database") as MockDB:
        MockDB.return_value.embed_entities.return_value = None
        MockDB.return_value.close.return_value = None

        assert not any(isinstance(result, RuntimeError) for result in asyncio.run(schedule_three()))
        assert not any(isinstance(result, RuntimeError) for result in asyncio.run(schedule_three()))

    assert len(mixin._bg_embedding_semaphores) == 2
