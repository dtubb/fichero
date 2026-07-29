"""SPARQL query endpoint over the RDF triple substrate (#987 / #983 Stage 1c).

The backend already materializes KnowledgeEntity + KnowledgeClaim rows as
RDF triples via ``fichero_server.kg.triples`` (foaf:Person / schema:Place /
skos:Concept ontology + reified rdf:Statement claims with SVO predicates).
This module exposes that graph behind a single HTTP endpoint so the
frontend (and any external SPARQL-aware tooling) can query it directly.

SPARQL is the W3C-standard counterpart to Neo4j's Cypher. Same expressive
power for KG queries; tighter interop with academic linked-data tooling.

Safety:
- Hard cap on result rows (default 1000) — runaway CONSTRUCT/SELECT can't
  bury the response.
- Soft timeout (5s) — long-running queries get an explicit 408 instead of
  hanging the worker.
- Read-only — only SELECT / ASK / CONSTRUCT / DESCRIBE are allowed; the
  request validator rejects INSERT / DELETE / DROP / CLEAR / LOAD verbs.
"""

from __future__ import annotations

import logging
import re
import time
import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from fichero_server.api.main import get_library_database
from fichero_server.db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg")


# Verbs that mutate the graph. Reject these — the endpoint is read-only.
# SPARQL Update keywords per W3C Rec.
_MUTATING_KEYWORDS = re.compile(
    r"\b(INSERT|DELETE|DROP|CLEAR|LOAD|CREATE|COPY|MOVE|ADD)\b",
    re.IGNORECASE,
)


class SparqlRequest(BaseModel):
    query: str = Field(
        ...,
        description=(
            "SPARQL 1.1 query. Read-only: SELECT / ASK / CONSTRUCT / "
            "DESCRIBE only — INSERT/DELETE/DROP/CLEAR/LOAD/CREATE rejected."
        ),
    )
    limit: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Cap on result rows. Defaults to 1000.",
    )


class SparqlResponseRow(BaseModel):
    """One SPARQL result row. Bindings keyed by query variable name."""
    bindings: dict[str, Any]


class SparqlResponse(BaseModel):
    rows: list[SparqlResponseRow]
    row_count: int
    truncated: bool
    elapsed_ms: int


class SparqlExampleQuery(BaseModel):
    """Saved/example query exposed so the frontend has visible seed content."""
    id: str
    title: str
    description: str
    query: str


class SparqlExamplesResponse(BaseModel):
    examples: list[SparqlExampleQuery]


_SPARQL_EXAMPLES: list[SparqlExampleQuery] = [
    SparqlExampleQuery(
        id="people-labels",
        title="People and labels",
        description="List every person in the library with their canonical label.",
        query=(
            "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "SELECT ?person ?label WHERE { "
            "?person a foaf:Person ; rdfs:label ?label . "
            "} ORDER BY ?label"
        ),
    ),
    SparqlExampleQuery(
        id="claims-with-source",
        title="Claims with source pages",
        description="Show claims, their subject entity, and the source page label when present.",
        query=(
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "PREFIX fichero: <https://fichero.app/ns#> "
            "SELECT ?claim ?subjectLabel ?page WHERE { "
            "?claim a rdf:Statement ; rdf:subject ?subject ; "
            "fichero:sourcePageLabel ?page . "
            "?subject rdfs:label ?subjectLabel . "
            "} ORDER BY ?subjectLabel ?page"
        ),
    ),
]


RdfExportFormat = Literal["nt", "turtle", "json-ld", "xml"]

_RDF_MEDIA_TYPES: dict[RdfExportFormat, str] = {
    "nt": "application/n-triples; charset=utf-8",
    "turtle": "text/turtle; charset=utf-8",
    "json-ld": "application/ld+json; charset=utf-8",
    "xml": "application/rdf+xml; charset=utf-8",
}

_RDF_FILENAMES: dict[RdfExportFormat, str] = {
    "nt": "knowledge-graph.nt",
    "turtle": "knowledge-graph.ttl",
    "json-ld": "knowledge-graph.jsonld",
    "xml": "knowledge-graph.rdf",
}


@router.get(
    "/query/examples",
    response_model=SparqlExamplesResponse,
    summary="List example KG queries",
    description=(
        "Returns curated SPARQL example queries so the KG query surface is "
        "discoverable in OpenAPI and the frontend can seed a query console."
    ),
)
async def sparql_examples() -> SparqlExamplesResponse:
    return SparqlExamplesResponse(examples=_SPARQL_EXAMPLES)


@router.post(
    "/query/sparql",
    response_model=SparqlResponse,
    summary="Run a SPARQL query against the library's RDF graph",
    description=(
        "Materializes the entity + claim store as an rdflib Graph "
        "(using the standard W3C ontology — foaf/schema/skos plus the "
        "fichero: namespace for SVO predicates) and runs the SPARQL "
        "query. Read-only; mutating verbs are rejected."
    ),
)
async def sparql_query(
    request: SparqlRequest,
    db: Database = Depends(get_library_database),
) -> SparqlResponse:
    if _MUTATING_KEYWORDS.search(request.query):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Mutating SPARQL verbs (INSERT / DELETE / DROP / CLEAR / "
                "LOAD / CREATE / COPY / MOVE / ADD) are not permitted on "
                "this endpoint. Use the typed mutation routes "
                "(/api/kg/mutations) or rebuild via /api/kg/rebuild."
            ),
        )

    try:
        from fichero_server.kg import triples as triples_module
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SPARQL/RDF support is not installed in this backend.",
        ) from exc

    started = time.monotonic()
    try:
        graph = _cached_rdf_graph(db)
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SPARQL/RDF support is not installed in this backend.",
        ) from exc

    try:
        raw_rows = await asyncio.wait_for(
            asyncio.to_thread(triples_module.sparql, graph, request.query), timeout=5
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="SPARQL query exceeded the 5 second execution limit.",
        ) from exc
    except Exception as exc:
        logger.warning("SPARQL parse/execution failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SPARQL error: {exc}",
        ) from exc

    rows: list[SparqlResponseRow] = []
    truncated = False
    for row in raw_rows:
        if len(rows) >= request.limit:
            truncated = True
            break
        rows.append(SparqlResponseRow(bindings=_row_to_bindings(row)))

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return SparqlResponse(
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=elapsed_ms,
    )


@router.post(
    "/sparql",
    response_model=SparqlResponse,
    summary="Run a SPARQL query against the library's RDF graph (legacy path)",
    description=(
        "Compatibility alias for the canonical ``/api/kg/query/sparql`` route. "
        "Kept so existing callers continue to work while the KG query/export "
        "surface is reorganized."
    ),
    deprecated=True,
)
async def sparql_query_legacy(
    request: SparqlRequest,
    db: Database = Depends(get_library_database),
) -> SparqlResponse:
    return await sparql_query(request=request, db=db)


@router.get(
    "/export/rdf",
    summary="Export the library knowledge graph as RDF",
    description=(
        "Materializes the entity + claim store as RDF and serializes it for "
        "external linked-data tooling. Supports N-Triples, Turtle, JSON-LD, "
        "and RDF/XML."
    ),
    response_class=Response,
)
async def export_rdf(
    format: RdfExportFormat = Query(
        default="turtle",
        description="RDF serialization format.",
    ),
    db: Database = Depends(get_library_database),
) -> Response:
    graph = _cached_rdf_graph(db)
    payload = graph.serialize(format=format, encoding="utf-8")
    headers = {
        "Content-Disposition": f'attachment; filename="{_RDF_FILENAMES[format]}"',
    }
    return Response(
        content=payload,
        media_type=_RDF_MEDIA_TYPES[format],
        headers=headers,
    )


def _row_to_bindings(row: Any) -> dict[str, Any]:
    """Convert an rdflib result row into a JSON-serialisable bindings dict.

    rdflib's ``Graph.query`` yields different shapes by query form:
    - SELECT: ``ResultRow`` per binding (attribute access by variable name)
    - ASK: a single ``bool`` (no variable bindings)
    - CONSTRUCT / DESCRIBE: ``(s, p, o)`` triples

    We normalise all three so callers always get a ``{name: str}`` dict.
    """
    # ASK form — a bare bool, no bindings. Surface under a "result" key.
    if isinstance(row, bool):
        return {"result": str(row).lower()}

    if hasattr(row, "asdict"):
        raw = row.asdict()
    elif hasattr(row, "_asdict"):
        raw = row._asdict()
    elif hasattr(row, "labels") and row.labels is not None:
        # rdflib ResultRow exposes .labels + indexable access.
        raw = {str(label): row[label] for label in row.labels}
    else:
        # CONSTRUCT / DESCRIBE — a (s, p, o) triple.
        try:
            triple = tuple(row)
        except TypeError:
            return {"value": _term_to_json(row)}
        if len(triple) == 3:
            raw = {"subject": triple[0], "predicate": triple[1], "object": triple[2]}
        else:
            raw = {f"col{i}": value for i, value in enumerate(triple)}
    return {key: _term_to_json(value) for key, value in raw.items()}


def _term_to_json(term: Any) -> Any:
    """Coerce an rdflib term to a JSON-serialisable value."""
    if term is None:
        return None
    return str(term)


# Library-scoped rdflib graph cache. Same key shape as the networkx
# graph cache in fichero_server.kg.graph (count + max(updated_at) on claims
# and entities) so both caches invalidate on the same write events.
# Cuts SPARQL latency from ~3-4s to ~50ms on warm cache at 200K triples.
# (#992 — scaling-review bottleneck 3)
_RDF_CACHE: dict[str, tuple[tuple, Any]] = {}
_RDF_CACHE_MAX_ENTRIES = 8


def _cached_rdf_graph(db: Database) -> Any:
    """Return the materialized rdflib graph for ``db``, caching across requests.

    Re-uses the existing graph when the knowledge tables haven't changed.
    Imports rdflib + the triple builder lazily because rdflib pulls in
    pyparsing and pulls hard.
    """
    from fichero_server.kg import graph as graph_module
    from fichero_server.kg import triples as triples_module
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    key = str(db.path)
    signature = graph_module._cache_signature(db)
    cached = _RDF_CACHE.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    graph = triples_module.build_graph(
        db.query(KnowledgeEntity),
        db.query(KnowledgeClaim),
    )
    if len(_RDF_CACHE) >= _RDF_CACHE_MAX_ENTRIES and key not in _RDF_CACHE:
        _RDF_CACHE.pop(next(iter(_RDF_CACHE)))
    _RDF_CACHE[key] = (signature, graph)
    return graph
