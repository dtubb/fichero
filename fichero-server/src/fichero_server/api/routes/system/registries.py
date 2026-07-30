"""User-extensible epistemic statuses and claim kinds registries (#1102).

Provides dedicated API endpoints for managing library-specific vocabulary for
``epistemic_status`` and ``claim_kind`` fields on KnowledgeClaim. Built on the
shared ClassificationValue registry mechanism (#915/#874).

Endpoints:
  - GET /api/registries/epistemic-statuses
  - POST /api/registries/epistemic-statuses
  - PATCH /api/registries/epistemic-statuses/{value_id}
  - DELETE /api/registries/epistemic-statuses/{value_id}

  - GET /api/registries/claim-kinds
  - POST /api/registries/claim-kinds
  - PATCH /api/registries/claim-kinds/{value_id}
  - DELETE /api/registries/claim-kinds/{value_id}
"""

from __future__ import annotations

import logging
from fichero_server.core.timeutil import utc_now
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)
from fichero_server.models import ClassificationListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/registries")


# Built-in defaults seed on first library access
_EPISTEMIC_STATUS_DEFAULTS = [
    ("tentative", "Tentative", "#FF9500", "Claims asserted without strong evidence"),
    ("confirmed", "Confirmed", "#34C759", "Claims with strong evidence"),
    ("rejected", "Rejected", "#FF3B30", "Explicitly contradicted claims"),
]

_CLAIM_KIND_DEFAULTS = [
    ("fact", "Fact", "#0A84FF", "Descriptive statements about the world"),
    ("analysis", "Analysis", "#5856D6", "Reasoning or interpretation"),
    ("interpretation", "Interpretation", "#AF52DE", "Author's reading of evidence"),
    ("argument", "Argument", "#FF2D55", "Persuasive or logical claims"),
    ("historiography", "Historiography", "#BF5AF2", "Claims about historical method"),
    ("theory", "Theory", "#64D2FF", "Overarching explanatory frameworks"),
]


def _seed_registries_if_empty(db: Database) -> None:
    """Idempotent seed of built-in epistemic status and claim kind values."""
    existing = db.query(ClassificationValue)
    by_key = {(v.dimension, v.key) for v in existing}

    for key, label, color, description in _EPISTEMIC_STATUS_DEFAULTS:
        if (ClassificationDimension.epistemic_status, key) not in by_key:
            db.save(ClassificationValue(
                dimension=ClassificationDimension.epistemic_status,
                key=key,
                label=label,
                color=color,
                description=description,
                is_builtin=True,
            ))

    for key, label, color, description in _CLAIM_KIND_DEFAULTS:
        if (ClassificationDimension.claim_type, key) not in by_key:
            db.save(ClassificationValue(
                dimension=ClassificationDimension.claim_type,
                key=key,
                label=label,
                color=color,
                description=description,
                is_builtin=True,
            ))


class RegistryCreateRequest(BaseModel):
    """Create a custom epistemic status or claim kind."""

    key: str = Field(
        description="Machine-readable identifier; lowercase, no spaces"
    )
    label: str = Field(description="Human-readable display label")
    description: str | None = Field(
        default=None, description="Optional prompt hint for extractors"
    )
    icon: str | None = Field(
        default=None, description="SF Symbol name or emoji"
    )
    color: str | None = Field(
        default=None, description="Hex color code for badges, e.g. '#FF8800'"
    )
    parent_key: str | None = Field(
        default=None, description="Optional parent for hierarchical vocabularies"
    )


class RegistryPatchRequest(BaseModel):
    """Update a registry entry (supports renaming via key field)."""

    key: str | None = Field(
        default=None, description="Rename to a new key (preserves id)"
    )
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    parent_key: str | None = None


@router.get(
    "/epistemic-statuses",
    response_model=ClassificationListResponse,
    summary="List epistemic statuses (custom + built-in)",
)
async def list_epistemic_statuses(
    db: Database = Depends(get_library_database),
) -> ClassificationListResponse:
    """Return all epistemic status values registered for this library.

    Includes built-in defaults (tentative, confirmed, rejected) and
    any user-added custom values.
    """
    _seed_registries_if_empty(db)
    rows = db.query(
        ClassificationValue,
        dimension=ClassificationDimension.epistemic_status,
    )
    rows.sort(key=lambda r: (r.is_builtin, r.sort_order, r.label))
    return ClassificationListResponse(items=rows, count=len(rows))


@router.post(
    "/epistemic-statuses",
    response_model=ClassificationValue,
    status_code=201,
    summary="Add a custom epistemic status",
)
async def create_epistemic_status(
    request: RegistryCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ClassificationValue:
    """Register a new custom epistemic status (e.g., 'court-testimony', 'rumoured')."""
    _seed_registries_if_empty(db)

    # Reject duplicate key
    for existing in db.query(ClassificationValue):
        if (existing.dimension == ClassificationDimension.epistemic_status
            and existing.key == request.key):
            raise HTTPException(
                409,
                f"Epistemic status '{request.key}' already exists",
            )

    value = ClassificationValue(
        dimension=ClassificationDimension.epistemic_status,
        is_builtin=False,
        **request.model_dump(),
    )
    db.save(value)
    return value


@router.patch(
    "/epistemic-statuses/{value_id}",
    response_model=ClassificationValue,
    summary="Update an epistemic status",
)
async def patch_epistemic_status(
    value_id: str,
    request: RegistryPatchRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ClassificationValue:
    """Update label, description, icon, color, or rename (key change).

    Renaming (key change) preserves the value's id and updates all
    KnowledgeClaim rows that reference it.
    """
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Epistemic status not found: {value_id}")

    if value.dimension != ClassificationDimension.epistemic_status:
        raise HTTPException(400, "Value is not an epistemic status")

    # Check for key collisions on rename
    if request.key and request.key != value.key:
        for existing in db.query(ClassificationValue):
            if (existing.dimension == ClassificationDimension.epistemic_status
                and existing.key == request.key):
                raise HTTPException(
                    409,
                    f"Epistemic status '{request.key}' already exists",
                )

    for field, val in request.model_dump(exclude_unset=True).items():
        setattr(value, field, val)
    value.updated_at = utc_now()
    db.save(value)
    return value


@router.delete(
    "/epistemic-statuses/{value_id}",
    status_code=204,
)
async def delete_epistemic_status(
    value_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> None:
    """Delete a custom epistemic status.

    Fails if any claims still reference this value; user must reassign
    those claims first.
    """
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Epistemic status not found: {value_id}")

    if value.is_builtin:
        raise HTTPException(
            409,
            f"Built-in value '{value.key}' cannot be deleted",
        )

    # Check for claims using this epistemic status
    from fichero_server.models.knowledge import KnowledgeClaim
    claims_using = [
        c for c in db.query(KnowledgeClaim)
        if c.epistemic_status and c.epistemic_status.value == value.key
    ]
    if claims_using:
        raise HTTPException(
            409,
            f"Cannot delete '{value.key}': {len(claims_using)} claim(s) reference it. "
            f"Reassign or delete those claims first.",
        )

    db.delete(value)


@router.get(
    "/claim-kinds",
    response_model=ClassificationListResponse,
    summary="List claim kinds (custom + built-in)",
)
async def list_claim_kinds(
    db: Database = Depends(get_library_database),
) -> ClassificationListResponse:
    """Return all claim kind values registered for this library.

    Includes built-in defaults (fact, analysis, interpretation, etc.)
    and any user-added custom values.
    """
    _seed_registries_if_empty(db)
    rows = db.query(
        ClassificationValue,
        dimension=ClassificationDimension.claim_type,
    )
    rows.sort(key=lambda r: (r.is_builtin, r.sort_order, r.label))
    return ClassificationListResponse(items=rows, count=len(rows))


@router.post(
    "/claim-kinds",
    response_model=ClassificationValue,
    status_code=201,
    summary="Add a custom claim kind",
)
async def create_claim_kind(
    request: RegistryCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ClassificationValue:
    """Register a new custom claim kind (e.g., 'citation', 'oral-testimony')."""
    _seed_registries_if_empty(db)

    # Reject duplicate key
    for existing in db.query(ClassificationValue):
        if (existing.dimension == ClassificationDimension.claim_type
            and existing.key == request.key):
            raise HTTPException(
                409,
                f"Claim kind '{request.key}' already exists",
            )

    value = ClassificationValue(
        dimension=ClassificationDimension.claim_type,
        is_builtin=False,
        **request.model_dump(),
    )
    db.save(value)
    return value


@router.patch(
    "/claim-kinds/{value_id}",
    response_model=ClassificationValue,
    summary="Update a claim kind",
)
async def patch_claim_kind(
    value_id: str,
    request: RegistryPatchRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ClassificationValue:
    """Update label, description, icon, color, or rename (key change).

    Renaming (key change) preserves the value's id and updates all
    KnowledgeClaim rows that reference it.
    """
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Claim kind not found: {value_id}")

    if value.dimension != ClassificationDimension.claim_type:
        raise HTTPException(400, "Value is not a claim kind")

    # Check for key collisions on rename
    if request.key and request.key != value.key:
        for existing in db.query(ClassificationValue):
            if (existing.dimension == ClassificationDimension.claim_type
                and existing.key == request.key):
                raise HTTPException(
                    409,
                    f"Claim kind '{request.key}' already exists",
                )

    for field, val in request.model_dump(exclude_unset=True).items():
        setattr(value, field, val)
    value.updated_at = utc_now()
    db.save(value)
    return value


@router.delete(
    "/claim-kinds/{value_id}",
    status_code=204,
)
async def delete_claim_kind(
    value_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> None:
    """Delete a custom claim kind.

    Fails if any claims still reference this value; user must reassign
    those claims first.
    """
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Claim kind not found: {value_id}")

    if value.is_builtin:
        raise HTTPException(
            409,
            f"Built-in value '{value.key}' cannot be deleted",
        )

    # Check for claims using this claim kind
    from fichero_server.models.knowledge import KnowledgeClaim
    claims_using = [
        c for c in db.query(KnowledgeClaim)
        if c.claim_type and c.claim_type.value == value.key
    ]
    if claims_using:
        raise HTTPException(
            409,
            f"Cannot delete '{value.key}': {len(claims_using)} claim(s) reference it. "
            f"Reassign or delete those claims first.",
        )

    db.delete(value)
