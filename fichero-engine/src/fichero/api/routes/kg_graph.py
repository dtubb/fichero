"""NetworkX-backed KG analytics routes (#376).

Exposes the ``fichero.kg.graph`` module as HTTP endpoints:

- ``GET /api/kg/graph/centrality`` — top-k most central entities,
  optionally filtered by entity type.
- ``GET /api/kg/graph/cooccurrence/{entity_id}`` — neighbours of an
  entity in the co-occurrence graph, sorted by edge weight.
- ``GET /api/kg/graph/path?source=X&target=Y`` — shortest path
  between two entities through the directed claim graph.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/graph")


class CentralityRow(BaseModel):
    """One entity in the centrality ranking."""
    entity_id: str
    canonical_name: str
    degree: int
    betweenness: float
    eigenvector: float


@router.get(
    "/centrality",
    response_model=list[CentralityRow],
    summary="Top-k entities by composite centrality",
    description=(
        "Ranks entities by degree + betweenness + eigenvector "
        "centrality (z-score normalised). Optionally filter to one "
        "EntityType to ask 'who is most central among the people' "
        "vs 'which places connect the most claims'. (#376)"
    ),
)
async def centrality(
    top_k: int = Query(default=20, ge=1, le=200),
    entity_type: str | None = Query(
        default=None,
        description="Filter to one EntityType (person/location/...).",
    ),
    db: Database = Depends(get_library_database),
) -> list[CentralityRow]:
    from fichero.kg.graph import build_full_cooccurrence, centrality as compute_centrality

    g = build_full_cooccurrence(db)
    scores = compute_centrality(g, top_k=top_k, only_type=entity_type)
    return [
        CentralityRow(
            entity_id=s.entity_id,
            canonical_name=s.canonical_name,
            degree=s.degree,
            betweenness=s.betweenness,
            eigenvector=s.eigenvector,
        )
        for s in scores
    ]


class CooccurrenceNeighbour(BaseModel):
    """One entity adjacent to the query entity in the co-occurrence graph."""
    entity_id: str
    canonical_name: str
    entity_type: str
    weight: int  # number of shared source documents


@router.get(
    "/cooccurrence/{entity_id}",
    response_model=list[CooccurrenceNeighbour],
    summary="Co-occurrence neighbours of an entity",
    description=(
        "Returns every other entity that shares a source document "
        "with the target, sorted by descending co-occurrence count. "
        "Use case: 'who appears alongside Eugenio Córdoba in the "
        "archive?' (#376)"
    ),
)
async def cooccurrence_neighbours(
    entity_id: str,
    db: Database = Depends(get_library_database),
) -> list[CooccurrenceNeighbour]:
    from fichero.kg.graph import build_full_cooccurrence, NODE_NAME, NODE_TYPE

    g = build_full_cooccurrence(db)
    if entity_id not in g:
        raise HTTPException(status_code=404, detail=f"Entity not found in graph: {entity_id}")

    rows = []
    for other in g.neighbors(entity_id):
        attrs = g.nodes[other]
        rows.append(CooccurrenceNeighbour(
            entity_id=other,
            canonical_name=attrs.get(NODE_NAME, ""),
            entity_type=attrs.get(NODE_TYPE, ""),
            weight=g[entity_id][other]["weight"],
        ))
    rows.sort(key=lambda r: -r.weight)
    return rows


class PathResponse(BaseModel):
    """Shortest path between two entities as a list of entity IDs."""
    source_id: str
    target_id: str
    path: list[str]
    length: int  # path length in edges; 0 means no path


@router.get(
    "/path",
    response_model=PathResponse,
    summary="Shortest path between two entities",
    description=(
        "Finds the shortest sequence of claim edges connecting "
        "source → target. Returns an empty path with length 0 "
        "when no connection exists. (#376)"
    ),
)
async def shortest_path(
    source: str = Query(..., description="Source entity ID"),
    target: str = Query(..., description="Target entity ID"),
    db: Database = Depends(get_library_database),
) -> PathResponse:
    from fichero.kg.graph import build_full_graph, shortest_path_entities

    g = build_full_graph(db)
    path = shortest_path_entities(g, source, target)
    return PathResponse(
        source_id=source,
        target_id=target,
        path=path,
        length=max(0, len(path) - 1),
    )
