"""Coverage for heuristic knowledge-graph prediction helpers."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from fichero.api.routes import kg_predictions as routes
from fichero.models.knowledge import ClaimRelationType, KnowledgeClaim, KnowledgeClaimLink


def test_build_minimal_triples_excludes_sensitive_claims_and_deduplicates():
    public = KnowledgeClaim(
        id="c1", text="public", entity_ids=["e2", "e1", "e1"], metadata={"sensitivity": "public"}
    )
    secret = KnowledgeClaim(
        id="c2", text="secret", entity_ids=["e3"], metadata={"sensitivity": "secret"}
    )
    link = KnowledgeClaimLink(
        claim_id="c1", related_claim_id="c9", relation_type=ClaimRelationType.supports
    )

    assert routes._build_minimal_pykeen_triples([public, secret], [link]) == [
        ("c1", "mentions", "e1"),
        ("c1", "mentions", "e2"),
        ("e1", "co_occurs_with", "e2"),
        ("e2", "co_occurs_with", "e1"),
        ("c1", "claim_supports", "c9"),
    ]


class _DB:
    def __init__(self, tables=None, claims=None, links=None, vectors=None):
        self.tables = tables or set()
        self.claims = claims or []
        self.links = links or []
        self.vectors = vectors or []

    def _lance_tables(self):
        return self.tables

    def all(self, model):
        return self.links if model is KnowledgeClaimLink else self.claims

    async def _embed_text_async(self, _text, *, role):
        assert role == "passage"
        return [0.1]

    def search_vectors(self, _table, _vector, *, limit):
        return self.vectors[:limit]

    def get(self, _model, ident):
        return next((claim for claim in self.claims if claim.id == ident), None)


def test_heuristic_predictions_requires_claim_embeddings():
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.generate_heuristic_predictions(routes.HeuristicRequest(), _DB()))
    assert caught.value.status_code == 503


def test_heuristic_predictions_filters_existing_links_and_entity_scope():
    first = KnowledgeClaim(id="c1", text="one", entity_ids=["e1"])
    second = KnowledgeClaim(id="c2", text="two", entity_ids=["e2"])
    third = KnowledgeClaim(id="c3", text="three", entity_ids=["e1"])
    existing = KnowledgeClaimLink(
        claim_id="c1", related_claim_id="c2", relation_type=ClaimRelationType.supports
    )
    db = _DB(
        tables={routes.KG_CLAIM_EMBEDDINGS_TABLE},
        claims=[first, second, third],
        links=[existing],
        vectors=[{"id": "c1", "_score": 1.0}, {"id": "c2", "_score": 0.9}, {"id": "c3", "_score": 0.8}],
    )

    response = asyncio.run(
        routes.generate_heuristic_predictions(
            routes.HeuristicRequest(top_k=2, entity_id="e1"), db
        )
    )

    assert response.claims_embedded == 3
    pairs = {(p.source_claim_id, p.target_claim_id) for p in response.predictions}
    assert ("c1", "c2") not in pairs and ("c2", "c1") not in pairs
    assert {("c1", "c3"), ("c3", "c1"), ("c2", "c3")} <= pairs
