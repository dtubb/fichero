"""#5360: stored vectors that no longer match their source are reported stale, with the reason."""
from __future__ import annotations

from unittest.mock import MagicMock

from fichero_server.db.embeddings import DatabaseEmbeddingMixin


class _Mixin(DatabaseEmbeddingMixin):
    def __init__(self, stored):
        self._stored = stored

    def _stored_text_and_model(self, table_name, ids):
        return {i: self._stored[i] for i in ids if i in self._stored}

    def _vector_model_metadata(self):
        return {"embedding_model_id": "m1"}


def _item(i):
    return MagicMock(id=i)


def test_stale_reasons_name_text_model_and_missing():
    m = _Mixin({"a": ("text a", "m1"), "b": ("old", "m1"), "c": ("text c", "other")})
    got = m.stale_reasons("t", [_item(i) for i in "abcd"], ["text a", "new", "text c", "text d"])
    assert got == {"b": "text-changed", "c": "model-changed", "d": "not-embedded"}
