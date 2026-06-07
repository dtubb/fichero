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
