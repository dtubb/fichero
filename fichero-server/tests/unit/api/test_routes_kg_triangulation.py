"""Coverage for KG triangulation routes."""

from __future__ import annotations

import asyncio

from fichero_server.api.routes import kg_triangulation as routes
from fichero_server.knowledge.triangulation import TripleKey, TripleSupport


def _support() -> TripleSupport:
    return TripleSupport(
        key=TripleKey("entity-1", "works-at", "archive"),
        support_count=3,
        weighted_support=2.7,
        source_document_ids=("doc-1", "doc-2"),
        claim_ids=("claim-1", "claim-2", "claim-3"),
    )


def test_entity_triangulation_maps_support_records(monkeypatch):
    support = _support()
    calls = []
    monkeypatch.setattr(
        "fichero_server.knowledge.triangulation.triples_for_entity",
        lambda db, entity_id: calls.append((db, entity_id)) or [support],
    )
    db = object()

    response = asyncio.run(routes.entity_triangulation("entity-1", db=db))

    assert calls == [(db, "entity-1")]
    assert response.count == 1
    assert response.items[0].model_dump() == {
        "subject_id": "entity-1",
        "predicate": "works-at",
        "object_text": "archive",
        "support_count": 3,
        "weighted_support": 2.7,
        "corroboration": "corroborated",
        "source_document_ids": ["doc-1", "doc-2"],
        "claim_ids": ["claim-1", "claim-2", "claim-3"],
    }


def test_library_triangulation_forwards_threshold(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "fichero_server.knowledge.triangulation.triangulated_facts",
        lambda db, *, threshold: calls.append((db, threshold)) or [],
    )
    db = object()

    response = asyncio.run(routes.library_triangulation(threshold=4.5, db=db))

    assert response.items == []
    assert response.count == 0
    assert calls == [(db, 4.5)]


def test_recompute_reports_updated_claim_count(monkeypatch):
    monkeypatch.setattr("fichero_server.knowledge.triangulation.persist_support_counts", lambda db: 7)

    response = asyncio.run(routes.recompute_triangulation(db=object()))

    assert response.claims_updated == 7
    assert response.message == "Triangulation recomputed: 7 claim(s) updated."
