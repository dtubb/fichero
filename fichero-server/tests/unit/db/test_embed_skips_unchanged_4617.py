"""#4617: a repair re-drop embeds only new or changed text; a row whose stored text and model match is skipped."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fichero_server.db.embeddings import DatabaseEmbeddingMixin


class _Mixin(DatabaseEmbeddingMixin):
    def __init__(self, stored):
        self.save_vectors = MagicMock()
        self._stored = stored  # id -> (text, model_id)

    def _stored_text_and_model(self, table_name, ids):
        return {i: self._stored[i] for i in ids if i in self._stored}


def _entity(eid):
    e = MagicMock()
    e.id, e.canonical_name, e.aliases, e.description = eid, eid, [], ""
    e.entity_type = MagicMock(value="person")
    return e


def _run(stored, entities):
    mixin = _Mixin(stored)
    embedded = []
    def embed(texts, **_):
        embedded.extend(texts)
        return [[0.0] for _ in texts]
    with (
        patch.object(mixin, "entity_embedding_text", side_effect=lambda e: f"text {e.id}"),
        patch.object(mixin, "_embed_texts", side_effect=embed),
        patch.object(mixin, "_vector_model_metadata", return_value={"embedding_model_id": "m1"}),
    ):
        count = mixin.embed_entities(entities)
    return count, embedded, mixin


def test_unchanged_rows_are_not_re_embedded():
    count, embedded, mixin = _run({"a": ("text a", "m1")}, [_entity("a"), _entity("b")])
    assert embedded == ["text b"] and count == 1
    assert [r["id"] for r in mixin.save_vectors.call_args[0][1]] == ["b"]


def test_changed_text_or_model_is_embedded_again():
    _, embedded, _ = _run({"a": ("old text", "m1"), "b": ("text b", "other")}, [_entity("a"), _entity("b")])
    assert embedded == ["text a", "text b"]


def test_all_unchanged_writes_nothing():
    count, embedded, mixin = _run({"a": ("text a", "m1")}, [_entity("a")])
    assert count == 0 and embedded == []
    mixin.save_vectors.assert_not_called()
