"""KG rebuild — backfill vectors + RDF graph from canonical DuckDB rows.

Called when:
- A library was catalogued before the embedding store existed and
  needs its entity vectors backfilled.
- A consumer wants an up-to-date ``kg.nt`` RDF snapshot beside the
  DuckDB file for SPARQL queries / external tooling.
- Apple Intelligence improves and re-cataloguing isn't necessary,
  but we still want fresh derived state.

Idempotent: re-running over an already-up-to-date library is cheap
(LanceDB rows replaced by id; RDF file overwritten).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.db import Database

logger = logging.getLogger(__name__)


def rebuild_kg(
    db: "Database",
    *,
    vectors: bool = True,
    triples: bool = True,
    triples_path: Optional[Path] = None,
) -> dict[str, int]:
    """Backfill entity vectors and/or rebuild the RDF triple file.

    Returns a stats dict describing what was processed:
    ``{"entities": N, "claims": M, "entity_vectors_indexed": N,
    "claim_vectors_indexed": M, "triples_written": K}``.

    Vectors path: rewrites the canonical entity + claim embedding tables
    from the DuckDB rows. Existing rows are replaced by id, so a partial
    backfill that gets interrupted can be re-run safely.

    RDF path: queries all entities + claims, builds an in-memory
    graph via ``triples.build_graph``, then serializes to
    ``triples_path`` (defaults to ``<duckdb-parent>/kg.nt``).

    Both stages catch exceptions and log them — a failed vector
    index on entity #42 doesn't stop the loop from processing #43,
    and a failed triple write doesn't take down the caller.
    """
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    stats = {
        "entities": 0,
        "claims": 0,
        "entity_vectors_indexed": 0,
        "claim_vectors_indexed": 0,
        "triples_written": 0,
    }

    entities = db.query(KnowledgeEntity)
    stats["entities"] = len(entities)
    claims = db.query(KnowledgeClaim)
    stats["claims"] = len(claims)

    if vectors:
        try:
            stats["entity_vectors_indexed"] = db.embed_entities(entities)
        except Exception as exc:
            logger.warning("rebuild_kg: entity vector backfill failed: %s", exc)
        try:
            stats["claim_vectors_indexed"] = db.embed_claims(claims)
        except Exception as exc:
            logger.warning("rebuild_kg: claim vector backfill failed: %s", exc)

    if triples:
        try:
            from fichero_server.knowledge import triples as triples_module

            path = triples_path or (Path(db.path).parent / "kg.nt")
            graph = triples_module.build_graph(entities, claims)
            triples_module.persist(graph, path, format="nt")
            stats["triples_written"] = len(graph)
            logger.info(
                "rebuild_kg: wrote %d triples to %s",
                stats["triples_written"], path,
            )
        except Exception as exc:
            logger.warning("rebuild_kg: triple persist failed: %s", exc)

    return stats


__all__ = [name for name in globals() if not name.startswith("__")]
