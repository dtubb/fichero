"""Tests for #2233: embed_entities/embed_claims batch processing.

Without batching, a 10 000-entity corpus materialises all texts + vectors in
RAM simultaneously. With batch_size, each iteration holds at most batch_size
items. We verify:
- Correct return count (sum across batches)
- save_vectors called once per batch, not once for everything
- Empty input → 0 returned, save_vectors not called
- batch_size=1 emits one save_vectors call per item
- None items in input are filtered before batching
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fichero.db.embeddings import DatabaseEmbeddingMixin


class _FakeMixin(DatabaseEmbeddingMixin):
    """Concrete stub with save_vectors as a MagicMock so tests can assert on calls."""

    def __init__(self) -> None:
        self.path = "/fake/db.duckdb"
        self.save_vectors = MagicMock()

    def _embedding_text_for_document(self, doc):
        return doc.page_content

    def passage_units_for_document(self, doc, *, text):
        return []

    def embed(self, doc, *, mode="passage"):
        return False


def _fake_entity(eid: str) -> MagicMock:
    e = MagicMock()
    e.id = eid
    e.canonical_name = f"Entity {eid}"
    e.aliases = []
    e.description = ""
    e.entity_type = MagicMock(value="person")
    return e


def _fake_claim(cid: str) -> MagicMock:
    c = MagicMock()
    c.id = cid
    c.text = f"Claim {cid}"
    c.source_excerpt = None
    c.subject_canonical = "subj"
    c.svo_subject = None
    c.predicate_verb = "verb"
    c.svo_verb = None
    c.predicate_canonical = None
    c.object_phrase = "obj"
    c.svo_object = None
    c.claim_type = MagicMock(value="fact")
    c.curation_state = MagicMock(value="unreviewed")
    return c


# ---------------------------------------------------------------------------
# embed_entities
# ---------------------------------------------------------------------------


def test_embed_entities_empty_returns_zero() -> None:
    mixin = _FakeMixin()
    result = mixin.embed_entities([])
    assert result == 0
    mixin.save_vectors.assert_not_called()


def test_embed_entities_batches_save_vectors() -> None:
    """With 5 entities and batch_size=2, save_vectors is called 3 times."""
    mixin = _FakeMixin()
    entities = [_fake_entity(str(i)) for i in range(5)]

    fake_vector = [0.1, 0.2]
    with (
        patch.object(mixin, "entity_embedding_text", return_value="text"),
        patch.object(mixin, "_embed_texts", return_value=[fake_vector, fake_vector]),
        patch.object(mixin, "_vector_model_metadata", return_value={}),
    ):
        result = mixin.embed_entities(entities, batch_size=2)

    assert result == 5
    assert mixin.save_vectors.call_count == 3, (
        f"Expected 3 batch saves, got {mixin.save_vectors.call_count}"
    )


def test_embed_entities_batch_size_one() -> None:
    """batch_size=1 → one save_vectors call per entity."""
    mixin = _FakeMixin()
    entities = [_fake_entity(str(i)) for i in range(3)]

    with (
        patch.object(mixin, "entity_embedding_text", return_value="text"),
        patch.object(mixin, "_embed_texts", return_value=[[0.0]]),
        patch.object(mixin, "_vector_model_metadata", return_value={}),
    ):
        result = mixin.embed_entities(entities, batch_size=1)

    assert result == 3
    assert mixin.save_vectors.call_count == 3


def test_embed_entities_filters_none() -> None:
    """None items are stripped before batching."""
    mixin = _FakeMixin()
    entities = [_fake_entity("e1"), None, _fake_entity("e3")]

    with (
        patch.object(mixin, "entity_embedding_text", return_value="text"),
        patch.object(mixin, "_embed_texts", return_value=[[0.0], [0.0]]),
        patch.object(mixin, "_vector_model_metadata", return_value={}),
    ):
        result = mixin.embed_entities(entities)

    assert result == 2


# ---------------------------------------------------------------------------
# embed_claims
# ---------------------------------------------------------------------------


def test_embed_claims_empty_returns_zero() -> None:
    mixin = _FakeMixin()
    result = mixin.embed_claims([])
    assert result == 0
    mixin.save_vectors.assert_not_called()


def test_embed_claims_batches_save_vectors() -> None:
    """With 7 claims and batch_size=3, save_vectors is called 3 times."""
    mixin = _FakeMixin()
    claims = [_fake_claim(str(i)) for i in range(7)]

    with (
        patch.object(mixin, "claim_embedding_text", return_value="claim text"),
        patch.object(mixin, "_embed_texts", return_value=[[0.1], [0.1], [0.1]]),
        patch.object(mixin, "_vector_model_metadata", return_value={}),
    ):
        result = mixin.embed_claims(claims, batch_size=3)

    assert result == 7
    assert mixin.save_vectors.call_count == 3


def test_embed_claims_filters_none() -> None:
    mixin = _FakeMixin()
    claims = [None, _fake_claim("c2"), None]

    with (
        patch.object(mixin, "claim_embedding_text", return_value="claim text"),
        patch.object(mixin, "_embed_texts", return_value=[[0.0]]),
        patch.object(mixin, "_vector_model_metadata", return_value={}),
    ):
        result = mixin.embed_claims(claims)

    assert result == 1
