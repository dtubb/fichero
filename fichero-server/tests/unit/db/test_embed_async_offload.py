"""Tests for #2231: async wrappers offload ONNX embedding off the event loop.

_embed_text_async() / _embed_texts_async() must:
- Delegate to the synchronous _embed_text / _embed_texts via asyncio.to_thread
- Propagate return values unchanged
- Propagate exceptions from the synchronous layer
- Empty list → empty list (fast path via _embed_texts)
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from fichero_server.db.embeddings import DatabaseEmbeddingMixin


class _FakeMixin(DatabaseEmbeddingMixin):
    def __init__(self) -> None:
        self.path = "/fake/db.duckdb"

    def _embedding_text_for_document(self, doc):
        return doc.page_content

    def passage_units_for_document(self, doc, *, text):
        return []

    def embed(self, doc, *, mode="passage"):
        return False


@pytest.mark.anyio
async def test_embed_text_async_returns_sync_result() -> None:
    mixin = _FakeMixin()
    expected = [0.1, 0.2, 0.3]

    with patch.object(mixin, "_embed_text", return_value=expected) as mock_sync:
        result = await mixin._embed_text_async("hello", role="query")

    assert result == expected
    mock_sync.assert_called_once_with("hello", role="query")


@pytest.mark.anyio
async def test_embed_texts_async_returns_sync_result() -> None:
    mixin = _FakeMixin()
    expected = [[0.1, 0.2], [0.3, 0.4]]

    with patch.object(mixin, "_embed_texts", return_value=expected) as mock_sync:
        result = await mixin._embed_texts_async(["a", "b"], role="passage")

    assert result == expected
    mock_sync.assert_called_once_with(["a", "b"], role="passage")


@pytest.mark.anyio
async def test_embed_text_async_propagates_exception() -> None:
    mixin = _FakeMixin()

    with patch.object(mixin, "_embed_text", side_effect=RuntimeError("ONNX fail")):
        with pytest.raises(RuntimeError, match="ONNX fail"):
            await mixin._embed_text_async("boom", role="query")


@pytest.mark.anyio
async def test_embed_texts_async_empty_list() -> None:
    mixin = _FakeMixin()

    with patch.object(mixin, "_embed_texts", return_value=[]) as mock_sync:
        result = await mixin._embed_texts_async([], role="passage")

    assert result == []
    mock_sync.assert_called_once_with([], role="passage")


@pytest.mark.anyio
async def test_embed_text_async_uses_thread() -> None:
    """Verify the call actually goes through asyncio.to_thread (not blocking the loop)."""
    mixin = _FakeMixin()
    ran_in_thread = []

    def _sync_embed(text, *, role="query"):
        # asyncio.get_event_loop() in a thread pool thread raises DeprecationWarning
        # but asyncio.get_running_loop() should raise RuntimeError (no loop in thread).
        try:
            asyncio.get_running_loop()
            ran_in_thread.append(False)
        except RuntimeError:
            ran_in_thread.append(True)
        return [0.0]

    with patch.object(mixin, "_embed_text", side_effect=_sync_embed):
        await mixin._embed_text_async("test", role="query")

    assert ran_in_thread == [True], "Embedding must run in a thread (no event loop there)"
