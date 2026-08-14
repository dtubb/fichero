"""Dataset query — the persistence half of the renderer feed (#1876).

All SQL for POST /api/documents/dataset/query lives HERE, in the DB layer,
behind one typed entry point (`run_dataset_query`). The route keeps HTTP
concerns (limit validation, error mapping, prototype-defaults sidecar).

Injection stance: attribute NAMES are bound as json-path parameters, never
interpolated; every value is a bind parameter; the operator vocabulary is
closed. Invalid attribute names raise ValueError — the route maps it to 422.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from fichero_server.db import Database

# Closed operator vocabulary; each maps to one SQL shape. LOUD on unknowns.
FILTER_OPS = {"eq", "ne", "contains", "gte", "lte", "between", "is_set", "not_set"}
_CASTS = {
    "number": "DOUBLE",
    "rating": "DOUBLE",
    "date": "DATE",
    "checkbox": "BOOLEAN",
}


class DatasetFilter(BaseModel):
    attr: str
    op: Literal["eq", "ne", "contains", "gte", "lte", "between", "is_set", "not_set"]
    value: Any = None
    value2: Any = None  # upper bound for `between`
    type: str = "text"  # declared attribute type — picks the SQL cast


class DatasetSort(BaseModel):
    attr: str
    direction: Literal["asc", "desc"] = "asc"
    type: str = "text"


class DatasetBins(BaseModel):
    attr: str
    granularity: Literal["year", "month", "day"] = "month"


class DatasetQuery(BaseModel):
    """Scope + shapes. Every shape is optional; one request serves a grid
    page, a timeline, a calendar month and facet rails in one round trip."""

    parent_id: Optional[str] = None
    recursive: bool = False
    prototype_key: Optional[str] = None
    filters: list[DatasetFilter] = Field(default_factory=list)
    sort: Optional[DatasetSort] = None
    limit: int = 100
    offset: int = 0
    bins: Optional[DatasetBins] = None
    facets: list[str] = Field(default_factory=list)


def _extract(attr: str, attr_type: str = "text") -> str:
    """SQL for one attribute read. The attribute NAME is bound as a json path
    parameter — never interpolated — so user-named attributes cannot inject."""
    base = "json_extract_string(attributes, ?)"
    cast = _CASTS.get(attr_type)
    return f"TRY_CAST({base} AS {cast})" if cast else base


def _json_path(attr: str) -> str:
    if '"' in attr or "'" in attr:
        raise ValueError(f"Invalid attribute name: {attr!r}")
    return f'$."{attr}"'


def _scope_sql(query: DatasetQuery, params: list[Any]) -> str:
    clauses = ["deleted_at IS NULL"]
    if query.parent_id and query.recursive:
        clauses.append(
            "id IN (WITH RECURSIVE sub(id) AS ("
            " SELECT id FROM documents WHERE parent_id = ? AND deleted_at IS NULL"
            " UNION ALL"
            " SELECT d.id FROM documents d JOIN sub s ON d.parent_id = s.id"
            "  WHERE d.deleted_at IS NULL"
            ") SELECT id FROM sub)"
        )
        params.append(query.parent_id)
    elif query.parent_id:
        clauses.append("parent_id = ?")
        params.append(query.parent_id)
    if query.prototype_key:
        clauses.append("prototype_key = ?")
        params.append(query.prototype_key)
    return " AND ".join(clauses)


def _filter_sql(filters: list[DatasetFilter], params: list[Any]) -> str:
    clauses: list[str] = []
    for spec in filters:
        expr = _extract(spec.attr, spec.type)
        path = _json_path(spec.attr)
        if spec.op == "is_set":
            clauses.append(f"{expr} IS NOT NULL")
            params.append(path)
        elif spec.op == "not_set":
            clauses.append(f"{expr} IS NULL")
            params.append(path)
        elif spec.op == "contains":
            clauses.append(f"{expr} ILIKE ?")
            params.extend([path, f"%{spec.value}%"])
        elif spec.op == "between":
            clauses.append(f"{expr} BETWEEN ? AND ?")
            params.extend([path, spec.value, spec.value2])
        else:
            op_sql = {"eq": "=", "ne": "!=", "gte": ">=", "lte": "<="}[spec.op]
            clauses.append(f"{expr} {op_sql} ?")
            params.extend([path, spec.value])
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def run_dataset_query(db: "Database", query: DatasetQuery) -> dict[str, Any]:
    """Rows page + optional bins + optional facets — everything except the
    prototype-defaults sidecar, which is model-layer resolution, not SQL."""
    import json as _json

    scope_params: list[Any] = []
    scope = _scope_sql(query, scope_params)
    filter_params: list[Any] = []
    filters = _filter_sql(query.filters, filter_params)
    where = f"{scope}{filters}"
    where_params = scope_params + filter_params

    total = db.execute_fetchall(
        f"SELECT COUNT(*) FROM documents WHERE {where}", where_params
    )[0][0]

    order = ""
    order_params: list[Any] = []
    if query.sort:
        expr = _extract(query.sort.attr, query.sort.type)
        direction = "ASC" if query.sort.direction == "asc" else "DESC"
        order = f" ORDER BY {expr} {direction} NULLS LAST, name"
        order_params.append(_json_path(query.sort.attr))
    else:
        order = " ORDER BY sort_order, name"

    rows = db.execute_fetchall(
        f"""
        SELECT id, name, prototype_key, node_kind, doc_type,
               CAST(attributes AS VARCHAR) AS attributes_json
        FROM documents WHERE {where}{order}
        LIMIT ? OFFSET ?
        """,
        where_params + order_params + [query.limit, query.offset],
    )

    result: dict[str, Any] = {
        "total": total,
        "offset": query.offset,
        "rows": [
            {
                "id": r[0],
                "name": r[1],
                "prototype_key": r[2],
                "node_kind": r[3],
                "doc_type": r[4],
                "attributes": _json.loads(r[5]) if r[5] else {},
            }
            for r in rows
        ],
    }

    if query.bins:
        trunc = {"year": 4, "month": 7, "day": 10}[query.bins.granularity]
        bins = db.execute_fetchall(
            f"""
            SELECT substr(json_extract_string(attributes, ?), 1, {trunc}) AS bin,
                   COUNT(*)
            FROM documents WHERE {where}
              AND json_extract_string(attributes, ?) IS NOT NULL
            GROUP BY bin ORDER BY bin
            """,
            [_json_path(query.bins.attr)] + where_params + [_json_path(query.bins.attr)],
        )
        result["bins"] = [{"bin": b[0], "count": b[1]} for b in bins]

    if query.facets:
        facet_out: dict[str, list[dict]] = {}
        for attr in query.facets:
            counts = db.execute_fetchall(
                f"""
                SELECT json_extract_string(attributes, ?) AS v, COUNT(*)
                FROM documents WHERE {where} AND json_extract_string(attributes, ?) IS NOT NULL
                GROUP BY v ORDER BY COUNT(*) DESC, v
                """,
                [_json_path(attr)] + where_params + [_json_path(attr)],
            )
            facet_out[attr] = [{"value": c[0], "count": c[1]} for c in counts]
        result["facets"] = facet_out

    return result
