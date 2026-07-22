"""Coverage for semantic claim-search route helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero.api.routes import kg_claim_search as routes
from fichero.models.knowledge import ClaimType, KnowledgeClaim


class DB:
    def __init__(self, tables=None, results=None):
        self.tables = tables or set()
        self.results = results or []

    def _lance_tables(self):
        return self.tables

    def _embed_text(self, _query):
        return [0.1, 0.2]

    def search_vectors(self, _table, _vector, *, limit):
        return self.results[:limit]

    def all(self, _model):
        return self.claims


def test_vector_similarity_prefers_score_and_converts_distance():
    assert routes._vector_similarity({"_score": 0.75, "_distance": 1.0}) == 0.75
    assert routes._vector_similarity({"_distance": 1.0}) == 0.5
    assert routes._vector_similarity({"_distance": 3.0}) == -1.0
    assert routes._vector_similarity({}) == 0.0


def test_semantic_search_requires_claim_embedding_table():
    db = DB()
    db.claims = []

    with pytest.raises(HTTPException) as caught:
        routes.search_claims_semantic_impl(db=db, q="query")

    assert caught.value.status_code == 503


def test_semantic_search_filters_claim_type_and_returns_scores():
    wanted = KnowledgeClaim(id="wanted", text="wanted", claim_type=ClaimType.fact)
    other = KnowledgeClaim(id="other", text="other", claim_type=ClaimType.analysis)
    db = DB(
        tables={routes.KG_CLAIM_EMBEDDINGS_TABLE},
        results=[{"id": "wanted", "_score": 0.9}, {"id": "other", "_score": 0.8}],
    )
    db.claims = [wanted, other]

    response = routes.search_claims_semantic_impl(
        db=db, q="query", claim_type=ClaimType.fact, limit=5
    )

    assert response.count == 1
    assert response.items[0]["id"] == "wanted"
    assert response.items[0]["similarity_score"] == 0.9
