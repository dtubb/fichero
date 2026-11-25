"""The traverse route and the contradiction graph read a real claim link (#6759).

`KnowledgeClaimLink` has `claim_id`, `related_claim_id` and `relation_type`.
Both readers are run on a real `Database` holding real links, not a stand-in.
"""

from __future__ import annotations

import asyncio

from fichero_server.api.routes.kg import graph as routes
from fichero_server.db import Database
from fichero_server.knowledge.graph import contradiction_subgraph
from fichero_server.models.knowledge import (
    ClaimRelationType,
    EntityType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)


def _seed(db: Database) -> tuple[KnowledgeEntity, KnowledgeClaim, KnowledgeClaim, KnowledgeClaim]:
    entity = KnowledgeEntity(canonical_name="Alice", entity_type=EntityType.person)
    db.save(entity)
    said = KnowledgeClaim(text="Alice says X", source_document_id="doc-1", entity_ids=[entity.id])
    denied = KnowledgeClaim(text="Bob says not X", source_document_id="doc-1")
    agreed = KnowledgeClaim(text="Carol says X", source_document_id="doc-1")
    for claim in (said, denied, agreed):
        db.save(claim)
    db.save(KnowledgeClaimLink(
        claim_id=said.id, related_claim_id=denied.id,
        relation_type=ClaimRelationType.contradicts,
    ))
    db.save(KnowledgeClaimLink(
        claim_id=denied.id, related_claim_id=agreed.id,
        relation_type=ClaimRelationType.supports,
    ))
    return entity, said, denied, agreed


def test_traverse_walks_a_real_claim_link(tmp_path):
    db = Database(path=tmp_path / "lib" / "fichero.duckdb")
    try:
        entity, said, denied, agreed = _seed(db)

        response = asyncio.run(
            routes.traverse(entity.id, max_depth=3, include_claims=True, db=db)
        )

        assert [node.id for node in response.nodes] == [entity.id, said.id, denied.id, agreed.id]
        assert [node.depth for node in response.nodes] == [0, 1, 2, 3]
        claim_edges = [
            (edge.source, edge.target, edge.type, edge.depth)
            for edge in response.edges
            if edge.type != "mentioned_in"
        ]
        assert claim_edges == [
            (said.id, denied.id, "contradicts", 2),
            (denied.id, agreed.id, "supports", 3),
        ]
        assert response.nodes[2].metadata == {"relation": "contradicts"}
    finally:
        db.close()


def test_contradiction_subgraph_reads_a_real_claim_link(tmp_path):
    db = Database(path=tmp_path / "lib" / "fichero.duckdb")
    try:
        _entity, said, denied, agreed = _seed(db)

        graph = contradiction_subgraph(db)

        assert set(graph.nodes) == {said.id, denied.id}
        assert {frozenset(edge) for edge in graph.edges} == {frozenset((said.id, denied.id))}
        assert graph.nodes[said.id]["text"] == "Alice says X"
        assert agreed.id not in graph.nodes
    finally:
        db.close()
