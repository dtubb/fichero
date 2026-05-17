"""User-extensible classification registry (#915).

Lets researchers add their own ``epistemic_status`` / ``claim_type`` /
``entity_type`` values without code changes. Built-in values (seeded
on first run) cannot be deleted; user-added values can be edited
freely.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClassificationDimension,
    ClassificationValue,
)
from fichero.models import ClassificationListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/classifications")


# Built-in seed values mirror the existing hardcoded enums so a fresh
# library has all the defaults available before the user customises.
_BUILTIN_SEEDS: list[tuple[ClassificationDimension, str, str, str | None]] = [
    (ClassificationDimension.epistemic_status, "confirmed", "Confirmed", "#34C759"),
    (ClassificationDimension.epistemic_status, "tentative", "Tentative", "#FF9500"),
    (ClassificationDimension.epistemic_status, "rejected", "Rejected", "#FF3B30"),
    (ClassificationDimension.claim_type, "fact", "Fact", "#0A84FF"),
    (ClassificationDimension.claim_type, "analysis", "Analysis", "#5856D6"),
    (ClassificationDimension.claim_type, "interpretation", "Interpretation", "#AF52DE"),
    (ClassificationDimension.claim_type, "argument", "Argument", "#FF2D55"),
    (ClassificationDimension.claim_type, "historiography", "Historiography", "#BF5AF2"),
    (ClassificationDimension.claim_type, "theory", "Theory", "#64D2FF"),
    (ClassificationDimension.entity_type, "person", "Person", "#0A84FF"),
    (ClassificationDimension.entity_type, "location", "Place", "#30D158"),
    (ClassificationDimension.entity_type, "organization", "Organization", "#5856D6"),
    (ClassificationDimension.entity_type, "event", "Event", "#FF9500"),
    (ClassificationDimension.entity_type, "concept", "Concept", "#FFD60A"),
    (ClassificationDimension.entity_type, "other", "Other", "#8E8E93"),
]


def _seed_if_empty(db: Database) -> None:
    """Idempotent seed of built-in values when the table is fresh."""
    existing = db.query(ClassificationValue)
    by_key = {(v.dimension, v.key) for v in existing}
    for dim, key, label, color in _BUILTIN_SEEDS:
        if (dim, key) in by_key:
            continue
        db.save(ClassificationValue(
            dimension=dim,
            key=key,
            label=label,
            color=color,
            is_builtin=True,
        ))


@router.get(
    "",
    response_model=ClassificationListResponse,
    summary="List classification values (filter by dimension)",
)
async def list_values(
    dimension: ClassificationDimension | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> ClassificationListResponse:
    _seed_if_empty(db)
    rows = db.query(ClassificationValue)
    if dimension is not None:
        rows = [r for r in rows if r.dimension == dimension]
    rows.sort(key=lambda r: (r.dimension.value, r.sort_order, r.label))
    return rows


class ClassificationCreateRequest(BaseModel):
    dimension: ClassificationDimension
    key: str
    label: str
    description: str | None = None
    parent_key: str | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int = 0


@router.post(
    "",
    response_model=ClassificationValue,
    summary="Add a custom classification value",
)
async def create_value(
    request: ClassificationCreateRequest,
    db: Database = Depends(get_library_database),
) -> ClassificationValue:
    # Reject duplicate (dimension, key).
    for existing in db.query(ClassificationValue):
        if existing.dimension == request.dimension and existing.key == request.key:
            raise HTTPException(
                409,
                f"{request.dimension.value}={request.key} already exists",
            )
    value = ClassificationValue(**request.model_dump(), is_builtin=False)
    db.save(value)
    return value


class ClassificationPatchRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    parent_key: str | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None


@router.patch(
    "/{value_id}",
    response_model=ClassificationValue,
    summary="Edit a classification value's label / color / order",
)
async def patch_value(
    value_id: str,
    request: ClassificationPatchRequest,
    db: Database = Depends(get_library_database),
) -> ClassificationValue:
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Value not found: {value_id}")
    for field, val in request.model_dump(exclude_unset=True).items():
        setattr(value, field, val)
    value.updated_at = datetime.now()
    db.save(value)
    return value


@router.delete("/{value_id}", status_code=204)
async def delete_value(
    value_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Value not found: {value_id}")
    if value.is_builtin:
        raise HTTPException(
            409, f"Built-in value {value.dimension.value}={value.key} cannot be deleted",
        )
    db.delete(value)
