"""Dataset query surface — datasets Stage 2 (spec §3/§4).

One read endpoint serving every renderer over a folder's attribute-bearing
rows: grid/table paging with server-side sort, typed filters, date BINNING
(timeline + calendar), and facet counts — all straight `json_extract` over
``Document.attributes`` in DuckDB, per the 2026-08-13 measurement
(bench_attribute_scale.py: ≤22ms at 100k rows, ≤50ms at 1M for every one
of these shapes; Daniel's ruling: no column promotion).

Effective values: rows return the node's RAW attributes; the response
carries each involved prototype's chain-merged DEFAULTS so a page-sized
client overlays cheaply. Sorting/filtering read the raw values (nulls
last) — defaults are display, not data, and baking them into SQL is the
promotion decision Stage 2 explicitly declined.

The SQL itself lives in ``fichero_server.db.dataset_query`` (#1876: routes
never hold SQL); this module keeps the HTTP concerns — limit validation,
error mapping, and the prototype-defaults sidecar.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.db.dataset_query import (
    DatasetBins,
    DatasetFilter,
    DatasetQuery,
    DatasetSort,
    run_dataset_query,
)
from fichero_server.models.node_prototypes import (
    PrototypeResolutionError,
    resolve_prototype_attributes,
)

__all__ = [
    "DatasetBins",
    "DatasetFilter",
    "DatasetQuery",
    "DatasetSort",
    "dataset_query",
    "router",
]

logger = logging.getLogger(__name__)

router = APIRouter()


def _defaults_for(db: Database, prototype_keys: set[str]) -> dict[str, dict]:
    """Chain-merged declarations per prototype on this page. A key that no
    longer resolves reports its error string instead of vanishing — partial
    data must say so (prefer-raise, surfaced not fatal for a LIST)."""
    out: dict[str, dict] = {}
    for key in sorted(prototype_keys):
        try:
            out[key] = resolve_prototype_attributes(db, key)
        except (PrototypeResolutionError, ValueError) as exc:
            out[key] = {"_unresolved": str(exc)}
    return out


@router.post("/dataset/query")
async def dataset_query(
    query: DatasetQuery,
    db: Database = Depends(get_library_database),
) -> dict:
    """The renderer query: rows page + optional bins + optional facets."""
    if query.limit < 1 or query.limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1..500")

    try:
        result = run_dataset_query(db, query)
    except ValueError as exc:
        # Invalid attribute names raise in the DB layer; here they are 422s.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result["defaults_by_prototype"] = _defaults_for(
        db, {r["prototype_key"] for r in result["rows"] if r["prototype_key"]}
    )
    return result
