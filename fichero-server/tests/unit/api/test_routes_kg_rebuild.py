"""Coverage for derived-store rebuild routes.

#4982: the KG reset route (`POST /kg/reset`, `reset_kg`) and its ONLY test
(`test_reset_deletes_all_knowledge_graph_rows`, against a `FakeDB` whose
`delete(model, row_id)` faked a two-argument signature `Database.delete`
never actually had) are both deleted, not repaired — see
`test_routes_kg_reset_removed.py` for what replaces them.
"""

from __future__ import annotations

import asyncio

from fichero_server.api.routes import kg_rebuild as routes


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

    monkeypatch.setattr("fichero_server.knowledge.rebuild.rebuild_kg", fake_rebuild)
    db = object()

    response = asyncio.run(routes.rebuild_kg(request=None, db=db))

    assert calls == [(db, True, True)]
    assert response.entities == 1
    assert response.triples_written == 3


def test_rebuild_forwards_disabled_stages(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "fichero_server.knowledge.rebuild.rebuild_kg",
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
