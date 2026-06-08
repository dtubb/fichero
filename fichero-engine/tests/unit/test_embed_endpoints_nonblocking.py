"""#1004 — POST /semantic/embed and POST /kg/claim-search/embed must NOT
block the FastAPI event loop.

Both endpoints used to call the synchronous FastEmbed batch
(`db._embed_texts`) directly inside the async handler. For a real corpus
that's hundreds of model invocations on the loop thread, freezing every
other endpoint (e.g. `/api/health`) until the call finished. The fix
delegates the CPU-bound block to `asyncio.to_thread`. These tests verify
that delegation is in place — if a future refactor inlines the sync call
again, the regression is caught here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fichero.api.routes import kg_claim_search, kg_entity_curation
from fichero.kg import rebuild
from fichero.knowledge_models import (
    ClaimType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _entity(name: str = "Davidson") -> KnowledgeEntity:
    return KnowledgeEntity(
        canonical_name=name,
        entity_type=EntityType.person,
        aliases=[],
    )


def _claim(text: str = "X causes Y") -> KnowledgeClaim:
    return KnowledgeClaim(
        text=text,
        claim_type=ClaimType.fact,
        source_document_id="doc1",
    )


@pytest.mark.asyncio
async def test_embed_entities_offloads_to_thread():
    """The route must call asyncio.to_thread, not _embed_texts directly."""
    db = MagicMock()
    db.all.return_value = [_entity()]

    with patch.object(
        kg_entity_curation.asyncio,
        "to_thread",
        new=AsyncMock(return_value=1),
    ) as mocked:
        result = await kg_entity_curation.embed_entities(request=None, db=db)

    mocked.assert_awaited_once()
    # First positional arg is the sync helper; we should never have called
    # the raw `db._embed_texts` directly from the handler thread.
    db._embed_texts.assert_not_called()
    assert result.embedded == 1


@pytest.mark.asyncio
async def test_embed_claims_offloads_to_thread():
    db = MagicMock()
    db.all.return_value = [_claim()]

    with patch.object(
        kg_claim_search.asyncio,
        "to_thread",
        new=AsyncMock(return_value=1),
    ) as mocked:
        result = await kg_claim_search.embed_claims(request=None, db=db)

    mocked.assert_awaited_once()
    db._embed_texts.assert_not_called()
    assert result.embedded == 1


@pytest.mark.asyncio
async def test_embed_entities_empty_short_circuits():
    """No entities → no thread offload, no embed call, response says 0."""
    db = MagicMock()
    db.all.return_value = []

    with patch.object(
        kg_entity_curation.asyncio,
        "to_thread",
        new=AsyncMock(),
    ) as mocked:
        result = await kg_entity_curation.embed_entities(request=None, db=db)

    mocked.assert_not_awaited()
    assert result.embedded == 0


@pytest.mark.asyncio
async def test_search_entities_semantic_falls_back_to_legacy_table():
    """Older libraries may have entity vectors only in `kg_entities`."""
    db = MagicMock()
    entity = _entity("Asprilla")
    entity.id = "entity-1"
    db._lance_tables.return_value = ["kg_entities"]
    db._embed_text.return_value = [0.1, 0.2]
    db.search_vectors.return_value = [{"id": entity.id, "_score": 0.8}]
    db.all.return_value = [entity]

    result = await kg_entity_curation.search_entities_semantic(
        q="Asprilla",
        entity_type=None,
        limit=5,
        db=db,
    )

    db.search_vectors.assert_called_once_with("kg_entities", [0.1, 0.2], limit=5)
    assert result.count == 1
    assert result.items[0]["id"] == entity.id
    assert result.items[0]["similarity_score"] == 0.8


@pytest.mark.asyncio
async def test_embed_claims_empty_short_circuits():
    db = MagicMock()
    db.all.return_value = []

    with patch.object(
        kg_claim_search.asyncio,
        "to_thread",
        new=AsyncMock(),
    ) as mocked:
        result = await kg_claim_search.embed_claims(request=None, db=db)

    mocked.assert_not_awaited()
    assert result.embedded == 0


@pytest.mark.asyncio
async def test_embed_entities_writes_canonical_table_and_searches(db):
    entity = _entity("Asprilla")
    db.save(entity)

    with patch.object(db, "_embed_texts", return_value=[[1.0, 0.0]]):
        result = await kg_entity_curation.embed_entities(request=None, db=db)

    assert result.embedded == 1
    assert "kg_entity_embeddings" in db._lance_tables()

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        search = await kg_entity_curation.search_entities_semantic(
            q="Asprilla",
            entity_type=None,
            limit=5,
            db=db,
        )

    assert search.count == 1
    assert search.items[0]["canonical_name"] == "Asprilla"


@pytest.mark.asyncio
async def test_embed_claims_writes_canonical_table_and_searches(db):
    claim = KnowledgeClaim(
        text="Asprilla worked the mine.",
        claim_type=ClaimType.fact,
        source_document_id="doc-1",
        subject_canonical="Asprilla",
        predicate_verb="worked",
        object_phrase="the mine",
        source_excerpt="Asprilla worked the mine.",
    )
    db.save(claim)

    with patch.object(db, "_embed_texts", return_value=[[1.0, 0.0]]):
        result = await kg_claim_search.embed_claims(request=None, db=db)

    assert result.embedded == 1
    assert "kg_claim_embeddings" in db._lance_tables()

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        search = await kg_claim_search.search_claims_semantic(
            q="Asprilla mine",
            claim_type=None,
            curation_state=None,
            limit=5,
            db=db,
        )

    assert search.count == 1
    assert search.items[0]["text"] == claim.text


def test_rebuild_backfills_entities_and_claims_idempotently(db):
    entity = KnowledgeEntity(
        canonical_name="Marshall",
        entity_type=EntityType.person,
        description="diarist",
    )
    claim = KnowledgeClaim(
        text="Marshall kept a diary.",
        claim_type=ClaimType.fact,
        source_document_id="doc-1",
        subject_canonical="Marshall",
        predicate_verb="kept",
        object_phrase="a diary",
        source_excerpt="Marshall kept a diary.",
    )
    db.save(entity)
    db.save(claim)

    with patch.object(db, "_embed_texts", side_effect=[[[1.0, 0.0]], [[0.0, 1.0]], [[1.0, 0.0]], [[0.0, 1.0]]]):
        first = rebuild.rebuild_kg(db, vectors=True, triples=False)
        second = rebuild.rebuild_kg(db, vectors=True, triples=False)

    assert first["entity_vectors_indexed"] == 1
    assert first["claim_vectors_indexed"] == 1
    assert second["entity_vectors_indexed"] == 1
    assert second["claim_vectors_indexed"] == 1
    assert db.lance.open_table("kg_entity_embeddings").count_rows() == 1
    assert db.lance.open_table("kg_claim_embeddings").count_rows() == 1
