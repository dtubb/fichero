"""Coverage for KG reset and derived-store rebuild routes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fichero.api.routes import kg_rebuild as routes
from fichero.models.knowledge import KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity


class FakeDB:
    def __init__(self):
        self.rows = {
            KnowledgeEntity: [SimpleNamespace(id="entity-1")],
            KnowledgeClaim: [SimpleNamespace(id="claim-1"), SimpleNamespace(id="claim-2")],
            KnowledgeClaimLink: [SimpleNamespace(id="link-1")],
        }
        self.deleted = []

    def query(self, model):
        return list(self.rows[model])

    def delete(self, model, row_id):
        self.deleted.append((model, row_id))


def test_reset_deletes_all_knowledge_graph_rows():
    db = FakeDB()

    response = asyncio.run(routes.reset_kg(db=db))

    assert response.model_dump() == {
        "entities_deleted": 1,
        "claims_deleted": 2,
        "links_deleted": 1,
    }
    assert {(model, row_id) for model, row_id in db.deleted} == {
        (KnowledgeEntity, "entity-1"),
        (KnowledgeClaim, "claim-1"),
        (KnowledgeClaim, "claim-2"),
        (KnowledgeClaimLink, "link-1"),
    }


def test_rebuild_uses_default_options(monkeypatch):
    calls = []

    def fake_rebuild(db, *, vectors, triples):
        calls.append((db, vectors, triples))
        return {
            "entities": 1,
            "claims": 2,
            "entity_vectors_indexed": 1,
            "claim_vectors_indexed": 2,
            "triples_written": 3,
        }

    monkeypatch.setattr("fichero.kg.rebuild.rebuild_kg", fake_rebuild)
    db = object()

    response = asyncio.run(routes.rebuild_kg(request=None, db=db))

    assert calls == [(db, True, True)]
    assert response.entities == 1
    assert response.triples_written == 3


def test_rebuild_forwards_disabled_stages(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "fichero.kg.rebuild.rebuild_kg",
        lambda db, *, vectors, triples: calls.append((db, vectors, triples)) or {
            "entities": 0,
            "claims": 0,
            "entity_vectors_indexed": 0,
            "claim_vectors_indexed": 0,
            "triples_written": 0,
        },
    )
    db = object()

    asyncio.run(routes.rebuild_kg(routes.RebuildRequest(vectors=False, triples=True), db=db))

    assert calls == [(db, False, True)]
