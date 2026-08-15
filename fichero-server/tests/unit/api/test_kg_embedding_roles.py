"""Tests for #2226: E5 query/passage role mismatch in same-type similarity.

Same-type similarity (entity dedup, claim-vs-claim) must embed the probe with
role="passage" so the cosine distance is in the same metric space as the
stored passage vectors.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from fichero_server.knowledge.entity_vectors import find_similar


# ---------------------------------------------------------------------------
# entity_vectors.find_similar — synchronous, easy to test directly
# ---------------------------------------------------------------------------


def _make_entity_db(captured: list[str]) -> MagicMock:
    db = MagicMock()
    db._lance_tables.return_value = ["kg_entity_embeddings"]
    db.entity_embedding_text.return_value = "Leidy Gutierrez person"
    db.search_vectors.return_value = []

    def fake_embed_text(text, *, role="query"):
        captured.append(role)
        return [0.0] * 4

    db._embed_text = fake_embed_text
    return db


def test_entity_dedup_find_similar_uses_passage_role() -> None:
    """Entity dedup embeds probe with role='passage' to match stored passage vectors."""
    captured: list[str] = []
    db = _make_entity_db(captured)

    find_similar(db, canonical_name="Leidy Gutierrez", entity_type="person")

    assert captured, "_embed_text was not called"
    assert captured[0] == "passage", (
        f"Entity dedup should embed probe as 'passage'; got {captured[0]!r}"
    )


# ---------------------------------------------------------------------------
# find_similar_claims — async route, test via pytest-anyio
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_find_similar_claims_uses_passage_role() -> None:
    """find_similar_claims must call _embed_text with role='passage'."""
    from fichero_server.api.routes.kg_claim_search import find_similar_claims
    from fichero_server.models.knowledge import ClaimCurationState, ClaimType, KnowledgeClaim

    captured: list[str] = []

    claim = KnowledgeClaim(
        id="c1",
        text="Leidy founded the organization in 1990.",
        source_document_id="doc1",
        claim_type=ClaimType.fact,
        curation_state=ClaimCurationState.unreviewed,
        entity_ids=[],
    )

    db = MagicMock()
    db._lance_tables.return_value = ["kg_claim_embeddings"]
    db.get.return_value = claim
    db.all.return_value = []
    db.search_vectors.return_value = []

    def fake_embed(text, *, role="query"):
        captured.append(role)
        return [0.0] * 4

    db._embed_text = fake_embed
    # Route now calls the async offload variant (#2231); wire it to the same capture fn
    async def fake_embed_async(text, *, role="query"):
        captured.append(role)
        return [0.0] * 4

    db._embed_text_async = fake_embed_async

    # Pass limit explicitly — Query() default doesn't resolve outside FastAPI
    await find_similar_claims("c1", limit=10, db=db)

    assert captured, "_embed_text was not called"
    assert captured[0] == "passage", (
        f"find_similar_claims should embed with role='passage'; got {captured[0]!r}"
    )


# ---------------------------------------------------------------------------
# generate_heuristic_predictions — async route, test via pytest-anyio
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_heuristic_predictions_uses_passage_role() -> None:
    """generate_heuristic_predictions must call _embed_text with role='passage'."""
    from fichero_server.api.routes.kg_predictions import (
        generate_heuristic_predictions,
        HeuristicRequest,
    )
    from fichero_server.models.knowledge import ClaimCurationState, ClaimType, KnowledgeClaim

    captured: list[str] = []

    claim = KnowledgeClaim(
        id="c1",
        text="Leidy founded the organization.",
        source_document_id="doc1",
        claim_type=ClaimType.fact,
        curation_state=ClaimCurationState.unreviewed,
        entity_ids=[],
    )

    db = MagicMock()
    db._lance_tables.return_value = ["kg_claim_embeddings"]
    # First call → claims; second call → links (none)
    db.all.side_effect = [[claim], []]
    db.search_vectors.return_value = []

    def fake_embed(text, *, role="query"):
        captured.append(role)
        return [0.0] * 4

    db._embed_text = fake_embed
    # Route now calls the async offload variant (#2231); wire it to the same capture fn
    async def fake_embed_async(text, *, role="query"):
        captured.append(role)
        return [0.0] * 4

    db._embed_text_async = fake_embed_async

    req = HeuristicRequest(top_k=5)
    await generate_heuristic_predictions(req, db=db)

    assert captured, "_embed_text was not called for any claim"
    assert all(r == "passage" for r in captured), (
        f"All heuristic-prediction embeds should use role='passage'; got {captured}"
    )


@pytest.mark.anyio
async def test_heuristic_predictions_raises_when_a_claim_cannot_be_embedded() -> None:
    """A failed embedding must not silently omit a claim from predictions."""
    from fichero_server.api.routes.kg_predictions import (
        HeuristicRequest,
        generate_heuristic_predictions,
    )
    from fichero_server.models.knowledge import ClaimCurationState, ClaimType, KnowledgeClaim

    claim = KnowledgeClaim(
        id="broken-claim",
        text="Broken vector input.",
        source_document_id="doc1",
        claim_type=ClaimType.fact,
        curation_state=ClaimCurationState.unreviewed,
        entity_ids=[],
    )
    db = MagicMock()
    db._lance_tables.return_value = ["kg_claim_embeddings"]
    db.all.side_effect = [[claim], []]

    async def fail_embed(*_args, **_kwargs):
        raise RuntimeError("embedding backend unavailable")

    db._embed_text_async = fail_embed

    with pytest.raises(HTTPException) as exc:
        await generate_heuristic_predictions(HeuristicRequest(), db=db)

    assert exc.value.status_code == 503
    assert "broken-claim" in exc.value.detail
